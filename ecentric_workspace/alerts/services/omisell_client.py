"""Omisell HTTP client - READ-ONLY BY CONSTRUCTION (Phase D).

This is the ONLY module in alerts/ allowed to import an HTTP library.
Hard guarantees (user directive 2026-06-08):
  * Single `_request()` chokepoint. ALLOWED_METHODS = {"GET"} (frozen).
  * The ONLY permitted POST is the authentication/token request, matched
    against an explicit auth-path allowlist. PATCH/PUT/DELETE always refused.
  * No mutation function exists in this module (enforced by test_phase_d
    introspection + pre-merge grep gate).
  * Everything returned or logged passes _sanitize() - tokens / keys /
    Authorization material never leave this module.
  * Rate limits respected: <=1 req/sec pacing, X-Omisell-Api-Call-Limit
    header watched (slow down above 70/100), 429 -> backoff 30/60/120s.

Auth (official docs developers.omisell.com/doc-400887): API key (created in
app.omisell.com) exchanged for {token, expired_time, refresh_token}; requests
carry `Authorization: Omi <token>`; token expires ~daily. Exact auth path/body
key are confirmed at T0 - both configurable via site_config without redeploy:
  ec_alerts_omisell_auth_path   (default /api/v2/auth/token/get/ - official)
  ec_alerts_omisell_auth_scheme (default Omi; set "Account" to send a static
                                 account key with no token exchange)
Auth body (confirmed): JSON {"api_key": ..., "api_secret": ...} - BOTH from
EC Brand Integration Settings; either missing -> clean OmisellAuthError.
"""
import json
import time
from datetime import datetime

import frappe
import requests
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

ALLOWED_METHODS = frozenset({"GET"})
DEFAULT_BASE = "https://api.omisell.com"
DEFAULT_AUTH_PATH = "/api/v2/auth/token/get/"  # confirmed from official docs code sample
RATE_HEADER = "X-Omisell-Api-Call-Limit"
THROTTLE_AT = 70          # of bucket 100
MIN_INTERVAL = 1.0        # seconds between calls (<=1 req/sec)
BACKOFFS = (30, 60, 120)  # seconds, on HTTP 429
BACKOFFS_5XX = (5, 15)    # bounded retry on Omisell server errors (hardening 2026-06-10)
BACKOFFS_TIMEOUT = (2, 5)  # read/connect timeout retry, GET ONLY (hotfix 2026-06-12)
# Hotfix A 2026-06-13 (LOF auth-POST zero-retry incident): the idempotent auth
# token exchange gets its OWN bounded transient retry (timeout / connection /
# 429 / 5xx) - NEVER for 400/401/403 credential rejection. 3 total attempts,
# backoff 1s then 3s. Distinct from the long order 429 backoff (30/60/120).
AUTH_MAX_ATTEMPTS = 3          # total tries incl. the first
AUTH_BACKOFFS = (1, 3)        # seconds between the (<=2) retries
DEFAULT_TOKEN_TTL_MIN = 30    # fallback token lifetime when Omisell omits expired_time
# Hotfix 2026-06-12 (LOF repeated read timeouts at 30s): default read timeout
# raised to 60s, tunable via site_config ec_alerts_omisell_read_timeout
# (clamped 10..180). NOTE: TIMEOUT constant kept as fallback floor.
DEFAULT_READ_TIMEOUT = 60
TIMEOUT = 30  # legacy fallback floor - do not lower DEFAULT below this


def token_ttl_minutes():
    """Fallback token lifetime (minutes) when Omisell omits expired_time.
    site_config ec_alerts_omisell_token_ttl_minutes; fail-safe 30."""
    try:
        v = frappe.conf.get("ec_alerts_omisell_token_ttl_minutes")
        if v in (None, ""):
            return DEFAULT_TOKEN_TTL_MIN
        return max(1, int(float(v)))
    except Exception:
        return DEFAULT_TOKEN_TTL_MIN


def read_timeout():
    """Effective per-request read timeout (seconds). site_config override,
    fail-safe to DEFAULT_READ_TIMEOUT."""
    try:
        v = frappe.conf.get("ec_alerts_omisell_read_timeout")
        if v in (None, ""):
            return DEFAULT_READ_TIMEOUT
        return max(10, min(int(float(v)), 180))
    except Exception:
        return DEFAULT_READ_TIMEOUT

SENSITIVE_KEYS = ("token", "refresh_token", "api_key", "api_secret",
                  "authorization", "password", "secret")


class OmisellError(frappe.ValidationError):
    pass


class OmisellAuthError(OmisellError):
    pass


