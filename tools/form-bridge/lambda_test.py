"""
Unit tests for the donor-form-bridge Lambda function
Tests the form parsing and Zendesk JSON formatting without external calls
"""

import base64
import json
import hashlib
from pathlib import Path
import pytest
from unittest.mock import patch
from types import SimpleNamespace
from lambda_function import ScreenshotAttachment, upload_screenshot_to_zendesk, describe_screenshot_drop

import lambda_function
import abuse
import rate_limit
from lambda_function import map_form_to_zendesk, lambda_handler
import urllib.parse

def test_parse_form_data():
    """Test URL-encoded form data parsing"""
    # Test data as it would come from Form Assembly
    form_body = "tfa_211=Support+Request&tfa_163=I+need+help+with+my+account&tfa_1=John+Doe&tfa_10=john%40example.com"

    result = dict(urllib.parse.parse_qsl(form_body, keep_blank_values=True))

    expected = {
        'tfa_211': 'Support Request',
        'tfa_163': 'I need help with my account',
        'tfa_1': 'John Doe',
        'tfa_10': 'john@example.com'
    }

    assert result == expected


@pytest.fixture
def connector_auth(monkeypatch):
    monkeypatch.setattr(lambda_function, 'FORMASSEMBLY_AUTH_SECRET_ID', 'form-bridge/prod/formassembly')
    monkeypatch.setattr(lambda_function, '_connector_auth_cache', {
        'secret_id': None, 'credentials': None, 'expires_at': 0.0,
    })
    with patch.object(lambda_function.secrets_client, 'get_secret_value', return_value={
        'SecretString': json.dumps({'username': 'connector', 'password': 'test-secret'}),
    }) as get_secret:
        yield get_secret


def _authenticated_connector_event(**fields):
    form = {'tfa_10': 'donor@example.org', 'tfa_163': 'Please send my receipt.',
            'submitter_ip': '203.0.113.42'}
    form.update(fields)
    return {
        'body': urllib.parse.urlencode(form),
        'headers': {
            'Content-Type': 'application/x-www-form-urlencoded',
            'Authorization': 'Basic ' + base64.b64encode(b'connector:test-secret').decode('ascii'),
        },
        'requestContext': {'requestId': 'authenticated-request', 'http': {'sourceIp': '198.51.100.25'}},
    }


def test_authenticated_connector_uses_forwarded_ip_from_unlisted_source(connector_auth, monkeypatch):
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', 'rate-limit-test')
    with patch.object(rate_limit, 'check', return_value='key') as check, patch.object(rate_limit, 'record_success') as record:
        with patch('lambda_function.send_to_zendesk', return_value=(True, {'ticket': {'id': 17}})) as send:
            response = lambda_handler(_authenticated_connector_event(), None)
    assert response['statusCode'] == 200
    check.assert_called_once_with('203.0.113.42')
    record.assert_called_once_with('key', 'authenticated-request')
    assert send.call_args.args[0]['ticket']['metadata']['submitter_ip'] == '203.0.113.42'
    connector_auth.assert_called_once()


@pytest.mark.parametrize('authorization', ['', 'Basic !!!',
    'Basic ' + base64.b64encode(b'connector:wrong').decode('ascii')])
def test_missing_or_wrong_connector_auth_stops_before_processing(connector_auth, monkeypatch,
                                                                  authorization):
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', 'rate-limit-test')
    event = _authenticated_connector_event()
    event['headers']['Authorization'] = authorization
    with patch.object(rate_limit, 'check') as check, patch('lambda_function.send_to_zendesk') as send:
        response = lambda_handler(event, None)
    assert response['statusCode'] == 401
    check.assert_not_called()
    send.assert_not_called()


def test_authenticated_connector_requires_a_submitter_ip(connector_auth, monkeypatch):
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', 'rate-limit-test')
    event = _authenticated_connector_event()
    event['body'] = urllib.parse.urlencode({'tfa_10': 'donor@example.org'})
    with patch.object(rate_limit, 'check') as check, patch('lambda_function.send_to_zendesk') as send:
        response = lambda_handler(event, None)
    assert response['statusCode'] == 503
    check.assert_not_called()
    send.assert_not_called()


def test_auth_secret_outage_fails_closed(connector_auth):
    connector_auth.side_effect = RuntimeError('secret unavailable')
    with patch('lambda_function.send_to_zendesk') as send:
        response = lambda_handler(_authenticated_connector_event(), None)
    assert response['statusCode'] == 503
    send.assert_not_called()

def test_map_form_to_zendesk():
    """Test form data mapping to Zendesk format"""
    form_data = {
        'tfa_211': 'Support Request',
        'tfa_163': 'I need help with my account',
        'tfa_1': 'John Doe',
        'tfa_10': 'john@example.com'
    }

    result = map_form_to_zendesk(form_data)

    expected = {
        "ticket": {
            "subject": "Support Request",
            "comment": {
                "body": "I need help with my account"
            },
            "requester": {
                "name": "John Doe",
                "email": "john@example.com"
            },
            "brand_id": 43075490201747
        }
    }

    assert result == expected

