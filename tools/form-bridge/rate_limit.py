"""Limit submissions by recording each IP only after successful delivery."""

import hashlib
import ipaddress
import os
import time

import boto3

WINDOW_SECONDS = 12 * 60 * 60
TABLE_NAME = os.environ.get('DONOR_RATE_LIMIT_TABLE', '')
client = boto3.client('dynamodb', region_name='us-east-2')


class RateLimitExceeded(Exception):
    def __init__(self, retry_after: int):
        self.retry_after = retry_after
        super().__init__('One submission per IP address is allowed every 12 hours')


def check(ip: str) -> str:
    """Check the last successful submission without reserving an allowance."""
    now = int(time.time())
    address = ipaddress.ip_address(ip)
    if address.version == 6:
        address = address.ipv4_mapped or ipaddress.ip_network(f'{address}/64', strict=False)
    ip_key = hashlib.sha256(str(address).encode('utf-8')).hexdigest()
    response = client.get_item(
        TableName=TABLE_NAME,
        Key={'ip_key': {'S': ip_key}},
        ConsistentRead=True,
    )
    expires_at = int(response.get('Item', {}).get('expires_at', {}).get('N', '0'))
    if expires_at > now:
        raise RateLimitExceeded(expires_at - now)
    return ip_key


def record_success(ip_key: str, request_id: str) -> None:
    """Start the 12-hour window only once Zendesk has accepted the ticket."""
    client.put_item(
        TableName=TABLE_NAME,
        Item={
            'ip_key': {'S': ip_key},
            'request_id': {'S': request_id},
            'expires_at': {'N': str(int(time.time()) + WINDOW_SECONDS)},
        },
    )
