# Copyright (c) 2026, eCentric and contributors
"""Low-level SCTS HTTP client (NO frappe import - unit-testable with an injected
transport, never touches the network in CI).

Responsibilities: HTTP mechanics ONLY - authentication, token expiry handling, safe
single re-login on 401, configurable timeout, bounded retry for network / 5xx errors,
NO retry for validation / auth / security errors, and normalization of every failure
into base.ProviderError (retryable flag drives Retryable vs Permanent Failure upstream).

It knows the four SCTS UAT endpoints required for S2B-A:
    POST /api/Auth/login
    GET  /api/SignerSignature/GetSignatures/{userId}
    POST /api/Workflow/bulk-process
    GET  /api/Document/{documentId}

It returns PARSED JSON (dict/list); provider->ERP field normalization lives in the
adapter (scts.py). Secrets (token, password, Authorization header, file content) are
NEVER logged or echoed into ProviderError messages.
"""
import time

from ecentric_workspace.approval_center.esign.providers.base import ProviderError

# HTTP status classes we treat distinctly.
_AUTH_STATUSES = (401, 403)
_NO_RETRY_4XX = (400, 401, 403, 404, 409, 422)  # validation / auth / security -> never retry


class SctsHttpError(Exception):
    """Internal: an HTTP response with a non-2xx status. Carries status + safe body."""

    def __init__(self, status, body=""):
        super().__init__("http_%s" % status)
        self.status = int(status)
        self.body = body


def _default_transport(method, url, headers=None, json_body=None, timeout=30, verify_tls=True):
    """Real transport (requests). Imported lazily so the module imports with no network
    stack and tests never hit it."""
    import requests  # bundled with frappe
    resp = requests.request(method, url, headers=headers or {}, json=json_body,
                            timeout=timeout, verify=verify_tls)
    return resp


