# Copyright (c) 2026, eCentric and contributors
"""SSRF / provider-URL safety for the SCTS adapter (fail-closed).

The adapter builds request URLs from `settings.base_url` plus a FIXED, code-defined
endpoint path (never a frontend-supplied path). The residual risk is a mis- or
maliciously-configured base_url pointing at an internal service, or one that disables TLS
verification. These helpers are frappe-free and deterministic so they can be unit-tested.
"""
import ipaddress
try:
    from urllib.parse import urlsplit
except Exception:  # pragma: no cover
    from urlparse import urlsplit  # type: ignore

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "metadata",
                      "metadata.google.internal"}
_ALLOWED_SCHEMES = ("https",)


def _host_is_private_literal(host):
    """True if host is an IP literal in a loopback/private/link-local/reserved range."""
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    return (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified)


def validate_base_url(base_url, allow_hosts=None, require_https=True):
    """Return (ok, reason). Fail-closed rules:
      * must parse with a scheme + host;
      * scheme must be https (unless require_https=False for an explicit local UAT bench);
      * no embedded credentials (user:pass@host);
      * host must not be a loopback/private/link-local IP literal or a blocked hostname;
      * if allow_hosts is a non-empty set, the host must be in it (exact, case-insensitive).
    `allow_hosts` lets an operator pin the exact SCTS UAT/Prod hostnames."""
    if not base_url or not str(base_url).strip():
        return False, "empty_base_url"
    parts = urlsplit(str(base_url).strip())
    if not parts.scheme or not parts.hostname:
        return False, "malformed_url"
    if require_https and parts.scheme.lower() not in _ALLOWED_SCHEMES:
        return False, "scheme_not_https"
    if parts.username or parts.password:
        return False, "embedded_credentials"
    host = parts.hostname.lower()
    if host in _BLOCKED_HOSTNAMES:
        return False, "blocked_hostname"
    if _host_is_private_literal(host):
        return False, "private_or_loopback_host"
    if allow_hosts:
        allowed = {h.strip().lower() for h in allow_hosts if h and h.strip()}
        if allowed and host not in allowed:
            return False, "host_not_in_allowlist"
    return True, "ok"


def assert_base_url_safe(base_url, allow_hosts=None, require_https=True):
    """Raise ValueError on an unsafe base_url (adapter/settings callers convert to
    ProviderError so nothing above the adapter boundary sees provider internals)."""
    ok, reason = validate_base_url(base_url, allow_hosts=allow_hosts,
                                   require_https=require_https)
    if not ok:
        raise ValueError("unsafe_base_url:%s" % reason)
    return True


def safe_join(base_url, path):
    """Join a FIXED code path onto base_url, refusing absolute overrides and traversal.
    The path must be a relative, code-defined endpoint (e.g. '/api/AddDocument')."""
    p = str(path or "")
    if "://" in p or p.startswith("//"):
        raise ValueError("absolute_path_override")
    if ".." in p.split("/"):
        raise ValueError("path_traversal")
    return "%s/%s" % (str(base_url).rstrip("/"), p.lstrip("/"))