def sanitize(obj):
    """Recursively strip credential material from any structure before it is
    returned, stored or logged."""
    if isinstance(obj, dict):
        return {k: ("***" if str(k).lower() in SENSITIVE_KEYS else sanitize(v))
                for k, v in obj.items()}
    if isinstance(obj, list):
        return [sanitize(x) for x in obj]
    return obj


class OmisellClient:
    """One client per EC Brand Integration Settings record (per brand).
    No cross-brand credential reuse is possible by design."""

    def __init__(self, bis_name):
        self.bis = frappe.get_doc("EC Brand Integration Settings", bis_name)
        self.base = (self.bis.base_url or DEFAULT_BASE).rstrip("/")
        self.last_rate_header = None
        self._last_call = 0.0

    # ----- public READ-ONLY surface (the complete list) ---------------------
    def get_shops(self, page=1, page_size=50):
        return self._request("GET", "/api/v2/public/shop/list",
                             params={"page": page, "page_size": page_size,
                                     "is_active": 1})

    def get_orders(self, updated_from_ts, updated_to_ts, page=1, page_size=50):
        return self._request("GET", "/api/v2/public/order/list",
                             params={"page": page, "page_size": page_size,
                                     "updated_from": int(updated_from_ts),
                                     "updated_to": int(updated_to_ts),
                                     "status_group": "all"})

    def get_order_detail(self, omisell_order_number):
        return self._request(
            "GET", "/api/v2/public/order/%s" % str(omisell_order_number).strip())

    def get_catalogues(self, page=1, page_size=50):
        """G2.2 (2026-06-12): catalogue list - the per-shop SKU source of
        truth (includes platform/shop_id/status/external_id/images/variants).
        READ-ONLY like everything else behind the GET chokepoint. Path
        confirmed live by the G2.2 probe on FES-VN + LOF-VN."""
        return self._request("GET", "/api/v2/public/catalogue/list",
                             params={"page": page, "page_size": page_size})

    # ----- auth --------------------------------------------------------------
    def _auth_scheme(self):
        return frappe.conf.get("ec_alerts_omisell_auth_scheme") or "Omi"

    def _auth_paths(self):
        return (frappe.conf.get("ec_alerts_omisell_auth_path") or DEFAULT_AUTH_PATH,)

    def _headers(self):
        scheme = self._auth_scheme()
        if scheme == "Account":
            key = self.bis.get_password("api_key", raise_exception=False)
            if not key:
                raise OmisellAuthError(_("No api_key on {0}").format(self.bis.name))
            return {"Authorization": "Account %s" % key,
                    "Content-Type": "application/json"}
        return {"Authorization": "Omi %s" % self._ensure_token(),
                "Content-Type": "application/json"}

    def _log_token(self, source):
        """Token-source diagnostic (NO token / credential value ever logged)."""
        try:
            frappe.logger("alerts").info(
                {"omisell_token_source": source, "bis": self.bis.name})
        except Exception:
            pass

    def _ensure_token(self):
        """Reuse the DB-cached token while valid (exp > now + 2 min margin);
        otherwise refresh. Within one client instance the refreshed token is
        held on self.bis and reused by subsequent list/detail calls."""
        token = self.bis.get_password("token", raise_exception=False)
        exp = self.bis.token_expired_at
        if token and exp and get_datetime(exp) > add_to_date(now_datetime(), minutes=2):
            self._log_token("reused_cached")
            return token
        if not token:
            reason = "refreshed_missing_token"
        elif not exp:
            reason = "refreshed_missing_expiry"
        else:
            reason = "refreshed_expired"
        return self._authenticate(reason)

    def _authenticate(self, reason="refreshed"):
        api_key = self.bis.get_password("api_key", raise_exception=False)
        api_secret = self.bis.get_password("api_secret", raise_exception=False)
        if not api_key or not api_secret:
            raise OmisellAuthError(
                _("api_key AND api_secret are required on {0} (official auth "
                  "contract: POST /api/v2/auth/token/get/).").format(self.bis.name))
        # Hotfix A: bounded transient retry for the idempotent auth POST.
        payload = self._request("POST", self._auth_paths()[0],
                                json_body={"api_key": api_key,
                                           "api_secret": api_secret},
                                auth=False, auth_retry=True)
        data = (payload or {}).get("data") or {}
        token = data.get("token")
        if not token:
            raise OmisellAuthError(_("Token exchange failed for {0}").format(self.bis.name))
        self.bis.token = token
        if data.get("expired_time"):
            self.bis.token_expired_at = datetime.fromtimestamp(int(data["expired_time"]))
            self._log_token(reason)
        else:
            # Omisell omitted expired_time -> persist a conservative fallback
            # TTL so we do NOT re-auth on every request.
            self.bis.token_expired_at = add_to_date(now_datetime(),
                                                    minutes=token_ttl_minutes())
            self._log_token("fallback_ttl_applied")
        self.bis.save(ignore_permissions=True)
        return token

    # ----- THE chokepoint -----------------------------------------------------
    def _request(self, method, path, params=None, json_body=None, auth=True,
                 auth_retry=False):
        method = (method or "").upper()
        if method not in ALLOWED_METHODS:
            is_auth_post = (method == "POST" and not auth and
                            any(path.startswith(p) for p in self._auth_paths()))
            if not is_auth_post:
                # No write verb ever leaves this module. Period.
                frappe.throw(
                    _("Omisell client is READ-ONLY: refusing {0} {1}").format(method, path),
                    OmisellError)
        url = self.base + path
        headers = self._headers() if auth else {"Content-Type": "application/json"}

        attempt_429 = 0
        attempt_5xx = 0
        attempt_timeout = 0
        auth_attempts = 0   # Hotfix A: ONE transient-retry budget for the auth POST
        while True:
            self._pace()
            try:
                resp = requests.request(method, url, params=params, json=json_body,
                                        headers=headers, timeout=read_timeout())
            except (requests.Timeout, requests.ConnectionError) as e:
                # GET: read-only, safe to replay (2s, 5s). auth_retry: the
                # idempotent auth POST retries transiently (1s, 3s; <=3 total).
                if method == "GET" and attempt_timeout < len(BACKOFFS_TIMEOUT):
                    time.sleep(BACKOFFS_TIMEOUT[attempt_timeout])
                    attempt_timeout += 1
                    continue
                if auth_retry and auth_attempts < AUTH_MAX_ATTEMPTS - 1:
                    time.sleep(AUTH_BACKOFFS[min(auth_attempts, len(AUTH_BACKOFFS) - 1)])
                    auth_attempts += 1
                    continue
                raise OmisellError(_("TIMEOUT on {0} {1} (after {2} retries, "
                                     "read_timeout={3}s): {4}").format(
                    method, path, attempt_timeout + auth_attempts,
                    read_timeout(), str(e)[:120]))
            self.last_rate_header = resp.headers.get(RATE_HEADER)
            if resp.status_code == 429:
                # auth_retry uses the SHORT auth budget (not the 30/60/120 order
                # schedule) so an unreachable token endpoint surfaces fast.
                if auth_retry:
                    if auth_attempts >= AUTH_MAX_ATTEMPTS - 1:
                        raise OmisellError(_("Rate limited (429) on auth after retries: {0}").format(path))
                    time.sleep(AUTH_BACKOFFS[min(auth_attempts, len(AUTH_BACKOFFS) - 1)])
                    auth_attempts += 1
                    continue
                if attempt_429 >= len(BACKOFFS):
                    raise OmisellError(_("Rate limited (429) after retries: {0}").format(path))
                time.sleep(BACKOFFS[attempt_429])
                attempt_429 += 1
                continue
            if resp.status_code >= 500:
                if auth_retry:
                    if auth_attempts >= AUTH_MAX_ATTEMPTS - 1:
                        raise OmisellError(_("HTTP {0} on auth {1} (after {2} retries)").format(
                            resp.status_code, path, auth_attempts))
                    time.sleep(AUTH_BACKOFFS[min(auth_attempts, len(AUTH_BACKOFFS) - 1)])
                    auth_attempts += 1
                    continue
                # transient server errors: bounded retry (5s, 15s) then surface
                if attempt_5xx >= len(BACKOFFS_5XX):
                    raise OmisellError(_("HTTP {0} on {1} (after {2} retries)").format(
                        resp.status_code, path, attempt_5xx))
                time.sleep(BACKOFFS_5XX[attempt_5xx])
                attempt_5xx += 1
                continue
            if resp.status_code in (401, 403):
                raise OmisellAuthError(
                    _("Auth failed ({0}) on {1}").format(resp.status_code, path))
            if resp.status_code >= 400:
                raise OmisellError(_("HTTP {0} on {1}").format(resp.status_code, path))
            try:
                payload = resp.json()
            except (ValueError, json.JSONDecodeError):
                raise OmisellError(_("Non-JSON response on {0}").format(path))
            if isinstance(payload, dict) and payload.get("error") and \
                    payload.get("error_code") not in (200, 201, 0):
                raise OmisellError(_("Omisell error {0}: {1}").format(
                    payload.get("error_code"),
                    sanitize(payload).get("messages")))
            return payload

    def _pace(self):
        wait = MIN_INTERVAL - (time.monotonic() - self._last_call)
        if wait > 0:
            time.sleep(wait)
        if self.last_rate_header:
            try:
                used = int(str(self.last_rate_header).split("/")[0])
                if used > THROTTLE_AT:
                    time.sleep(5)
            except (ValueError, IndexError):
                pass
        self._last_call = time.monotonic()
