"""Editable phrase rules applied to every string field in a submission."""

import json
import logging
import os
from pathlib import Path
import unicodedata
from typing import Any, Mapping, Optional

logger = logging.getLogger(__name__)


def normalize_text(value: str) -> str:
    return ''.join(
        char for char in unicodedata.normalize('NFKC', value).casefold()
        if char.isalnum()
    )


def load_rules() -> list[list[str]]:
    """A string is one rule; a list requires all phrases in the same field."""
    try:
        configured = os.environ.get('DONOR_ABUSE_SIGNATURES')
        if configured is None:
            configured = Path(__file__).with_name('blocked_strings.json').read_text(encoding='utf-8')
        groups = json.loads(configured)
        if not isinstance(groups, list):
            raise ValueError('Expected a list of rules')
        rules = []
        for group in groups:
            phrases = [group] if isinstance(group, str) else group
            if not isinstance(phrases, list) or not phrases:
                raise ValueError('Expected a string or nonempty phrase group')
            if any(not isinstance(phrase, str) for phrase in phrases):
                raise ValueError('Expected string phrases')
            normalized = [normalize_text(phrase) for phrase in phrases]
            if not all(normalized):
                raise ValueError('Expected nonempty normalized phrases')
            rules.append(normalized)
        return rules
    except (OSError, ValueError, TypeError):
        logger.error('Invalid abuse rules; content filter disabled')
        return []


RULES = load_rules()


def match_rule(form_data: Mapping[str, Any]) -> Optional[str]:
    for value in form_data.values():
        if not isinstance(value, str):
            continue
        normalized = normalize_text(value)
        for index, phrases in enumerate(RULES, start=1):
            if all(phrase in normalized for phrase in phrases):
                return f'donor-abuse-{index}'
    return None
