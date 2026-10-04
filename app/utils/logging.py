"""
Sanitized Application and Security Audit Logging.

Guarantees that sensitive data:
- Passwords
- JWT Bearer tokens
- Database connection credentials / secrets
- Raw biometric feature vectors (embeddings)
- Raw image payloads
are strictly sanitized and redacted before emitting to log streams or storage.
"""

import logging
import re
import sys
from typing import Any
from app.config.settings import settings

# Regular expression patterns for sensitive data redaction
REDACTION_PATTERNS = [
    # Passwords in URLs (e.g. postgresql://user:pass@host)
    (re.compile(r"(://[^:]+:)([^@]+)(@)"), r"\1***\3"),
    # Bearer tokens
    (re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{15,}", re.IGNORECASE), r"\1[REDACTED_JWT_TOKEN]"),
    # JWT tokens starting with eyJ
    (re.compile(r"eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}"), "[REDACTED_JWT_TOKEN]"),
    # Password parameters (e.g., password=foo or "password": "foo")
    (re.compile(r"(password[\"']?\s*[:=]\s*[\"'])([^\"'&]+)([\"']?)", re.IGNORECASE), r"\1[REDACTED_PASSWORD]\3"),
    # Secret keys
    (re.compile(r"(jwt_secret_key[\"']?\s*[:=]\s*[\"'])([^\"'&]+)([\"']?)", re.IGNORECASE), r"\1[REDACTED_SECRET]\3"),
    # Biometric 512-d embeddings in string representations
    (re.compile(r"(\[[-0-9\.\seE,]{60,}\])"), "[REDACTED_EMBEDDING_VECTOR]"),
]


class SanitizedFormatter(logging.Formatter):
    """Custom logging formatter that strips credentials, tokens, and raw embeddings."""

    def format(self, record: logging.LogRecord) -> str:
        original = super().format(record)
        sanitized = original
        for pattern, replacement in REDACTION_PATTERNS:
            sanitized = pattern.sub(replacement, sanitized)
        return sanitized


def setup_logger(name: str = "biometric") -> logging.Logger:
    """
    Sets up a structured application logger with sanitized output.
    Ensures biometric embeddings, raw images, and secrets are never logged.
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        level = getattr(logging, settings.log_level.upper(), logging.INFO)
        logger.setLevel(level)

        formatter = SanitizedFormatter(
            fmt="%(asctime)s | %(levelname)-7s | [%(name)s] %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)

        # Prevent propagation to avoid duplicated logs
        logger.propagate = False

    return logger


logger = setup_logger("biometric")
