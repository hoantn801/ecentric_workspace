# Copyright (c) 2026, eCentric and contributors
"""SSRF / provider-URL safety for the SCTS adapter (fail-closed).

The adapter builds request URLs from `settings.base_url` plus a FIXED, code-defined endpoint
path (never a frontend-supplied path). Defences (all fail-closed, frappe-free, testable):
  * literal URL validation (https, no credentials, no private/loopback/metadata host);
  * an app-owned host ALLOWLIST that must be non-empty for SCTS (empty => no request);
  * DNS resolution of the host with rejection of any resolved loopback/private/link-local/
    reserved/multicast address - re-checked immediately BEFORE each request (rebinding-safe).
"""
import ipaddress
import socket
try:
    from urllib.parse import urlsplit
except Exception:  # pragma: no cover
    from urlparse import urlsplit  # type: ignore

_BLOCKED_HOSTNAMES = {"localhost", "localhost.localdomain", "ip6-localhost", "metadata",
                      "metadata.google.internal"}
_ALLOWED_SCHEMES = ("https",)


def _ip_blocked(ip_obj):
    return (ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local
            or ip_obj.is_reserved or ip_obj.is_multicast or ip_obj.is_unspecified)


def _host_is_private_literal(host):
    try:
        return _ip_blocked(ipaddress.ip_address(host))
    except ValueError:
        return False


def _norm_allow(allow_hosts):
    if not allow_hosts:
        return set()
    if isinstance(allow_hosts, str):
        allow_hosts = allow_hosts.replace(",", "\n").splitlines()
    return {h.strip().lower() for h in allow_hosts if h and h.strip()}


def validate_base_url(base_url, allow_hosts=None, require_https=True, require_allowlist=False):
    """Return (ok, reason). Literal (non-DNS) checks. When require_allowlist is True an empty
    allowlist fails closed (used for SCTS)."""
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
    allowed = _norm_allow(allow_hosts)
    if require_allowlist and not allowed:
        return False, "empty_allowlist_fail_closed"
    if allowed and host not in allowed:
        return False, "host_not_in_allowlist"
    return True, "ok"


def resolve_and_validate(host, resolver=None):
    """Resolve `host` and reject if ANY resolved address is loopback/private/link-local/
    reserved/multicast/unspecified. `resolver(host)` -> iterable of IP strings (injectable
    for tests); defaults to socket.getaddrinfo. Returns (ok, reason, ips)."""
    host = str(host or "").strip().lower()
    if not host:
        return False, "empty_host", []
    # a literal IP is validated directly (no DNS)
    try:
        ip = ipaddress.ip_address(host)
        return (False, "private_or_loopback_ip", [host]) if _ip_blocked(ip) else (True, "ok", [host])
    except ValueError:
        pass
    try:
        if resolver is None:
            infos = socket.getaddrinfo(host, None)
            ips = sorted({str(i[4][0]) for i in infos})
        else:
            ips = sorted({str(x) for x in resolver(host)})
    except Exception as e:
        return False, "dns_resolution_failed:%s" % type(e).__name__, []
    if not ips:
        return False, "no_addresses", []
    for ip in ips:
        try:
            if _ip_blocked(ipaddress.ip_address(ip)):
                return False, "resolves_to_blocked:%s" % ip, ips
        except ValueError:
            return False, "unparseable_address:%s" % ip, ips
    return True, "ok", ips


def assert_request_allowed(base_url, allow_hosts, resolver=None, require_https=True):
    """Fail-closed pre-request gate for SCTS: non-empty allowlist + literal checks + DNS
    resolution validation. Raises ValueError (callers convert to ProviderError). This is
    called immediately before EACH request so DNS-rebinding cannot slip a private address in."""
    ok, reason = validate_base_url(base_url, allow_hosts=allow_hosts,
                                   require_https=require_https, require_allowlist=True)
    if not ok:
        raise ValueError("unsafe_base_url:%s" % reason)
    host = urlsplit(str(base_url).strip()).hostname
    rok, rreason, _ips = resolve_and_validate(host, resolver=resolver)
    if not rok:
        raise ValueError("unsafe_base_url:%s" % rreason)
    return True


def assert_base_url_safe(base_url, allow_hosts=None, require_https=True, require_allowlist=False):
    ok, reason = validate_base_url(base_url, allow_hosts=allow_hosts,
                                   require_https=require_https, require_allowlist=require_allowlist)
    if not ok:
        raise ValueError("unsafe_base_url:%s" % reason)
    return True


def safe_join(base_url, path):
    p = str(path or "")
    if "://" in p or p.startswith("//"):
        raise ValueError("absolute_path_override")
    if ".." in p.split("/"):
        raise ValueError("path_traversal")
    return "%s/%s" % (str(base_url).rstrip("/"), p.lstrip("/"))
