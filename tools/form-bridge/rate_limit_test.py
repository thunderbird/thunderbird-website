"""The limiter records actual submitters only after successful delivery."""

import copy
import json
from unittest.mock import patch
from urllib.parse import urlencode

from botocore.stub import Stubber
import pytest

import abuse
import lambda_function as bridge
import rate_limit


class SubmissionStore:
    """Model strongly consistent reads and completed-submission writes."""

    def __init__(self):
        self.items = {}

    def get_item(self, **request):
        assert request['ConsistentRead'] is True
        item = self.items.get(request['Key']['ip_key']['S'])
        return {'Item': copy.deepcopy(item)} if item else {}

    def put_item(self, **request):
        assert 'ConditionExpression' not in request
        self.items[request['Item']['ip_key']['S']] = copy.deepcopy(request['Item'])
        return {}


@pytest.fixture
def limiter(monkeypatch):
    store = SubmissionStore()
    clock = [1000000]
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', 'donor-rate-limit-test')
    monkeypatch.setattr(rate_limit, 'client', store)
    monkeypatch.setattr(rate_limit.time, 'time', lambda: clock[0])
    monkeypatch.setattr(bridge, 'FORMASSEMBLY_TRUSTED_IPS', frozenset({'18.221.37.214', '35.169.15.41'}))
    return store, clock


def event(ip='203.0.113.42', connection_ip='18.221.37.214', request_id='first', **fields):
    form = {'tfa_10': 'donor@example.com', 'tfa_163': 'Please send my receipt.'}
    if ip is not None:
        form['submitter_ip'] = ip
    form.update(fields)
    return {'body': urlencode(form), 'requestContext': {'requestId': request_id, 'http': {'sourceIp': connection_ip}}}


def test_one_request_per_twelve_hours_despite_email_or_relay_changes(limiter):
    _, clock = limiter
    with patch.object(bridge, 'send_to_zendesk', return_value=(True, {'ticket': {'id': 1}})) as send:
        assert bridge.lambda_handler(event(), None)['statusCode'] == 200
        clock[0] += rate_limit.WINDOW_SECONDS - 1
        limited = bridge.lambda_handler(event(connection_ip='35.169.15.41', request_id='second', tfa_10='changed@example.org'), None)
        assert limited['statusCode'] == 429
        assert limited['headers']['Retry-After'] == '1'
        assert send.call_count == 1
        # TTL cleanup may not have removed the old row yet.
        clock[0] += 1
        assert bridge.lambda_handler(event(request_id='third'), None)['statusCode'] == 200
        assert send.call_count == 2


def test_different_people_behind_same_relay_have_separate_limits(limiter):
    with patch.object(bridge, 'send_to_zendesk', return_value=(True, None)) as send:
        assert bridge.lambda_handler(event(), None)['statusCode'] == 200
        assert bridge.lambda_handler(event(ip='203.0.113.43', request_id='other'), None)['statusCode'] == 200
        assert send.call_count == 2


def test_window_starts_only_after_zendesk_accepts(limiter):
    store, clock = limiter
    def deliver(*args, **kwargs):
        assert not store.items
        clock[0] += 15
        return True, {'ticket': {'id': 42}}
    with patch.object(bridge, 'send_to_zendesk', side_effect=deliver):
        assert bridge.lambda_handler(event(), None)['statusCode'] == 200
    item = next(iter(store.items.values()))
    assert item['expires_at']['N'] == str(clock[0] + rate_limit.WINDOW_SECONDS)
    assert item['request_id']['S'] == 'first'


def test_unfinished_attempt_never_consumes_an_allowance(limiter):
    store, clock = limiter
    key = rate_limit.check('203.0.113.42')
    clock[0] += 60
    assert rate_limit.check('203.0.113.42') == key
    assert not store.items


def test_mapped_ipv6_cannot_bypass_ipv4_limit(limiter):
    with patch.object(bridge, 'send_to_zendesk', return_value=(True, None)) as send:
        assert bridge.lambda_handler(event(), None)['statusCode'] == 200
        assert bridge.lambda_handler(event(ip='::ffff:203.0.113.42', request_id='mapped'), None)['statusCode'] == 429
        send.assert_called_once()


def test_direct_callers_cannot_choose_their_rate_limit_ip(limiter):
    with patch.object(bridge, 'send_to_zendesk', return_value=(True, None)) as send:
        assert bridge.lambda_handler(event(connection_ip='198.51.100.20'), None)['statusCode'] == 200
        assert bridge.lambda_handler(event(ip='203.0.113.99', connection_ip='198.51.100.20', request_id='spoof'), None)['statusCode'] == 429
        send.assert_called_once()