def test_map_form_to_zendesk_with_dropdown():
    """Test form data mapping with dropdown selection"""
    form_data = {
        'tfa_95': 'tfa_193',  # "My donation refunded"
        'tfa_211': 'I need my money back',
        'tfa_163': 'I made a donation but want it refunded',
        'tfa_1': 'Jane Smith',
        'tfa_10': 'jane@example.com'
    }

    result = map_form_to_zendesk(form_data)

    expected = {
        "ticket": {
            "subject": "My donation refunded - I need my money back",
            "comment": {
                "body": "I made a donation but want it refunded"
            },
            "requester": {
                "name": "Jane Smith",
                "email": "jane@example.com"
            },
            "brand_id": 43075490201747
        }
    }

    assert result == expected

def test_map_form_to_zendesk_unknown_dropdown():
    """Test form data mapping with unknown dropdown value"""
    form_data = {
        'tfa_95': 'tfa_999',  # Unknown dropdown value
        'tfa_211': 'Some issue',
        'tfa_163': 'Description of issue',
        'tfa_1': 'Test User',
        'tfa_10': 'test@example.com'
    }

    result = map_form_to_zendesk(form_data)

    # Should fall back to just the user subject without prefix
    expected = {
        "ticket": {
            "subject": "Some issue",
            "comment": {
                "body": "Description of issue"
            },
            "requester": {
                "name": "Test User",
                "email": "test@example.com"
            },
            "brand_id": 43075490201747
        }
    }

    assert result == expected

def _test_lambda_handler_helper(is_base64_encoded: bool = False):
    """Helper function to test lambda handler with different body encodings"""
    import base64

    # Form data to test
    form_body = "tfa_95=tfa_197&tfa_211=Test+Support+Request&tfa_163=This+is+a+test&tfa_1=Test+User&tfa_10=test%40example.com"

    # Encode body if needed
    body = base64.b64encode(form_body.encode('utf-8')).decode('utf-8') if is_base64_encoded else form_body

    # Mock the send_to_zendesk function to avoid external calls
    with patch('lambda_function.send_to_zendesk') as mock_send:
        # Mock successful Zendesk response
        mock_zendesk_response = {
            "ticket": {
                "id": 12345,
                "url": "https://donors.zendesk.com/api/v2/tickets/12345.json",
                "subject": "Technical support for Thunderbird - Test Support Request"
            }
        }
        mock_send.return_value = (True, mock_zendesk_response)

        # Create test event
        event = {
            "body": body,
            "isBase64Encoded": is_base64_encoded,
            "httpMethod": "POST",
            "headers": {
                "content-type": "application/x-www-form-urlencoded"
            }
        }

        # Call the handler
        result = lambda_handler(event, None)

        # Verify response structure
        assert result['statusCode'] == 200

        response_body = json.loads(result['body'])
        assert response_body['message'] == 'Form submitted successfully'
        assert 'zendesk_response' in response_body

        # Verify send_to_zendesk was called with correct data
        mock_send.assert_called_once()
        call_args = mock_send.call_args[0][0]  # Get the ticket_data argument

        assert call_args['ticket']['subject'] == 'Technical support for Thunderbird - Test Support Request'
        assert call_args['ticket']['comment']['body'] == 'This is a test'
        assert call_args['ticket']['requester']['name'] == 'Test User'
        assert call_args['ticket']['requester']['email'] == 'test@example.com'
        assert call_args['ticket']['brand_id'] == 43075490201747

def test_lambda_handler():
    """Test the full Lambda handler with normal body"""
    _test_lambda_handler_helper(is_base64_encoded=False)

def test_lambda_handler_base64_encoded():
    """Test the full Lambda handler with base64 encoded body"""
    _test_lambda_handler_helper(is_base64_encoded=True)

def test_missing_fields():
    """Test handling of missing form fields"""
    # Form data with missing fields
    form_data = {
        'tfa_211': 'Support Request',
        # Missing tfa_163 (comment)
        'tfa_1': 'John Doe',
        # Missing tfa_10 (email)
    }

    result = map_form_to_zendesk(form_data)

    # Should use defaults for missing fields
    assert result['ticket']['subject'] == 'Support Request'
    assert result['ticket']['comment']['body'] == 'No comment provided'
    assert result['ticket']['requester']['name'] == 'John Doe'
    assert result['ticket']['requester']['email'] == ''

