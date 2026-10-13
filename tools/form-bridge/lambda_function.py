import json
import base64
import binascii
from dataclasses import dataclass
from email.parser import BytesParser
from email.policy import default
import hmac
import ipaddress
import os
import time
import urllib3
import urllib.parse
import boto3
from botocore.exceptions import ClientError
import logging
from typing import Dict, Any, Optional
import uuid

import abuse
import rate_limit

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

# FormAssembly's published US connector egress addresses (2026-10-13).
# https://help.formassembly.com/help/ip-whitelisting-for-formassembly
# Override for another hosting region or a change to FormAssembly's addresses.
FORMASSEMBLY_TRUSTED_IPS = frozenset(
    address.strip() for address in os.environ.get(
        'FORMASSEMBLY_TRUSTED_IPS',
        '34.230.105.243,18.221.37.214,35.169.15.41,34.231.230.11,18.217.101.3,18.217.15.195'
    ).split(',') if address.strip()
)
FORMASSEMBLY_AUTH_SECRET_ID = os.environ.get('FORMASSEMBLY_AUTH_SECRET_ID', '')
_connector_auth_cache = {'secret_id': None, 'credentials': None, 'expires_at': 0.0}
ZENDESK_SUBMITTER_IP_FIELD_ID = os.environ.get('ZENDESK_SUBMITTER_IP_FIELD_ID', '')


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


def normalize_ip(value: str) -> Optional[str]:
    """Accept one IPv4/IPv6 address, without a port, scope, or proxy chain."""
    value = value.strip()
    if '%' in value:
        return None
    try:
        address = ipaddress.ip_address(value)
        # IPv4-mapped IPv6 and plain IPv4 must share one allowance.
        return str(address.ipv4_mapped or address) if address.version == 6 else str(address)
    except ValueError:
        return None


def get_connector_credentials() -> bytes:
    """Cache the connector credential briefly so invalid requests cannot force a secret read each time."""
    now = time.monotonic()
    if (_connector_auth_cache['secret_id'] == FORMASSEMBLY_AUTH_SECRET_ID
            and now < _connector_auth_cache['expires_at']):
        return _connector_auth_cache['credentials']

    response = secrets_client.get_secret_value(SecretId=FORMASSEMBLY_AUTH_SECRET_ID)
    secret = json.loads(response['SecretString'])
    username, password = secret['username'], secret['password']
    if not isinstance(username, str) or not username or ':' in username or not isinstance(password, str) or not password:
        raise ValueError('Invalid FormAssembly credential configuration')
    credentials = f'{username}:{password}'.encode('utf-8')
    _connector_auth_cache.update(
        secret_id=FORMASSEMBLY_AUTH_SECRET_ID,
        credentials=credentials,
        expires_at=now + 300,
    )
    return credentials


def connector_authenticated(event: Dict[str, Any]) -> bool:
    """Authenticate the server-side FormAssembly HTTPS connector."""
    headers = event.get('headers') or {}
    authorization = next(
        (value for key, value in headers.items() if key.lower() == 'authorization'), ''
    )
    if not isinstance(authorization, str) or len(authorization) > 4096:
        return False
    scheme, separator, token = authorization.partition(' ')
    if scheme.lower() != 'basic' or not separator:
        return False
    try:
        supplied = base64.b64decode(token, validate=True)
    except (ValueError, binascii.Error):
        return False
    return hmac.compare_digest(supplied, get_connector_credentials())


def get_request_metadata(event: Dict[str, Any], context: Any,
                         form_data: Optional[Dict[str, str]] = None,
                         connector_verified: bool = False) -> Dict[str, Any]:
    """Keep the observed connection IP separate from FormAssembly's respondent IP."""
    request_context = event.get('requestContext') or {}
    connection_ip = normalize_ip((request_context.get('http') or {}).get('sourceIp', ''))
    metadata = {
        'event': 'donor_form_submission',
        'request_id': getattr(context, 'aws_request_id', None) or request_context.get('requestId'),
        'connection_ip': connection_ip,
        'submitter_ip': None,
        'submitter_ip_status': 'missing',
    }
    forwarded_ip = (form_data or {}).get('submitter_ip', '').strip()
    if not forwarded_ip:
        return metadata
    if not connector_verified and connection_ip not in FORMASSEMBLY_TRUSTED_IPS:
        metadata['submitter_ip_status'] = 'untrusted_source'
        return metadata
    submitter_ip = normalize_ip(forwarded_ip)
    if submitter_ip is None:
        metadata['submitter_ip_status'] = 'invalid'
        return metadata
    metadata.update(submitter_ip=submitter_ip, submitter_ip_status='forwarded')
    return metadata