@pytest.mark.parametrize('ip', [None, 'not-an-ip'])
def test_missing_or_invalid_forwarding_never_limits_shared_relay(limiter, ip):
    store, _ = limiter
    with patch.object(bridge, 'send_to_zendesk') as send:
        assert bridge.lambda_handler(event(ip=ip), None)['statusCode'] == 503
    assert not store.items
    send.assert_not_called()


def test_failed_delivery_uses_no_allowance(limiter):
    store, _ = limiter
    with patch.object(bridge, 'send_to_zendesk', side_effect=[(False, None), (True, None)]):
        assert bridge.lambda_handler(event(), None)['statusCode'] == 500
        assert not store.items
        assert bridge.lambda_handler(event(request_id='retry'), None)['statusCode'] == 200


def test_failed_delivery_leaves_a_concurrent_success_intact(limiter):
    store, _ = limiter
    def deliver(*args, **kwargs):
        key = rate_limit.check('203.0.113.42')
        rate_limit.record_success(key, 'concurrent-success')
        return False, None
    with patch.object(bridge, 'send_to_zendesk', side_effect=deliver):
        assert bridge.lambda_handler(event(), None)['statusCode'] == 500
    assert next(iter(store.items.values()))['request_id']['S'] == 'concurrent-success'


def test_storage_failure_does_not_bypass_limit(limiter):
    with patch.object(rate_limit.client, 'get_item', side_effect=RuntimeError('storage unavailable')):
        with patch.object(bridge, 'send_to_zendesk') as send:
            assert bridge.lambda_handler(event(), None)['statusCode'] == 503
        send.assert_not_called()


def test_recording_failure_still_acknowledges_the_created_ticket(limiter, caplog):
    store, _ = limiter
    with patch.object(rate_limit.client, 'put_item', side_effect=RuntimeError('storage unavailable')):
        with patch.object(bridge, 'send_to_zendesk', return_value=(True, {'ticket': {'id': 42}})):
            assert bridge.lambda_handler(event(), None)['statusCode'] == 200
    assert not store.items
    assert 'Failed to record successful donor submission' in caplog.text


def test_blocked_content_in_new_field_uses_no_allowance(limiter):
    store, _ = limiter
    with patch.object(bridge, 'send_to_zendesk') as send:
        response = bridge.lambda_handler(event(new_string_field='You want money? Give me your body.'), None)
    assert response['statusCode'] == 200
    send.assert_not_called()
    assert not store.items


def test_simple_string_rule_matches_any_string_field(monkeypatch):
    monkeypatch.setenv('DONOR_ABUSE_SIGNATURES', json.dumps(['blocked example']))
    monkeypatch.setattr(abuse, 'RULES', abuse.load_rules())
    assert abuse.match_rule({'new_field': 'BLOCKED...EXAMPLE'}) == 'donor-abuse-1'
    assert abuse.match_rule({'count': 42, 'file': b'blocked example', 'empty': None}) is None


def test_default_rules_keep_current_abuse_patterns(monkeypatch):
    monkeypatch.delenv('DONOR_ABUSE_SIGNATURES', raising=False)
    assert len(abuse.load_rules()) == 4


def test_dynamodb_api_request_is_valid(monkeypatch):
    import boto3
    client = boto3.client('dynamodb', region_name='us-east-2', aws_access_key_id='testing', aws_secret_access_key='testing')
    monkeypatch.setattr(rate_limit, 'client', client)
    monkeypatch.setattr(rate_limit, 'TABLE_NAME', 'donor-rate-limit-test')
    monkeypatch.setattr(rate_limit.time, 'time', lambda: 1000000)
    import hashlib
    ip_key = hashlib.sha256(b'203.0.113.42').hexdigest()
    with Stubber(client) as stubber:
        stubber.add_response('get_item', {}, {
            'TableName': 'donor-rate-limit-test', 'Key': {'ip_key': {'S': ip_key}},
            'ConsistentRead': True,
        })
        assert rate_limit.check('203.0.113.42') == ip_key
        stubber.add_response('put_item', {}, {
            'TableName': 'donor-rate-limit-test',
            'Item': {'ip_key': {'S': ip_key}, 'request_id': {'S': 'first'},
                     'expires_at': {'N': '1043200'}},
        })
        rate_limit.record_success(ip_key, 'first')


def test_ipv6_privacy_addresses_share_a_64_but_other_networks_do_not(limiter):
    with patch.object(bridge, 'send_to_zendesk', return_value=(True, None)):
        assert bridge.lambda_handler(event(ip='2001:db8:1234:1::10'), None)['statusCode'] == 200
        assert bridge.lambda_handler(event(ip='2001:db8:1234:1::20'), None)['statusCode'] == 429
        assert bridge.lambda_handler(event(ip='2001:db8:1234:2::10'), None)['statusCode'] == 200