def test_lambda_handler_with_empty_fields():
    """Handler should map empty fields to defaults and succeed"""
    with patch('lambda_function.send_to_zendesk') as mock_send:
        mock_send.return_value = (True, {"ok": True})

        body = (
            "tfa_95=tfa_197"  # Technical support dropdown
            "&tfa_211="       # empty subject
            "&tfa_163="       # empty comment
            "&tfa_1=%20%20"   # whitespace-only name
            "&tfa_10=user@example.com"  # non-empty email
        )

        event = {
            "body": body,
            "isBase64Encoded": False,
            "httpMethod": "POST",
            "headers": {"content-type": "application/x-www-form-urlencoded"}
        }

        result = lambda_handler(event, None)
        assert result['statusCode'] == 200

        call_args = mock_send.call_args[0][0]
        assert call_args['ticket']['subject'] == 'Technical support for Thunderbird - No subject provided'
        assert call_args['ticket']['comment']['body'] == 'No comment provided'
        assert call_args['ticket']['requester']['name'] == 'No name provided'
        assert call_args['ticket']['requester']['email'] == 'user@example.com'

def test_whitespace_only_subject():
    """Test subject with only whitespace defaults properly"""
    form_data = {
        'tfa_211': '   ',  # Whitespace-only subject
        'tfa_163': 'Description',
        'tfa_1': 'User',
        'tfa_10': 'user@example.com'
    }

    result = map_form_to_zendesk(form_data)

    # Should use default subject
    assert result['ticket']['subject'] == 'No subject provided'

def test_lambda_handler_malformed_base64():
    """Invalid base64 body should return 400 with appropriate error"""
    event = {
        "body": "not_base64!!!",
        "isBase64Encoded": True,
        "httpMethod": "POST"
    }

    result = lambda_handler(event, None)
    assert result['statusCode'] == 400
    response_body = json.loads(result['body'])
    assert response_body['error'] == 'Invalid base64 encoding'

def _test_invalid_email_helper(body: str):
    """Helper function to test invalid email scenarios"""
    event = {
        "body": body,
        "isBase64Encoded": False,
        "httpMethod": "POST"
    }

    result = lambda_handler(event, None)
    assert result['statusCode'] == 400
    response_body = json.loads(result['body'])
    assert response_body['error'] == 'Email address is required'

def test_lambda_handler_missing_email():
    """Missing email field should return 400 error"""
    _test_invalid_email_helper("tfa_211=Test+Subject&tfa_163=Test+Comment&tfa_1=Test+User")

def test_lambda_handler_empty_email():
    """Empty email field should return 400 error"""
    _test_invalid_email_helper("tfa_211=Test+Subject&tfa_163=Test+Comment&tfa_1=Test+User&tfa_10=")

def test_lambda_handler_whitespace_email():
    """Whitespace-only email field should return 400 error"""
    _test_invalid_email_helper("tfa_211=Test+Subject&tfa_163=Test+Comment&tfa_1=Test+User&tfa_10=%20%20%20")

def test_lambda_handler_no_body():
    """Request with no body should return 400 error"""
    event = {
        "isBase64Encoded": False,
        "httpMethod": "POST"
    }

    result = lambda_handler(event, None)
    assert result['statusCode'] == 400
    response_body = json.loads(result['body'])
    assert response_body['error'] == 'No form data provided'

def test_lambda_handler_empty_body():
    """Request with empty body should return 400 error"""
    event = {
        "body": "",
        "isBase64Encoded": False,
        "httpMethod": "POST"
    }

    result = lambda_handler(event, None)
    assert result['statusCode'] == 400
    response_body = json.loads(result['body'])
    assert response_body['error'] == 'No form data provided'

def test_lambda_handler_zendesk_failure():
    """When Zendesk API fails, handler should return 500"""
    with patch('lambda_function.send_to_zendesk') as mock_send:
        mock_send.return_value = (False, None)  # Simulate Zendesk failure

        event = {
            "body": "tfa_211=Test&tfa_163=Description&tfa_1=User&tfa_10=test@example.com",
            "isBase64Encoded": False,
            "httpMethod": "POST"
        }

        result = lambda_handler(event, None)
        assert result['statusCode'] == 500
        response_body = json.loads(result['body'])
        assert response_body['error'] == 'Failed to submit form'

def test_special_characters_in_form_data():
    """Test handling of special characters, Unicode, and potential XSS attempts"""
    form_data = {
        'tfa_211': 'Test with émoji 🎉 and special chars',
        'tfa_163': '<script>alert("XSS")</script> & HTML entities',
        'tfa_1': 'José María Núñez',  # Unicode characters
        'tfa_10': 'test+user@example.com'  # Plus sign in email
    }

    result = map_form_to_zendesk(form_data)

    # Should preserve all characters without modification
    assert result['ticket']['subject'] == 'Test with émoji 🎉 and special chars'
    assert result['ticket']['comment']['body'] == '<script>alert("XSS")</script> & HTML entities'
    assert result['ticket']['requester']['name'] == 'José María Núñez'
    assert result['ticket']['requester']['email'] == 'test+user@example.com'


@pytest.fixture
def ip_forwarding(monkeypatch):
    monkeypatch.setattr(lambda_function, 'FORMASSEMBLY_TRUSTED_IPS', frozenset({'18.221.37.214'}))
    monkeypatch.setattr(lambda_function, 'ZENDESK_SUBMITTER_IP_FIELD_ID', '123456')

    def make_event(ip='203.0.113.42', connection_ip='18.221.37.214', email='user@example.com'):
        fields = {'tfa_211': 'Help', 'tfa_163': 'Private donor message', 'tfa_10': email}
        if ip is not None:
            fields['submitter_ip'] = ip
        return {
            'body': urllib.parse.urlencode(fields),
            'requestContext': {
                'requestId': 'request-123',
                'http': {'sourceIp': connection_ip},
            },
        }

    return make_event