def get_rate_limit_ip(metadata: Dict[str, Any]) -> Optional[str]:
    if metadata['submitter_ip']:
        return metadata['submitter_ip']
    if FORMASSEMBLY_AUTH_SECRET_ID:
        # An authenticated connector must provide an individual submitter IP.
        return None
    connection_ip = metadata['connection_ip']
    # Direct callers can be limited by their observed address. Never share
    # an allowance across everyone behind a FormAssembly connector.
    if connection_ip and connection_ip not in FORMASSEMBLY_TRUSTED_IPS:
        return connection_ip
    return None


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
            headers=get_zendesk_headers(content_type=content_type),
            retries=False,
            redirect=False,
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
        message = BytesParser(policy=default).parsebytes(
            (
                f"Content-Type: {content_type}\r\n"
                "MIME-Version: 1.0\r\n"
                "\r\n"
            ).encode('utf-8') + body_bytes
        )
        if not message.get_boundary():
            raise ValueError('Missing multipart boundary')
        if not message.is_multipart() or message.defects:
            raise ValueError('Invalid multipart body')

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

            if part.get_filename():
                continue

            payload = part.get_payload(decode=True) or b''
            try:
                form_data[field_name] = payload.decode(part.get_content_charset('utf-8'))
            except (LookupError, UnicodeDecodeError) as e:
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


