"""
Unit tests for the donor-form-bridge Lambda function
Tests the form parsing and Zendesk JSON formatting without external calls
"""

import json
import pytest
from unittest.mock import patch

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