def submission_log(caplog):
    return next(json.loads(record.message) for record in reversed(caplog.records)
                if record.message.startswith('{')
                and json.loads(record.message).get('event') == 'donor_form_submission')


@pytest.mark.parametrize(('ip', 'expected'), [
    ('203.0.113.42', '203.0.113.42'),
    (' 203.0.113.42 ', '203.0.113.42'),
    ('2001:0db8:0000:0000:0000:0000:0000:0042', '2001:db8::42'),
])
def test_forwarded_ip_reaches_zendesk_and_logs(ip_forwarding, caplog, ip, expected):
    event = ip_forwarding(ip)
    with patch('lambda_function.send_to_zendesk', return_value=(True, {'ticket': {'id': 77}})) as send:
        result = lambda_handler(event, None)

    assert result['statusCode'] == 200
    ticket = send.call_args.args[0]['ticket']
    assert ticket['custom_fields'] == [{'id': 123456, 'value': expected}]
    assert ticket['metadata'] == {
        'submitter_ip': expected,
        'submitter_ip_source': 'formassembly',
        'lambda_request_id': 'request-123',
    }
    assert ticket['comment']['body'] == 'Private donor message'
    logged = submission_log(caplog)
    assert logged['submitter_ip'] == expected
    assert logged['connection_ip'] == '18.221.37.214'
    assert logged['submitter_ip_status'] == 'forwarded'
    assert logged['zendesk_ticket_id'] == 77
    assert 'Private donor message' not in json.dumps(logged)
    assert 'user@example.com' not in json.dumps(logged)


@pytest.mark.parametrize('ip', [
    'not an IP', '203.0.113.42, 198.51.100.1', '203.0.113.42:443',
    '2001:db8::42%eth0', '203.0.113.42\nforged log entry', '%%IP_ADDRESS%%',
])
def test_invalid_forwarded_ip_does_not_break_submission(ip_forwarding, caplog, ip):
    with patch('lambda_function.send_to_zendesk', return_value=(True, None)) as send:
        assert lambda_handler(ip_forwarding(ip), None)['statusCode'] == 200
    ticket = send.call_args.args[0]['ticket']
    assert 'custom_fields' not in ticket
    assert 'metadata' not in ticket
    logged = submission_log(caplog)
    assert logged['submitter_ip'] is None
    assert logged['submitter_ip_status'] == 'invalid'
    assert ip not in json.dumps(logged)


def test_direct_caller_cannot_forge_forwarded_ip(ip_forwarding, caplog):
    event = ip_forwarding(connection_ip='198.51.100.25')
    event['headers'] = {'x-forwarded-for': '18.221.37.214', 'x-real-ip': '18.221.37.214'}
    with patch('lambda_function.send_to_zendesk', return_value=(True, None)) as send:
        assert lambda_handler(event, None)['statusCode'] == 200
    assert 'custom_fields' not in send.call_args.args[0]['ticket']
    logged = submission_log(caplog)
    assert logged['submitter_ip'] is None
    assert logged['connection_ip'] == '198.51.100.25'
    assert logged['submitter_ip_status'] == 'untrusted_source'


def test_missing_forwarding_keeps_connection_ip_separate(ip_forwarding, caplog):
    with patch('lambda_function.send_to_zendesk', return_value=(True, None)) as send:
        assert lambda_handler(ip_forwarding(ip=None), None)['statusCode'] == 200
    assert 'custom_fields' not in send.call_args.args[0]['ticket']
    logged = submission_log(caplog)
    assert logged['submitter_ip'] is None
    assert logged['connection_ip'] == '18.221.37.214'
    assert logged['submitter_ip_status'] == 'missing'


@pytest.mark.parametrize('failure', ['missing_email', 'zendesk_error'])
def test_failed_submissions_still_log_ip(ip_forwarding, caplog, failure):
    event = ip_forwarding(email='' if failure == 'missing_email' else 'user@example.com')
    with patch('lambda_function.send_to_zendesk', return_value=(False, None)) as send:
        result = lambda_handler(event, None)
    assert result['statusCode'] == (400 if failure == 'missing_email' else 500)
    if failure == 'missing_email':
        send.assert_not_called()
    assert submission_log(caplog)['submitter_ip'] == '203.0.113.42'


def test_empty_request_logs_connection_ip(ip_forwarding, caplog):
    event = ip_forwarding()
    event['body'] = ''
    with patch('lambda_function.send_to_zendesk') as send:
        assert lambda_handler(event, None)['statusCode'] == 400
    send.assert_not_called()
    assert submission_log(caplog)['connection_ip'] == '18.221.37.214'


