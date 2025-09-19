import json
import urllib3
import urllib.parse
import boto3
from botocore.exceptions import ClientError
import logging
from typing import Dict, Any, Optional

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize HTTP client
http = urllib3.PoolManager()

# Initialize AWS Secrets Manager client
secrets_client = boto3.client('secretsmanager', region_name='us-east-2')

def map_form_to_zendesk(form_data: Dict[str, str]) -> Dict[str, Any]:
    """Map form fields to Zendesk ticket format"""
    # Field mappings as specified
    field_mappings = {
        'tfa_211': 'subject',
        'tfa_163': 'comment_body',
        'tfa_1': 'name',
        'tfa_10': 'email'
    }

    # Dropdown option mappings for tfa_95
    dropdown_options = {
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

    mapped_data = {}
    for form_field, zendesk_field in field_mappings.items():
        if form_field in form_data:
            mapped_data[zendesk_field] = form_data[form_field]

    # Handle dropdown selection (tfa_95) and prepend to subject
    dropdown_selection = form_data.get('tfa_95', '')
    dropdown_text = dropdown_options.get(dropdown_selection, '')

    # Build subject with dropdown prefix
    user_subject = mapped_data.get('subject', 'Form Submission')
    if dropdown_text:
        final_subject = f"{dropdown_text} - {user_subject}"
    else:
        final_subject = user_subject

    # Build Zendesk ticket payload
    ticket_data = {
        "ticket": {
            "subject": final_subject,
            "comment": {
                "body": mapped_data.get('comment_body', 'No comment provided')
            },
            "requester": {
                "name": mapped_data.get('name', 'Anonymous'),
                "email": mapped_data.get('email', 'noreply@thunderbird.net')
            },
            "brand_id": 43075490201747
        }
    }

    return ticket_data

def send_to_zendesk(ticket_data: Dict[str, Any]) -> tuple[bool, Optional[Dict[str, Any]]]:
    """Send ticket data to Zendesk API"""
    zendesk_url = "https://donors.zendesk.com/api/v2/tickets.json"

    # Get Zendesk configuration from AWS Secrets Manager
    # Secret: donor-form-bridge/prod/zendesk contains {"credentials": "email/token:api_token"}
    response = secrets_client.get_secret_value(SecretId="form-bridge/prod/zendesk")
    zendesk_config = json.loads(response['SecretString'])

    # Prepare Basic Auth credentials using urllib3 helper
    credentials = zendesk_config['credentials']  # Format: email/token:api_token
    username, password = credentials.split(':', 1)

    # Use urllib3's make_headers for Basic Auth
    auth_headers = urllib3.util.make_headers(basic_auth=f"{username}:{password}")
    headers = {
        'Content-Type': 'application/json',
        **auth_headers
    }

    try:
        # Send POST request to Zendesk
        response = http.request(
            'POST',
            zendesk_url,
            body=json.dumps(ticket_data).encode('utf-8'),
            headers=headers
        )

        if response.status == 201:
            # Parse and return the JSON response
            try:
                response_data = json.loads(response.data.decode('utf-8'))
                ticket_id = response_data.get('ticket', {}).get('id')
                if ticket_id:
                    logger.info(f"Created Zendesk ticket ID: {ticket_id}")
                else:
                    logger.info("Successfully created Zendesk ticket (no ID in response)")
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
    is_base64 = event.get('isBase64Encoded', False)
    logger.debug(f"Received event - isBase64Encoded: {is_base64}")
    logger.debug(f"Full event: {json.dumps(event)}")

    try:
        # Parse the incoming request
        body = event.get('body', '')

        # Parse form data
        if not body:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': 'No form data provided'})
            }

        # Decode base64 body if needed
        if event.get('isBase64Encoded', False):
            import base64
            try:
                body = base64.b64decode(body).decode('utf-8')
                logger.debug("Decoded base64 encoded body")
            except Exception as e:
                logger.error(f"Failed to decode base64 body: {e}")

        # Parse form data
        form_data = dict(urllib.parse.parse_qsl(body, keep_blank_values=True))

        # Map form data to Zendesk format
        ticket_data = map_form_to_zendesk(form_data)

        # Send to Zendesk
        success, zendesk_response = send_to_zendesk(ticket_data)

        if success:
            response_body = {
                'message': 'Form submitted successfully',
                'zendesk_response': zendesk_response
            }
            return {
                'statusCode': 200,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps(response_body)
            }
        else:
            # Log data for debugging on failure
            logger.error(f"Form submission failed - Parsed form data: {form_data}")
            logger.error(f"Form submission failed - Mapped ticket data: {json.dumps(ticket_data)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({'error': 'Failed to submit form'})
            }

    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        # Log form data for debugging if available
        try:
            form_data = dict(urllib.parse.parse_qsl(body, keep_blank_values=True))
            logger.error(f"Exception occurred - Parsed form data: {form_data}")
        except:
            logger.error(f"Exception occurred - Raw body: {body[:200]}...")  # First 200 chars

        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({'error': 'Internal server error'})
        }
