import json
import base64
import urllib3
import urllib.parse
import boto3
from botocore.exceptions import ClientError
import logging
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize clients
http = urllib3.PoolManager()
secrets_client = boto3.client('secretsmanager', region_name='us-east-2')

# Constants
BRAND_ID = 43075490201747
ZENDESK_URL = "https://donors.zendesk.com/api/v2/tickets.json"


# Name and subject are required by the form so those should never be used.
# They are included to make the bridge more robust in case the form changes.
# There's no default email because there would be no way to contact the submitter.
DEFAULT_NAME = 'No name provided' # tfa_1
DEFAULT_COMMENT = 'No comment provided' # tfa_163
DEFAULT_SUBJECT = 'No subject provided' # tfa_211


# These map form fields to Zendesk fields.
# tfa_211, tfa_1, and tfa_10 are required by the form.
# tfa_163 is optional but Zendesk requires it.
FIELD_MAPPINGS = {
    'tfa_211': 'subject',
    'tfa_163': 'comment_body',
    'tfa_1': 'name',
    'tfa_10': 'email'
}

# Dropdown option mappings for tfa_95
DROPDOWN_OPTIONS = {
    'tfa_186': 'Help with the donation form',
    'tfa_193': 'My donation refunded',
    'tfa_194': 'Help with an unauthorized or fraudulent donation',
    'tfa_188': 'To update my donation email address',
    'tfa_187': 'To change or cancel my monthly recurring donation',
    'tfa_189': 'Help donating by bank transfer (SEPA/IBAN)',
    'tfa_190': 'Help donating with another currency or payment method',
    'tfa_191': 'A copy of my donation receipt',
    'tfa_197': 'Technical support for Thunderbird',
    'tfa_198': 'To request a feature for Thunderbird',
    'tfa_196': 'Help with something else'
}

def map_form_to_zendesk(form_data: Dict[str, str]) -> Dict[str, Any]:
    """Map form fields to Zendesk ticket format"""
    # Map basic fields
    mapped_data = {
        zendesk_field: form_data.get(form_field)
        for form_field, zendesk_field in FIELD_MAPPINGS.items()
        if form_field in form_data
    }

    # Build subject with optional dropdown prefix
    user_subject = mapped_data.get('subject', '').strip() or DEFAULT_SUBJECT
    dropdown_text = DROPDOWN_OPTIONS.get(form_data.get('tfa_95', ''), '')
    final_subject = f"{dropdown_text} - {user_subject}" if dropdown_text else user_subject

    # Build Zendesk ticket payload
    return {
        "ticket": {
            "subject": final_subject,
            "comment": {
                "body": (mapped_data.get('comment_body', '').strip() or DEFAULT_COMMENT)
            },
            "requester": {
                "name": (mapped_data.get('name', '').strip() or DEFAULT_NAME),
                "email": mapped_data.get('email', '')
            },
            "brand_id": BRAND_ID
        }
    }

def send_to_zendesk(ticket_data: Dict[str, Any]) -> tuple[bool, Optional[Dict[str, Any]]]:
    """Send ticket data to Zendesk API"""
    try:
        # Get Zendesk credentials from AWS Secrets Manager
        response = secrets_client.get_secret_value(SecretId="form-bridge/prod/zendesk")
        credentials = json.loads(response['SecretString'])['credentials']

        # Prepare headers with Basic Auth
        headers = {
            'Content-Type': 'application/json',
            **urllib3.util.make_headers(basic_auth=credentials)
        }

        # Send POST request to Zendesk
        response = http.request(
            'POST',
            ZENDESK_URL,
            body=json.dumps(ticket_data).encode('utf-8'),
            headers=headers
        )

        if response.status == 201:
            try:
                response_data = json.loads(response.data.decode('utf-8'))
                ticket_id = response_data.get('ticket', {}).get('id')
                logger.info(f"Created Zendesk ticket{f' ID: {ticket_id}' if ticket_id else ''}")
                return True, response_data
            except json.JSONDecodeError:
                logger.error("Failed to parse Zendesk response JSON")
                return True, None
        else:
            logger.error(f"Failed to create Zendesk ticket. Status: {response.status}, Response: {response.data}")
            return False, None

    except Exception as e:
        logger.error(f"Error sending to Zendesk: {e}")
        return False, None

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler function"""
    try:
        # Get and validate body
        body = event.get('body', '')
        if not body:
            return {'statusCode': 400, 'body': json.dumps({'error': 'No form data provided'})}

        # Decode base64 if needed
        if event.get('isBase64Encoded', False):
            try:
                body = base64.b64decode(body).decode('utf-8')
                logger.debug("Decoded base64 encoded body")
            except Exception as e:
                logger.error(f"Failed to decode base64 body: {e}")
                return {'statusCode': 400, 'body': json.dumps({'error': 'Invalid base64 encoding'})}

        # Parse form data
        form_data = dict(urllib.parse.parse_qsl(body, keep_blank_values=True))
        logger.debug(f"Parsed form data: {list(form_data.keys())}")

        # Map and send to Zendesk
        ticket_data = map_form_to_zendesk(form_data)
        success, zendesk_response = send_to_zendesk(ticket_data)

        if success:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'message': 'Form submitted successfully',
                    'zendesk_response': zendesk_response
                })
            }
        else:
            logger.error(f"Form submission failed - Data: {json.dumps(ticket_data)}")
            return {'statusCode': 500, 'body': json.dumps({'error': 'Failed to submit form'})}

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        return {'statusCode': 500, 'body': json.dumps({'error': 'Internal server error'})}