def test_base64_request_preserves_forwarded_ip(ip_forwarding, caplog):
    import base64
    event = ip_forwarding()
    event['body'] = base64.b64encode(event['body'].encode()).decode()
    event['isBase64Encoded'] = True
    with patch('lambda_function.send_to_zendesk', return_value=(True, None)):
        assert lambda_handler(event, None)['statusCode'] == 200
    assert submission_log(caplog)['submitter_ip'] == '203.0.113.42'


def test_no_field_configuration_still_adds_audit_metadata(ip_forwarding, monkeypatch):
    monkeypatch.setattr(lambda_function, 'ZENDESK_SUBMITTER_IP_FIELD_ID', '')
    with patch('lambda_function.send_to_zendesk', return_value=(True, None)) as send:
        assert lambda_handler(ip_forwarding(), None)['statusCode'] == 200
    ticket = send.call_args.args[0]['ticket']
    assert ticket['metadata']['submitter_ip'] == '203.0.113.42'
    assert 'custom_fields' not in ticket


@pytest.fixture
def abuse_filter(monkeypatch):
    # The four observed production signatures, preserved in blocked_strings.json.
    monkeypatch.setenv('DONOR_ABUSE_SIGNATURES', json.dumps([
        ['you want money', 'give me your body'],
        ['金が欲しいんだろ', '身体差し出せよ'],
        ['fuck pussy'],
        ['質問できないやないかドアホ', 'クソ会社'],
    ]))
    monkeypatch.setattr(abuse, 'RULES', abuse.load_rules())
    monkeypatch.setattr(lambda_function, 'FORMASSEMBLY_TRUSTED_IPS', frozenset({'18.221.37.214'}))

    def make_event(**fields):
        data = {
            'tfa_211': 'Donation receipt',
            'tfa_163': 'Please send my receipt.',
            'tfa_1': 'Example donor',
            'tfa_10': 'donor@example.com',
            'submitter_ip': '203.0.113.42',
        }
        data.update(fields)
        return {
            'body': urllib.parse.urlencode(data),
            'requestContext': {
                'requestId': 'abuse-test-request',
                'http': {'sourceIp': '18.221.37.214'},
            },
        }

    return make_event


@pytest.mark.parametrize(('field', 'text', 'rule'), [
    ('tfa_163', 'You want money, right? Give me your body.', 'donor-abuse-1'),
    ('tfa_1', 'You want money? Give me your body.', 'donor-abuse-1'),
    ('tfa_163', 'Ｙｏｕ ｗａｎｔ ｍｏｎｅｙ. G\u200bi\u200bv\u200be me your body.', 'donor-abuse-1'),
    ('tfa_163', '金が欲しいんだろ？ 身体差し出せよ。', 'donor-abuse-2'),
    ('tfa_211', 'FUCK PUSSY', 'donor-abuse-3'),
    ('tfa_163', '質問できないやないかドア\nホ。クソ会社。', 'donor-abuse-4'),
])
def test_known_abuse_skips_zendesk_and_logs_rule(abuse_filter, caplog, field, text, rule):
    with patch('lambda_function.send_to_zendesk') as send:
        response = lambda_handler(abuse_filter(**{field: text}), None)
    assert response['statusCode'] == 200
    assert json.loads(response['body']) == {'message': 'Form submitted successfully'}
    send.assert_not_called()
    logged = submission_log(caplog)
    assert logged['outcome'] == 'blocked'
    assert logged['block_reason'] == 'known_abuse_signature'
    assert logged['block_rule'] == rule
    assert logged['request_id'] == 'abuse-test-request'
    assert logged['connection_ip'] == '18.221.37.214'
    assert logged['submitter_ip'] == '203.0.113.42'
    assert 'zendesk_ticket_id' not in logged
    assert text not in caplog.text
    assert 'donor@example.com' not in caplog.text


@pytest.mark.parametrize('email', ['first@example.com', 'second@example.org', ''])
def test_email_changes_do_not_bypass_abuse_filter(abuse_filter, email):
    with patch('lambda_function.send_to_zendesk') as send:
        response = lambda_handler(abuse_filter(
            tfa_10=email, tfa_163='You want money? Give me your body.'), None)
    assert response['statusCode'] == 200
    send.assert_not_called()


@pytest.mark.parametrize('fields', [
    {},
    {'tfa_163': 'You want money? Please cancel my donation.'},
    {'tfa_163': 'Please explain how to save image attachments in Thunderbird.'},
    {'tfa_163': '返金してください。画像の保存について質問があります。'},
    {'tfa_163': '金が欲しいんだろ？ 返金してください。'},
    {'tfa_211': 'You want money', 'tfa_163': 'Give me your body'},
    {'tfa_163': 'Your company is terrible. Cancel my donation now.'},
])
def test_unmatched_donors_still_reach_zendesk(abuse_filter, caplog, fields):
    with patch('lambda_function.send_to_zendesk', return_value=(True, {'ticket': {'id': 77}})) as send:
        response = lambda_handler(abuse_filter(**fields), None)
    assert response['statusCode'] == 200
    assert json.loads(response['body'])['zendesk_response']['ticket']['id'] == 77
    send.assert_called_once()
    assert 'block_rule' not in submission_log(caplog)