class SctsClient(object):
    """Stateful only in that it holds the last obtained bearer token in-process. Token
    PERSISTENCE across workers is the adapter's job (encrypted settings cache); this
    client just performs login and attaches the token it is given / obtains."""

    def __init__(self, base_url, timeout=30, retry_limit=2, verify_tls=True,
                 transport=None, sleeper=None, backoff_base=0.5):
        if not base_url:
            raise ProviderError("scts_base_url_missing", "SCTS base_url is not configured",
                                retryable=False)
        self.base_url = base_url.rstrip("/")
        self.timeout = int(timeout or 30)
        self.retry_limit = max(0, int(retry_limit if retry_limit is not None else 2))
        self.verify_tls = bool(verify_tls)
        self._transport = transport or _default_transport
        self._sleep = sleeper if sleeper is not None else time.sleep
        self._backoff_base = backoff_base

    # -- url ------------------------------------------------------------------
    def _url(self, path):
        return "%s/%s" % (self.base_url, path.lstrip("/"))

    # -- core request with bounded retry -------------------------------------
    def _request(self, method, path, token=None, json_body=None, _label="request"):
        """One logical call with bounded retry. Retries ONLY transport errors and 5xx;
        4xx (validation/auth/security) raise immediately. Returns parsed JSON."""
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        attempt = 0
        last_exc = None
        while attempt <= self.retry_limit:
            try:
                resp = self._transport(method, self._url(path), headers=headers,
                                       json_body=json_body, timeout=self.timeout,
                                       verify_tls=self.verify_tls)
            except Exception as e:  # transport-level (connection/timeout/DNS): retryable
                last_exc = ProviderError("scts_network_error",
                                         "network error during %s" % _label, retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            status = int(getattr(resp, "status_code", 0))
            if 200 <= status < 300:
                return self._parse(resp, _label)
            if status >= 500:  # server error: bounded retry
                last_exc = ProviderError("scts_server_error_%s" % status,
                                         "SCTS server error (%s) during %s" % (status, _label),
                                         retryable=True)
                attempt += 1
                if attempt > self.retry_limit:
                    raise last_exc
                self._sleep(self._backoff_base * attempt)
                continue
            # 4xx: validation / auth / security -> NEVER retry (fail closed).
            raise SctsHttpError(status, self._safe_body(resp))
        raise last_exc or ProviderError("scts_unknown_error", "unknown error during %s" % _label,
                                        retryable=True)

    @staticmethod
    def _parse(resp, _label):
        try:
            return resp.json()
        except Exception:
            raise ProviderError("scts_malformed_response",
                                "SCTS returned a non-JSON / malformed body during %s" % _label,
                                retryable=False)

    @staticmethod
    def _safe_body(resp):
        """A short, non-sensitive slice of the error body for diagnostics. Never returns
        tokens: callers only surface status codes upstream."""
        try:
            txt = resp.text or ""
        except Exception:
            txt = ""
        low = txt.lower()
        if any(s in low for s in ("token", "bearer", "authorization", "password", "base64")):
            return "(body withheld - sensitive markers)"
        return txt[:200]

    # -- endpoints ------------------------------------------------------------
    def login(self, username, password):
        """POST /api/Auth/login -> raw provider auth payload (parsed JSON). The adapter
        extracts token + expiry. 4xx here is an auth failure (non-retryable)."""
        try:
            return self._request("POST", "/api/Auth/login",
                                 json_body={"username": username, "password": password},
                                 _label="login")
        except SctsHttpError as e:
            raise ProviderError("scts_auth_failed",
                                "SCTS authentication failed (HTTP %s)" % e.status,
                                retryable=False)

    def get_signatures(self, user_id, token):
        """GET /api/SignerSignature/GetSignatures/{userId} -> raw list/dict."""
        try:
            return self._request("GET", "/api/SignerSignature/GetSignatures/%s" % user_id,
                                 token=token, _label="get_signatures")
        except SctsHttpError as e:
            if e.status in _AUTH_STATUSES:
                raise ProviderError("scts_auth_error_%s" % e.status,
                                    "SCTS rejected credentials on get_signatures (HTTP %s)"
                                    % e.status, retryable=False)
            raise ProviderError("scts_signatures_rejected_%s" % e.status,
                                "SCTS refused get_signatures (HTTP %s)" % e.status,
                                retryable=False)

    def bulk_process(self, instance_ids, user_id, signature_id, transition_type, token):
        """POST /api/Workflow/bulk-process -> raw payload. ASYNC ACCEPTED semantics:
        a 2xx means only that SCTS queued the job (bulkJobTransactionId). It is NEVER
        proof of signing - the caller must poll + verify Document/{id}.

        NON-IDEMPOTENT WRITE: exactly ONE HTTP attempt, NO automatic retry. A network
        error, timeout or 5xx is AMBIGUOUS - the provider may already have accepted the
        signing action - so it is normalized to `scts_bulk_outcome_unknown` (ambiguous,
        non-retryable); the caller transitions to Verifying and polls Document/{id}
        rather than resending. Only a definite 4xx is a hard rejection.

        Field contract (confirmed SCTS UAT): the signature is sent as `SignerSignatureId`."""
        body = {"instanceIds": list(instance_ids), "userId": user_id,
                "SignerSignatureId": signature_id}
        if transition_type is not None:
            body["transitionType"] = transition_type
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer %s" % token
        try:
            resp = self._transport("POST", self._url("/api/Workflow/bulk-process"),
                                   headers=headers, json_body=body, timeout=self.timeout,
                                   verify_tls=self.verify_tls)
        except Exception:
            # transport-level (connection/timeout/DNS): outcome UNKNOWN, never resend.
            raise ProviderError("scts_bulk_outcome_unknown",
                                "bulk-process outcome unknown (network/timeout)",
                                retryable=False, ambiguous=True)
        status = int(getattr(resp, "status_code", 0))
        if 200 <= status < 300:
            return self._parse(resp, "bulk_process")
        if status in _AUTH_STATUSES:
            raise ProviderError("scts_auth_error_%s" % status,
                                "SCTS rejected credentials on bulk-process (HTTP %s)" % status,
                                retryable=False)
        if status >= 500:
            # server error on a non-idempotent write: AMBIGUOUS, never resend.
            raise ProviderError("scts_bulk_outcome_unknown",
                                "bulk-process outcome unknown (HTTP %s)" % status,
                                retryable=False, ambiguous=True)
        # definite 4xx: a real rejection (not accepted) -> permanent, no retry.
        raise ProviderError("scts_bulk_rejected_%s" % status,
                            "SCTS rejected bulk-process (HTTP %s)" % status, retryable=False)

    def get_document(self, document_id, token):
        """GET /api/Document/{documentId} -> raw document payload (status/files/signers)."""
        try:
            return self._request("GET", "/api/Document/%s" % document_id, token=token,
                                 _label="get_document")
        except SctsHttpError as e:
            if e.status in _AUTH_STATUSES:
                raise ProviderError("scts_auth_error_%s" % e.status,
                                    "SCTS rejected credentials on get_document (HTTP %s)"
                                    % e.status, retryable=False)
            if e.status == 404:
                raise ProviderError("scts_document_not_found",
                                    "SCTS document not found (HTTP 404)", retryable=False)
            raise ProviderError("scts_document_error_%s" % e.status,
                                "SCTS refused get_document (HTTP %s)" % e.status,
                                retryable=False)