def map_form_to_zendesk(form_data: Dict[str, str],
                        request_metadata: Optional[Dict[str, Any]] = None,
                        screenshot_drop_note: str = '',
                        upload_tokens: Optional[list[str]] = None) -> Dict[str, Any]:
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
        comment_body = f'{comment_body}\n\n{screenshot_drop_note}'
    comment = {'body': comment_body}
    if upload_tokens:
        comment['uploads'] = upload_tokens

    # Build Zendesk ticket payload
    ticket_data = {
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
    if request_metadata and request_metadata.get('submitter_ip'):
        # Zendesk's system audit IP is read-only. Store the respondent's IP
        # separately; never put it in the public comment or overwrite that IP.
        ticket_data['ticket']['metadata'] = {
            'submitter_ip': request_metadata['submitter_ip'],
            'submitter_ip_source': 'formassembly',
            'lambda_request_id': request_metadata['request_id'],
        }
        if ZENDESK_SUBMITTER_IP_FIELD_ID.isdecimal():
            ticket_data['ticket']['custom_fields'] = [{
                'id': int(ZENDESK_SUBMITTER_IP_FIELD_ID),
                'value': request_metadata['submitter_ip'],
            }]
    return ticket_data

def send_to_zendesk(ticket_data: Dict[str, Any], request_id: Optional[str] = None) -> tuple[bool, Optional[Dict[str, Any]]]:
    """Send ticket data to Zendesk API"""
    try:
        headers = get_zendesk_headers()
        headers['Idempotency-Key'] = request_id or str(uuid.uuid4())
        # Send POST request to Zendesk
        response = http.request(
            'POST',
            ZENDESK_URL,
            body=json.dumps(ticket_data).encode('utf-8'),
            headers=headers,
            retries=False,
            redirect=False,
        )

        if response.status == 201:
            try:
                response_data = json.loads(response.data.decode('utf-8'))
                ticket_id = response_data.get('ticket', {}).get('id')
                logger.info(f"Created Zendesk ticket{f' ID: {ticket_id}' if ticket_id else ''}")
                return True, response_data
            except (ValueError, AttributeError, TypeError):
                logger.error("Zendesk created the ticket but returned an unreadable response")
                return True, None
        else:
            logger.error(f"Failed to create Zendesk ticket. Status: {response.status}, Response: {response.data}")
            return False, None

    except Exception as e:
        logger.error(f"Error sending to Zendesk: {e}")
        return False, None

def lambda_handler(event: Dict[str, Any], context: Any) -> Dict[str, Any]:
    """Main Lambda handler function"""
    request_metadata = get_request_metadata(event, context)
    request_id = request_metadata['request_id'] or str(uuid.uuid4())
    request_metadata['request_id'] = request_id
    rate_limit_key = None
    try:
        connector_verified = False
        if FORMASSEMBLY_AUTH_SECRET_ID:
            try:
                connector_verified = connector_authenticated(event)
            except Exception:
                logger.exception('Unable to authenticate FormAssembly connector')
                request_metadata['auth_status'] = 'error'
                return {'statusCode': 503, 'body': json.dumps({'error': 'Unable to process submission; please retry'})}
            if not connector_verified:
                request_metadata['auth_status'] = 'rejected'
                return {
                    'statusCode': 401,
                    'headers': {'WWW-Authenticate': 'Basic realm="donor-form"'},
                    'body': json.dumps({'error': 'Unauthorized'}),
                }
            request_metadata['auth_status'] = 'authenticated'

        # Get and validate body
        body = event.get('body', '')
        if not body:
            return {'statusCode': 400, 'body': json.dumps({'error': 'No form data provided'})}

        try:
            form_data, screenshot = parse_form_data(
                body, event.get('headers'), event.get('isBase64Encoded', False)
            )
        except ValueError as error:
            return {'statusCode': 400, 'body': json.dumps({'error': str(error)})}
        request_metadata = get_request_metadata(
            event, context, form_data, connector_verified=connector_verified
        )
        request_metadata['request_id'] = request_id
        if FORMASSEMBLY_AUTH_SECRET_ID:
            request_metadata['auth_status'] = 'authenticated'
        logger.debug(f"Parsed form data: {list(form_data.keys())}")

        abuse_rule = abuse.match_rule(form_data)
        if abuse_rule:
            request_metadata.update(
                outcome='blocked',
                block_reason='known_abuse_signature',
                block_rule=abuse_rule,
            )
            # Acknowledge delivery so the connector does not retry the spam.
            # Do not create a ticket or disclose the matching rule to the sender.
            return {
                'statusCode': 200,
                'body': json.dumps({'message': 'Form submitted successfully'}),
            }

        # Don't bother proceeding if we don't even have an email address
        email = form_data.get('tfa_10', '').strip()
        if not email:
            return {'statusCode': 400, 'body': json.dumps({'error': 'Email address is required'})}

        if rate_limit.TABLE_NAME:
            submitter_ip = get_rate_limit_ip(request_metadata)
            if not submitter_ip:
                request_metadata['rate_limit_status'] = 'missing_ip'
                return {'statusCode': 503, 'body': json.dumps({'error': 'Unable to identify submitter IP'})}
            try:
                rate_limit_key = rate_limit.check(submitter_ip)
                request_metadata['rate_limit_status'] = 'allowed'
            except rate_limit.RateLimitExceeded as error:
                request_metadata.update(
                    outcome='blocked', block_reason='ip_rate_limit',
                    rate_limit_status='limited', retry_after=error.retry_after,
                )
                return {
                    'statusCode': 429,
                    'headers': {'Retry-After': str(error.retry_after)},
                    'body': json.dumps({'error': str(error)}),
                }
            except Exception:
                logger.exception('Failed to check donor submission allowance')
                request_metadata['rate_limit_status'] = 'error'
                return {'statusCode': 503, 'body': json.dumps({'error': 'Unable to process submission; please retry'})}

        screenshot_drop_note = ''
        upload_tokens = None
        if screenshot:
            upload_token, drop_reason = upload_screenshot_to_zendesk(screenshot)
            if upload_token:
                upload_tokens = [upload_token]
            else:
                screenshot_drop_note = describe_screenshot_drop(drop_reason or "it could not be attached")
                logger.warning("Dropping screenshot attachment size=%s reason=%s",
                               len(screenshot.data), drop_reason or "unknown")

        # Map and send to Zendesk
        ticket_data = map_form_to_zendesk(
            form_data, request_metadata,
            screenshot_drop_note=screenshot_drop_note, upload_tokens=upload_tokens,
        )
        success, zendesk_response = send_to_zendesk(
            ticket_data, request_id=request_metadata['request_id'],
        )

        if success:
            if rate_limit_key is not None:
                try:
                    rate_limit.record_success(rate_limit_key, request_id)
                    request_metadata['rate_limit_status'] = 'recorded'
                except Exception:
                    # The ticket exists; do not ask the donor to send it again.
                    logger.exception('Failed to record successful donor submission')
                    request_metadata['rate_limit_status'] = 'error'
            request_metadata['zendesk_ticket_id'] = (zendesk_response or {}).get('ticket', {}).get('id')
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
    finally:
        # CloudTrail records the immediate caller, not a forwarded form field.
        # Log only request metadata here, including on failed submissions.
        logger.info(json.dumps(request_metadata))
