import json
import base64
import urllib3
import urllib.parse
import boto3
import logging
import os
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
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
ZENDESK_UPLOADS_URL = "https://donors.zendesk.com/api/v2/uploads.json"


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
FORM_FIELDS = {*FIELD_MAPPINGS, 'tfa_95'}
SCREENSHOT_FIELD = 'tfa_201'
MAX_SCREENSHOT_SIZE_BYTES = 1024 * 1024
SCREENSHOT_EXTENSION_TO_TYPE = {
    '.png': 'image/png',
    '.jpg': 'image/jpeg',
    '.jpeg': 'image/jpeg',
    '.webp': 'image/webp'
}
SCREENSHOT_TYPE_TO_EXTENSION = {
    'image/png': '.png',
    'image/jpeg': '.jpg',
    'image/jpg': '.jpg',
    'image/webp': '.webp'
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


@dataclass
class ScreenshotAttachment:
    filename: str
    content_type: str
    data: bytes


def get_zendesk_headers(content_type: str = 'application/json') -> Dict[str, str]:
    """Build Zendesk auth headers using the configured secret."""
    response = secrets_client.get_secret_value(SecretId="form-bridge/prod/zendesk")
    credentials = json.loads(response['SecretString'])['credentials']
    return {
        'Content-Type': content_type,
        **urllib3.util.make_headers(basic_auth=credentials)
    }


def describe_screenshot_drop(reason: str) -> str:
    """Format a user-visible note when a screenshot was not attached."""
    return f"Screenshot was submitted but dropped: {reason}."


def normalize_screenshot_content_type(filename: str, content_type: str) -> str:
    """Return a supported MIME type using either the provided type or file extension."""
    normalized_content_type = (content_type or '').lower()
    if normalized_content_type in SCREENSHOT_TYPE_TO_EXTENSION:
        return 'image/jpeg' if normalized_content_type == 'image/jpg' else normalized_content_type

    extension = os.path.splitext((filename or '').lower())[1]
    return SCREENSHOT_EXTENSION_TO_TYPE.get(extension, '')


def normalize_screenshot_filename(filename: str, content_type: str) -> str:
    """Return a safe filename with an extension that matches the upload MIME type."""
    base_name = os.path.basename(filename or '').strip() or 'screenshot'
    root, _ = os.path.splitext(base_name)
    extension = SCREENSHOT_TYPE_TO_EXTENSION[normalize_screenshot_content_type(base_name, content_type)]
    return f"{root or 'screenshot'}{extension}"


def upload_screenshot_to_zendesk(screenshot: ScreenshotAttachment) -> tuple[Optional[str], Optional[str]]:
    """Upload a screenshot to Zendesk and return an upload token or a drop reason."""
    content_type = normalize_screenshot_content_type(screenshot.filename, screenshot.content_type)
    if not content_type:
        return None, "unsupported file type"

    if len(screenshot.data) > MAX_SCREENSHOT_SIZE_BYTES:
        return None, "it exceeded the 1 MiB size limit"

    filename = normalize_screenshot_filename(screenshot.filename, content_type)

    try:
        response = http.request(
            'POST',
            f"{ZENDESK_UPLOADS_URL}?filename={urllib.parse.quote(filename)}",
            body=screenshot.data,
            headers=get_zendesk_headers(content_type=content_type)
        )

        if response.status != 201:
            logger.error(f"Failed to upload screenshot to Zendesk. Status: {response.status}, Response: {response.data}")
            return None, "Zendesk upload failed"

        response_data = json.loads(response.data.decode('utf-8'))
        upload_token = response_data.get('upload', {}).get('token')
        if not upload_token:
            logger.error("Zendesk upload response did not include a token")
            return None, "Zendesk upload failed"

        return upload_token, None

    except Exception as e:
        logger.error(f"Error uploading screenshot to Zendesk: {e}")
        return None, "Zendesk upload failed"


def parse_form_data(body: str, headers: Optional[Dict[str, str]], is_base64_encoded: bool) -> tuple[Dict[str, str], Optional[ScreenshotAttachment]]:
    """Parse either urlencoded or multipart form data."""
    try:
        body_bytes = base64.b64decode(body, validate=True) if is_base64_encoded else body.encode('utf-8')
    except Exception as e:
        logger.error(f"Failed to decode base64 body: {e}")
        raise ValueError("Invalid base64 encoding") from e

    headers = {key.lower(): value for key, value in (headers or {}).items()}
    content_type = headers.get('content-type', '')

    if content_type.lower().startswith('multipart/form-data'):
        if "boundary=" not in content_type:
            raise ValueError("Missing multipart boundary")

        message = BytesParser(policy=default).parsebytes(
            (
                f"Content-Type: {content_type}\r\n"
                "MIME-Version: 1.0\r\n"
                "\r\n"
            ).encode('utf-8') + body_bytes
        )

        form_data: Dict[str, str] = {}
        screenshot: Optional[ScreenshotAttachment] = None
        for part in message.iter_parts():
            field_name = part.get_param('name', header='content-disposition')
            if part.get_content_disposition() != 'form-data' or not field_name:
                continue

            if field_name == SCREENSHOT_FIELD and part.get_filename():
                screenshot = ScreenshotAttachment(
                    filename=part.get_filename(),
                    content_type=part.get_content_type(),
                    data=part.get_payload(decode=True) or b''
                )
                continue

            if (
                field_name not in FORM_FIELDS
                or part.get_filename()
            ):
                continue

            payload = part.get_payload(decode=True) or b''
            try:
                form_data[field_name] = payload.decode(part.get_content_charset('utf-8'))
            except UnicodeDecodeError as e:
                logger.error(f"Failed to decode multipart field {field_name}: {e}")
                raise ValueError(f"Invalid multipart field encoding: {field_name}") from e

        return form_data, screenshot

    if content_type and not content_type.lower().startswith('application/x-www-form-urlencoded'):
        raise ValueError(f"Unsupported content type: {content_type}")

    try:
        return dict(urllib.parse.parse_qsl(body_bytes.decode('utf-8'), keep_blank_values=True)), None
    except UnicodeDecodeError as e:
        logger.error(f"Failed to decode urlencoded body as UTF-8: {e}")
        raise ValueError("Invalid URL-encoded form body") from e

def map_form_to_zendesk(
    form_data: Dict[str, str],
    screenshot_drop_note: str = '',
    upload_tokens: Optional[list[str]] = None
) -> Dict[str, Any]:
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
    comment_body = mapped_data.get('comment_body', '').strip() or DEFAULT_COMMENT
    if screenshot_drop_note:
        comment_body = f"{comment_body}\n\n{screenshot_drop_note}"

    comment = {"body": comment_body}
    if upload_tokens:
        comment["uploads"] = upload_tokens

    # Build Zendesk ticket payload
    return {
        "ticket": {
            "subject": final_subject,
            "comment": comment,
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
        # Send POST request to Zendesk
        response = http.request(
            'POST',
            ZENDESK_URL,
            body=json.dumps(ticket_data).encode('utf-8'),
            headers=get_zendesk_headers()
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

        # Parse form data from either urlencoded or multipart requests
        try:
            form_data, screenshot = parse_form_data(
                body=body,
                headers=event.get('headers'),
                is_base64_encoded=event.get('isBase64Encoded', False)
            )
        except ValueError as e:
            return {'statusCode': 400, 'body': json.dumps({'error': str(e)})}

        logger.debug(f"Parsed form data: {list(form_data.keys())}")

        # Don't bother proceeding if we don't even have an email address
        email = form_data.get('tfa_10', '').strip()
        if not email:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Email address is required'})}

        screenshot_drop_note = ''
        upload_tokens = None
        if screenshot:
            upload_token, drop_reason = upload_screenshot_to_zendesk(screenshot)
            if upload_token:
                upload_tokens = [upload_token]
            else:
                screenshot_drop_note = describe_screenshot_drop(drop_reason or "it could not be attached")
                logger.warning(
                    "Dropping screenshot attachment filename=%s content_type=%s size=%s reason=%s",
                    screenshot.filename,
                    screenshot.content_type,
                    len(screenshot.data),
                    drop_reason or "unknown"
                )

        # Map and send to Zendesk
        ticket_data = map_form_to_zendesk(
            form_data,
            screenshot_drop_note=screenshot_drop_note,
            upload_tokens=upload_tokens
        )
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
