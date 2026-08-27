# Copyright (c) 2026, eCentric and contributors
"""Recursive redaction for anything the esign layer logs or persists as event metadata
(NO frappe import). Modeled on alerts/services/omisell_client.sanitize, extended with
signature/PDF payload keys. NEVER store or log: tokens, passwords, signature images,
PDF Base64, callback secrets, HSM identifiers."""

SENSITIVE_KEYS = (
    "token", "refresh_token", "api_key", "api_secret", "authorization", "password",
    "secret", "callback_secret", "signature_image", "signatureimage", "base64",
    "pdfbase64", "originalbase64", "filecontent", "content", "hsm", "certificate_key",
    "cookie", "set-cookie", "session_id", "sid",
)

REDACTED = "***redacted***"
_MAX_STR = 400


def _is_sensitive(key):
    k = str(key).lower()
    return any(s in k for s in SENSITIVE_KEYS)


def sanitize(value, _depth=0):
    """Deep-copy with sensitive keys redacted and long strings truncated. Safe on any
    JSON-ish structure; never raises (falls back to type name)."""
    try:
        if _depth > 8:
            return "***depth***"
        if isinstance(value, dict):
            return {k: (REDACTED if _is_sensitive(k) else sanitize(v, _depth + 1))
                    for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [sanitize(v, _depth + 1) for v in value[:50]]
        if isinstance(value, (bytes, bytearray)):
            return "***bytes:%d***" % len(value)
        if isinstance(value, str):
            if len(value) > _MAX_STR:
                return value[:_MAX_STR] + "...(truncated)"
            return value
        return value
    except Exception:
        return "***unsanitizable:%s***" % type(value).__name__


def safe_error(exc):
    """Exception -> short sanitized string (class + trimmed message, no payloads)."""
    try:
        msg = str(exc)
    except Exception:
        msg = ""
    # 200 was cutting provider validation details in half - the part naming the offending
    # field always comes last. 500 still fits an audit field and never carries payloads,
    # because the provider layer already renders errors compactly.
    if len(msg) > 500:
        msg = msg[:500] + "..."
    low = msg.lower()
    if any(s in low for s in ("bearer", "token", "authorization", "base64", "password")):
        msg = "(message withheld - contained sensitive markers)"
    return "%s: %s" % (type(exc).__name__, msg)
