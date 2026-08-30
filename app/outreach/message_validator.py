import os
import re
import logging
from typing import Tuple, List

logger = logging.getLogger(__name__)

TELEGRAM_MAX_MESSAGE_LENGTH = 4096

# Common template placeholders that must be filled
UNFILLED_PLACEHOLDER_PATTERN = re.compile(r'\{[a-zA-Z_]+\}')

# Basic URL validation
MALFORMED_URL_PATTERN = re.compile(r'https?://[\s<>"\']|https?://$|https?://\s')
URL_PATTERN = re.compile(r'https?://[^\s]+')


def validate_message(message_text: str, media_paths: list = None) -> Tuple[bool, List[str]]:
    """
    Validate outreach message before dispatch.
    
    Checks:
    1. Message is not empty or whitespace-only
    2. Message length <= 4096 characters
    3. No unfilled template placeholders like {name}, {channel}
    4. No malformed URLs (http:// followed by space, etc.)
    5. Message contains actual content (not just links/whitespace)
    6. Media paths exist if specified (check os.path.exists)
    
    Returns:
        Tuple of (is_valid, list_of_error_strings)
    """
    errors = []
    
    if not message_text or not message_text.strip():
        errors.append("Message is empty or whitespace-only.")
    else:
        if len(message_text) > TELEGRAM_MAX_MESSAGE_LENGTH:
            errors.append(f"Message length exceeds {TELEGRAM_MAX_MESSAGE_LENGTH} characters.")
        
        if UNFILLED_PLACEHOLDER_PATTERN.search(message_text):
            errors.append("Message contains unfilled template placeholders.")
        
        if MALFORMED_URL_PATTERN.search(message_text):
            errors.append("Message contains malformed URLs.")
            
        # Check if content remains after stripping out valid URLs
        content_without_urls = URL_PATTERN.sub('', message_text).strip()
        if not content_without_urls:
            errors.append("Message contains no actual content (only links/whitespace).")
            
    if media_paths:
        for path in media_paths:
            if not os.path.exists(path):
                errors.append(f"Media path does not exist: {path}")
                
    return len(errors) == 0, errors
