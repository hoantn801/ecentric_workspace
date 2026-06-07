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
TIMEOUT = 30
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

    def _ensure_token(self):
        token = self.bis.get_password("token", raise_exception=False)
        exp = self.bis.token_expired_at
        if token and exp and get_datetime(exp) > add_to_date(now_datetime(), minutes=2):
            return token
        return self._authenticate()

    def _authenticate(self):
        api_key = self.bis.get_password("api_key", raise_exception=False)
        api_secret = self.bis.get_password("api_secret", raise_exception=False)
        if not api_key or not api_secret:
            raise OmisellAuthError(
                _("api_key AND api_secret are required on {0} (official auth "
                  "contract: POST /api/v2/auth/token/get/).").format(self.bis.name))
        payload = self._request("POST", self._auth_paths()[0],
                                json_body={"api_key": api_key,
                                           "api_secret": api_secret},
                                auth=False)
        data = (payload or {}).get("data") or {}
        token = data.get("token")
        if not token:
            raise OmisellAuthError(_("Token exchange failed for {0}").format(self.bis.name))
        self.bis.token = token
        if data.get("expired_time"):
            self.bis.token_expired_at = datetime.fromtimestamp(int(data["expired_time"]))
        self.bis.save(ignore_permissions=True)
        return token

    # ----- THE chokepoint -----------------------------------------------------
    def _request(self, method, path, params=None, json_body=None, auth=True):
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

        attempt = 0
        while True:
            self._pace()
            resp = requests.request(method, url, params=params, json=json_body,
                                    headers=headers, timeout=TIMEOUT)
            self.last_rate_header = resp.headers.get(RATE_HEADER)
            if resp.status_code == 429:
                if attempt >= len(BACKOFFS):
                    raise OmisellError(_("Rate limited (429) after retries: {0}").format(path))
                time.sleep(BACKOFFS[attempt])
                attempt += 1
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
