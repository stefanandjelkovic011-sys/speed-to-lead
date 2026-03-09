"""
Input validation for Speed-to-Lead system.
"""

import re

VALID_PLATFORMS = [
    "google_lsa", "yelp", "thumbtack", "angi",
    "chat_widget", "contact_form", "duke_energy",
    "test", "test_simulation",
]


def validate_phone(phone):
    if not phone:
        return None
    digits = re.sub(r'\D', '', phone)
    if len(digits) < 7 or len(digits) > 15:
        return None
    return digits


def validate_email(email):
    if not email:
        return None
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if re.match(pattern, email):
        return email.strip().lower()
    return None


def validate_platform(platform):
    if platform and platform.strip().lower() in VALID_PLATFORMS:
        return platform.strip().lower()
    return None


def sanitize_message(message):
    if not message:
        return ""
    message = message.strip()
    if len(message) > 5000:
        message = message[:5000]
    return message