def test_base64_abuse_is_filtered(abuse_filter):
    import base64
    event = abuse_filter(tfa_163='You want money? Give me your body.')
    event['body'] = base64.b64encode(event['body'].encode()).decode()
    event['isBase64Encoded'] = True
    with patch('lambda_function.send_to_zendesk') as send:
        assert lambda_handler(event, None)['statusCode'] == 200
    send.assert_not_called()


def test_abuse_filter_can_be_disabled(abuse_filter, monkeypatch):
    monkeypatch.setenv('DONOR_ABUSE_SIGNATURES', '[]')
    monkeypatch.setattr(abuse, 'RULES', abuse.load_rules())
    with patch('lambda_function.send_to_zendesk', return_value=(True, None)) as send:
        assert lambda_handler(abuse_filter(tfa_163='You want money? Give me your body.'), None)['statusCode'] == 200
    send.assert_called_once()


@pytest.mark.parametrize('configuration', ['{}', 'null', '[[]]', '[[""]]', '[[null]]', '[["---"]]', 'not-json'])
def test_invalid_abuse_configuration_leaves_donors_unblocked(abuse_filter, monkeypatch, configuration):
    monkeypatch.setenv('DONOR_ABUSE_SIGNATURES', configuration)
    monkeypatch.setattr(abuse, 'RULES', abuse.load_rules())
    with patch('lambda_function.send_to_zendesk', return_value=(True, None)) as send:
        assert lambda_handler(abuse_filter(), None)['statusCode'] == 200
    send.assert_called_once()


def test_missing_email_validation_with_abuse_filter_enabled(abuse_filter):
    with patch('lambda_function.send_to_zendesk') as send:
        assert lambda_handler(abuse_filter(tfa_10=''), None)['statusCode'] == 400
    send.assert_not_called()


