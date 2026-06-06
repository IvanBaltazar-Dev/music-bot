"""Helpers de seguridad para logs, errores y verificacion de webhooks."""

from __future__ import annotations

import hashlib
import hmac
import re


_JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b")
_BEARER_RE = re.compile(r"Bearer\s+[A-Za-z0-9._~+/=-]+", re.IGNORECASE)
_LONG_SECRET_RE = re.compile(r"\b[A-Za-z0-9_./+=-]{32,}\b")


def mask_identifier(value: str, *, visible: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if len(text) <= visible:
        return "*" * len(text)
    return f"{'*' * (len(text) - visible)}{text[-visible:]}"


def sanitize_text(value: object, *, limit: int = 300) -> str:
    text = str(value or "")
    text = _BEARER_RE.sub("Bearer [REDACTED]", text)
    text = _JWT_RE.sub("[REDACTED_JWT]", text)
    text = _LONG_SECRET_RE.sub("[REDACTED]", text)
    return text[:limit]


def safe_exception(exc: BaseException, *, include_message: bool = False) -> str:
    if include_message:
        return f"{exc.__class__.__name__}: {sanitize_text(exc)}"
    return exc.__class__.__name__


def constant_time_equals(left: str | None, right: str | None) -> bool:
    return hmac.compare_digest(str(left or ""), str(right or ""))


def verify_meta_signature(raw_body: bytes, signature_header: str, app_secret: str) -> bool:
    if not app_secret:
        return True
    if not signature_header or not signature_header.startswith("sha256="):
        return False

    expected = "sha256=" + hmac.new(
        app_secret.encode("utf-8"),
        raw_body,
        hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