def _build_multipart_body(
    file_bytes: bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR",
    filename: str = "screenshot.png",
    content_type: str = "image/png",
    extra_fields=None,
):
    """Build a multipart body like FormAssembly sends for screenshot uploads."""
    boundary = "----CursorMultipartBoundary"
    multipart_body = (
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tfa_95"\r\n'
        "\r\n"
        "tfa_186\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tfa_211"\r\n'
        "\r\n"
        "email\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tfa_163"\r\n'
        "\r\n"
        "If you want more donations, it should not be a problem to write any good email adress.\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tfa_1"\r\n'
        "\r\n"
        "Example Donor\r\n"
        f"--{boundary}\r\n"
        'Content-Disposition: form-data; name="tfa_10"\r\n'
        "\r\n"
        "donor@example.org\r\n"
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="tfa_201"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n"
        "\r\n"
    ).encode("utf-8") + file_bytes + (
        "\r\n"
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    if extra_fields:
        extra_parts = ''.join(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'
            for name, value in extra_fields.items()
        ).encode('utf-8')
        closing = f'--{boundary}--\r\n'.encode('utf-8')
        multipart_body = multipart_body[:-len(closing)] + extra_parts + closing
    return boundary, multipart_body


def test_lambda_handler_base64_encoded_multipart_with_attachment():
    """Multipart submissions should attach screenshots when Zendesk upload succeeds."""
    boundary, multipart_body = _build_multipart_body()

    with patch('lambda_function.upload_screenshot_to_zendesk') as mock_upload, patch('lambda_function.send_to_zendesk') as mock_send:
        mock_upload.return_value = ("upload-token-123", None)
        mock_send.return_value = (True, {"ok": True})

        event = {
            "body": base64.b64encode(multipart_body).decode("ascii"),
            "isBase64Encoded": True,
            "httpMethod": "POST",
            "headers": {
                "content-type": f"multipart/form-data; boundary={boundary}"
            }
        }

        result = lambda_handler(event, None)
        assert result["statusCode"] == 200

        call_args = mock_send.call_args[0][0]
        assert call_args["ticket"]["subject"] == "Help with the donation form - email"
        assert "good email adress" in call_args["ticket"]["comment"]["body"]
        assert call_args["ticket"]["comment"]["uploads"] == ["upload-token-123"]
        assert call_args["ticket"]["requester"]["name"] == "Example Donor"
        assert call_args["ticket"]["requester"]["email"] == "donor@example.org"


def test_upload_screenshot_to_zendesk_success():
    """Supported screenshots should return the Zendesk upload token."""
    screenshot = ScreenshotAttachment(
        filename="screen.webp",
        content_type="image/webp",
        data=b"RIFF\x00\x00\x00\x00WEBPVP8 "
    )

    with patch('lambda_function.get_zendesk_headers') as mock_headers, patch('lambda_function.http.request') as mock_request:
        mock_headers.return_value = {"Content-Type": "image/webp", "Authorization": "Basic test"}
        mock_request.return_value = SimpleNamespace(
            status=201,
            data=json.dumps({"upload": {"token": "upload-token-123"}}).encode("utf-8")
        )

        token, reason = upload_screenshot_to_zendesk(screenshot)

    assert token == "upload-token-123"
    assert reason is None
    args, kwargs = mock_request.call_args
    assert args == ('POST', 'https://donors.zendesk.com/api/v2/uploads.json?filename=screen.webp')
    assert kwargs['body'] == screenshot.data
    assert kwargs['headers']['Content-Type'] == 'image/webp'
    assert kwargs['retries'] is False
    assert kwargs['redirect'] is False


def test_upload_screenshot_to_zendesk_rejects_oversized_file():
    """Oversized screenshots should be dropped before any Zendesk call."""
    screenshot = ScreenshotAttachment(
        filename="screen.png",
        content_type="image/png",
        data=b"x" * (1024 * 1024 + 1)
    )

    token, reason = upload_screenshot_to_zendesk(screenshot)

    assert token is None
    assert reason == "it exceeded the 1 MiB size limit"


def test_upload_screenshot_to_zendesk_rejects_unsupported_type():
    """Unsupported screenshot types should be dropped before any Zendesk call."""
    screenshot = ScreenshotAttachment(
        filename="screen.bmp",
        content_type="image/bmp",
        data=b"BM" + b"\x00" * 16
    )

    token, reason = upload_screenshot_to_zendesk(screenshot)

    assert token is None
    assert reason == "unsupported file type"


def test_lambda_handler_multipart_dropped_attachment_adds_note():
    """Screenshot upload failures should still create a ticket with a note."""
    boundary, multipart_body = _build_multipart_body(file_bytes=b"x" * (1024 * 1024 + 1))

    with patch('lambda_function.upload_screenshot_to_zendesk') as mock_upload, patch('lambda_function.send_to_zendesk') as mock_send:
        mock_upload.return_value = (None, "it exceeded the 1 MiB size limit")
        mock_send.return_value = (True, {"ok": True})

        event = {
            "body": base64.b64encode(multipart_body).decode("ascii"),
            "isBase64Encoded": True,
            "httpMethod": "POST",
            "headers": {
                "content-type": f"multipart/form-data; boundary={boundary}"
            }
        }

        result = lambda_handler(event, None)
        assert result["statusCode"] == 200

        call_args = mock_send.call_args[0][0]
        assert "Screenshot was submitted but dropped" in call_args["ticket"]["comment"]["body"]
        assert describe_screenshot_drop("it exceeded the 1 MiB size limit") in call_args["ticket"]["comment"]["body"]
        assert "uploads" not in call_args["ticket"]["comment"]


def _multipart_event(extra_fields=None):
    boundary, body = _build_multipart_body(extra_fields=extra_fields)
    return {
        'body': base64.b64encode(body).decode('ascii'),
        'isBase64Encoded': True,
        'headers': {'Content-Type': f'multipart/form-data; boundary={boundary}'},
        'requestContext': {'requestId': 'multipart-test', 'http': {'sourceIp': '18.221.37.214'}},
    }


def test_multipart_keeps_forwarded_ip_and_attachment(ip_forwarding):
    with patch('lambda_function.upload_screenshot_to_zendesk', return_value=('image-token', None)):
        with patch('lambda_function.send_to_zendesk', return_value=(True, None)) as send:
            response = lambda_handler(_multipart_event({'submitter_ip': '203.0.113.42'}), None)
    assert response['statusCode'] == 200
    ticket = send.call_args.args[0]['ticket']
    assert ticket['metadata']['submitter_ip'] == '203.0.113.42'
    assert ticket['custom_fields'] == [{'id': 123456, 'value': '203.0.113.42'}]
    assert ticket['comment']['uploads'] == ['image-token']


def test_multipart_unknown_string_field_is_filtered_before_upload(abuse_filter, monkeypatch):
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', 'rate-limit-test')
    with patch('lambda_function.upload_screenshot_to_zendesk') as upload, patch('lambda_function.send_to_zendesk') as send, patch('rate_limit.check') as check:
        response = lambda_handler(_multipart_event({'new_field': 'You want money? Give me your body.'}), None)
    assert response['statusCode'] == 200
    upload.assert_not_called()
    send.assert_not_called()
    check.assert_not_called()


def test_rate_limited_multipart_does_not_upload_screenshot(ip_forwarding, monkeypatch):
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', 'rate-limit-test')
    with patch('rate_limit.check', side_effect=rate_limit.RateLimitExceeded(120)):
        with patch('lambda_function.upload_screenshot_to_zendesk') as upload, patch('lambda_function.send_to_zendesk') as send:
            response = lambda_handler(_multipart_event({'submitter_ip': '203.0.113.42'}), None)
    assert response['statusCode'] == 429
    upload.assert_not_called()
    send.assert_not_called()


@pytest.mark.parametrize('content_type', ['multipart/form-data', 'application/json'])
def test_invalid_upload_encoding_keeps_zendesk_untouched(content_type):
    with patch('lambda_function.upload_screenshot_to_zendesk') as upload, patch('lambda_function.send_to_zendesk') as send:
        response = lambda_handler({'body': 'malformed', 'headers': {'content-type': content_type}}, None)
    assert response['statusCode'] == 400
    upload.assert_not_called()
    send.assert_not_called()


def test_multipart_boundary_parameter_is_case_insensitive():
    boundary, body = _build_multipart_body()
    fields, screenshot = lambda_function.parse_form_data(
        base64.b64encode(body).decode(), {'content-type': f'multipart/form-data; BOUNDARY="{boundary}"'}, True,
    )
    assert fields['tfa_10'] == 'donor@example.org'
    assert screenshot.data


@pytest.fixture
def zendesk_server():
    """Exercise real urllib3 POST behavior against a local test server."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    import threading
    state = {'status': 201, 'body': b'{"ticket":{"id":17}}', 'requests': []}
    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            state['requests'].append(({key.lower(): value for key, value in self.headers.items()}, self.rfile.read(int(self.headers['Content-Length']))))
            is_upload = self.path.startswith('/uploads.json?')
            response_body = b'{"upload":{"token":"captured-upload-token"}}' if is_upload else state['body']
            self.send_response(201 if is_upload else state['status'])
            self.send_header('Retry-After', '3600')
            self.send_header('Content-Length', str(len(response_body)))
            self.end_headers()
            self.wfile.write(response_body)

        def log_message(self, *args):
            pass
    server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    yield f'http://127.0.0.1:{server.server_port}/tickets.json', state
    server.shutdown()
    server.server_close()
    worker.join()


def test_real_formassembly_upload_reaches_ticket_unchanged(zendesk_server, monkeypatch):
    event = json.loads((Path(__file__).parent / 'fixtures' / 'formassembly-screenshot.json').read_text())
    fields, image = lambda_function.parse_form_data(event['body'], event['headers'], event['isBase64Encoded'])
    assert image.filename == 'donor-attachment-test.png'
    assert image.content_type == 'image/png'
    assert hashlib.sha256(image.data).hexdigest() == event['expectedImageSha256']
    assert fields['submitter_ip'] == '203.0.113.42'

    url, state = zendesk_server
    monkeypatch.setattr(lambda_function, 'ZENDESK_URL', url)
    monkeypatch.setattr(lambda_function, 'ZENDESK_UPLOADS_URL', url.replace('/tickets.json', '/uploads.json'))
    monkeypatch.setattr(lambda_function, 'FORMASSEMBLY_AUTH_SECRET_ID', '')
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', '')
    with patch.object(lambda_function.secrets_client, 'get_secret_value', return_value={
        'SecretString': json.dumps({'credentials': 'test-agent:test-secret'}),
    }):
        assert lambda_handler(event, None)['statusCode'] == 200

    assert len(state['requests']) == 2
    upload_headers, upload_body = state['requests'][0]
    assert upload_headers['content-type'] == 'image/png'
    assert upload_body == image.data
    ticket_headers, ticket_body = state['requests'][1]
    assert ticket_headers['content-type'] == 'application/json'
    ticket = json.loads(ticket_body)['ticket']
    assert ticket['comment']['uploads'] == ['captured-upload-token']
    assert ticket['comment']['body'] == fields['tfa_163']
    assert ticket['requester']['email'] == 'donor@example.org'


@pytest.mark.parametrize('status', [201, 429, 502, 503, 504])
def test_ticket_http_contract_and_no_retry_after_sleep(zendesk_server, monkeypatch, status):
    url, state = zendesk_server
    state['status'] = status
    if status != 201:
        state['body'] = b'{"error":"private donor message and donor@example.org"}'
    monkeypatch.setattr(lambda_function, 'ZENDESK_URL', url)
    with patch.object(lambda_function.secrets_client, 'get_secret_value', return_value={
        'SecretString': json.dumps({'credentials': 'test-agent:test-secret'}),
    }):
        success, result = lambda_function.send_to_zendesk(
            {'ticket': {'subject': 'test'}}, request_id='stable-request-id',
        )
    assert success == (status == 201)
    assert len(state['requests']) == 1
    headers, body = state['requests'][0]
    assert headers['idempotency-key'] == 'stable-request-id'
    assert headers['authorization'] == 'Basic ' + base64.b64encode(b'test-agent:test-secret').decode()
    assert headers['content-type'] == 'application/json'
    assert json.loads(body) == {'ticket': {'subject': 'test'}}


@pytest.mark.parametrize('body', [b'not-json', b'\xff', b'[]', b'{"ticket":null}'])
def test_created_ticket_with_unreadable_response_is_still_successful(body):
    with patch('lambda_function.get_zendesk_headers', return_value={}):
        with patch('lambda_function.http.request', return_value=SimpleNamespace(status=201, data=body)):
            assert lambda_function.send_to_zendesk({}) == (True, None)
