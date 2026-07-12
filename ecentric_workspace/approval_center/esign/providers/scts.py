# Copyright (c) 2026, eCentric and contributors
"""SCTS provider adapter (UAT). Implements the provider-neutral SignatureProviderAdapter
contract on top of the frappe-free SctsClient. This is the ONLY module besides
scts_client that knows SCTS payload shapes; the orchestrator and engine never see them.

Credentials live in encrypted Password fields on EC Digital Signature Provider Settings
(username/password) and are read via get_decrypted_password only. The bearer token is
cached ENCRYPTED in token_cache (+ token_expires_at) through the doc-save path - never
db.set_value on a Password field, never logged. All gate enforcement lives in guard /
binding; this adapter is a transport + normalization layer.

S2B-A SCOPE: authenticate, get_signatures (list_user_signatures), validate_signature_owner,
approve_and_sign (bulk-process submit primitive), get_document + poll_status
(GET /api/Document/{id}), normalize_error. Document ASSEMBLY (AddDocument / ConvertPdf /
get_pdf) and Workflow transition are deferred to a later sub-phase and fail closed with a
clear normalized error rather than a half-built call.
"""
import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime
from frappe.utils.password import get_decrypted_password

from ecentric_workspace.approval_center.esign.providers.base import (
    NormalizedDocState, ProviderError, SignatureProviderAdapter, VerificationResult,
)
from ecentric_workspace.approval_center.esign.providers.scts_client import SctsClient

SETTINGS_DT = "EC Digital Signature Provider Settings"

# Per-call HTTP retry bound (network / 5xx) is a conservative code constant; higher-level
# reconciler retry is governed by the existing max_poll_attempts setting. Keeping it a
# constant avoids a schema/migration change in S2B-A (see report §3).
_HTTP_RETRY_LIMIT = 2
# Refresh the cached token this many minutes BEFORE its stated expiry (clock skew guard).
_TOKEN_SKEW_MIN = 5


def _sval(settings, key, default=None):
    if isinstance(settings, dict):
        return settings.get(key, default)
    return getattr(settings, key, default)


class SctsAdapter(SignatureProviderAdapter):
    def __init__(self, settings, transport=None, sleeper=None):
        super().__init__(settings)
        self._name = _sval(settings, "name")
        self._client = SctsClient(
            base_url=_sval(settings, "base_url"),
            timeout=_sval(settings, "request_timeout") or 30,
            retry_limit=_HTTP_RETRY_LIMIT,
            transport=transport, sleeper=sleeper)

    # -- credentials (encrypted; never logged) --------------------------------
    def _password(self, fieldname):
        if not self._name:
            return None
        try:
            return get_decrypted_password(SETTINGS_DT, self._name, fieldname,
                                          raise_exception=False)
        except Exception:
            return None

    # -- token cache (encrypted, doc-save path) -------------------------------
    def _cached_token(self):
        exp = _sval(self.settings, "token_expires_at")
        if not exp:
            return None
        try:
            if get_datetime(exp) <= add_to_date(now_datetime(), minutes=_TOKEN_SKEW_MIN):
                return None  # expired or within skew window -> force refresh
        except Exception:
            return None
        return self._password("token_cache")

    def _store_token(self, token, expires_in_minutes):
        """Persist through the ORM so the Password field is encrypted (controller rule)."""
        if not self._name:
            return
        try:
            mins = int(expires_in_minutes or 0)
        except (TypeError, ValueError):
            mins = 0
        doc = frappe.get_doc(SETTINGS_DT, self._name)
        doc.token_cache = token
        doc.token_expires_at = add_to_date(now_datetime(), minutes=mins) if mins else None
        doc.save(ignore_permissions=True)
        # keep the in-memory settings snapshot coherent for the rest of this call
        if isinstance(self.settings, dict):
            self.settings["token_expires_at"] = doc.token_expires_at

    # -- session --------------------------------------------------------------
    def authenticate(self):
        """Force a fresh login and cache the token. Returns a SAFE summary (no token)."""
        username = _sval(self.settings, "username")
        password = self._password("password")
        if not username or not password:
            raise ProviderError("scts_credentials_missing",
                                "SCTS username/password not configured", retryable=False)
        raw = self._client.login(username, password)
        token = self._extract_token(raw)
        if not token:
            raise ProviderError("scts_login_no_token",
                                "SCTS login returned no token", retryable=False)
        mins = raw.get("expiresInMinutes") if isinstance(raw, dict) else None
        self._store_token(token, mins)
        return {"authenticated": True, "expires_in_minutes": mins}

    def refresh_or_get_token(self):
        """Return a usable bearer token: cached if still valid, otherwise re-login."""
        tok = self._cached_token()
        if tok:
            return tok
        self.authenticate()
        return self._password("token_cache")

    @staticmethod
    def _extract_token(raw):
        if not isinstance(raw, dict):
            return None
        for k in ("token", "accessToken", "access_token", "jwt", "bearer"):
            if raw.get(k):
                return raw[k]
        data = raw.get("data") if isinstance(raw.get("data"), dict) else None
        if data:
            for k in ("token", "accessToken", "access_token"):
                if data.get(k):
                    return data[k]
        return None

    def _with_auth(self, fn):
        """Run fn(token); on a provider AUTH error refresh ONCE and retry (single
        safe re-login). Any other error propagates as-is."""
        token = self.refresh_or_get_token()
        try:
            return fn(token)
        except ProviderError as e:
            if str(e.code or "").startswith("scts_auth_error"):
                self.authenticate()
                return fn(self._password("token_cache"))
            raise

    def test_connection(self):
        self.authenticate()
        return {"ok": True, "provider": "SCTS",
                "environment": _sval(self.settings, "environment")}

    # -- identity -------------------------------------------------------------
    def list_user_signatures(self, provider_user_id):
        raw = self._with_auth(lambda t: self._client.get_signatures(provider_user_id, t))
        return [self._norm_signature(x) for x in self._as_list(raw)]

    @staticmethod
    def _norm_signature(x):
        if not isinstance(x, dict):
            return {"id": None, "signerId": None, "type": None, "company": None, "active": False}
        sig_id = x.get("id") or x.get("signatureId") or x.get("signerSignatureId")
        signer = x.get("signerId") or x.get("userId") or x.get("signerUserId")
        active = x.get("isActive")
        if active is None:
            active = x.get("active")
        if active is None:
            st = str(x.get("status") or "").lower()
            active = st in ("", "active", "valid", "usable") and st != "inactive"
        return {"id": sig_id, "signerId": signer,
                "type": x.get("type") or x.get("signatureType"),
                "company": x.get("company") or x.get("companyName"),
                "active": bool(active)}

    def validate_signature_owner(self, mapped_user, signature_id):
        """LIVE ownership + usability check against GetSignatures. Returns a
        VerificationResult; the binding layer converts a False into a hard block BEFORE
        any bulk-process write. SCTS's own authorization is never trusted - ERP proves
        ownership from the provider's signature list for THIS mapped user."""
        try:
            sigs = self.list_user_signatures(mapped_user)
        except ProviderError as e:
            return VerificationResult(False, "signatures_unavailable:%s" % (e.code or "err"))
        match = None
        for s in sigs:
            if str(s.get("id")) == str(signature_id):
                match = s
                break
        if not match:
            return VerificationResult(False, "signature_not_in_user_set")
        if str(match.get("signerId")) != str(mapped_user):
            return VerificationResult(False, "signature_owner_mismatch")
        if not match.get("active"):
            return VerificationResult(False, "signature_inactive")
        return VerificationResult(True, "verified_owner")

    # -- actions --------------------------------------------------------------
    def approve_and_sign(self, instance_ids, provider_user_id, signature_id,
                         transition_type=None):
        """POST /api/Workflow/bulk-process. Async ACCEPTED only -> returns
        {bulk_job_transaction_id}. Never treated as signing success."""
        raw = self._with_auth(lambda t: self._client.bulk_process(
            instance_ids, provider_user_id, signature_id, transition_type, t))
        return {"bulk_job_transaction_id": self._extract_txn_id(raw)}

    @staticmethod
    def _extract_txn_id(raw):
        if isinstance(raw, dict):
            for k in ("bulkJobTransactionId", "transactionId", "bulkJobId", "id", "jobId"):
                if raw.get(k):
                    return str(raw[k])
            data = raw.get("data") if isinstance(raw.get("data"), dict) else None
            if data:
                for k in ("bulkJobTransactionId", "transactionId", "id"):
                    if data.get(k):
                        return str(data[k])
        return None

    # -- documents / status ---------------------------------------------------
    def get_document(self, document_id):
        return self._with_auth(lambda t: self._client.get_document(document_id, t))

    def get_document_status(self, provider_document_id):
        """Normalized document status (alias surface required by S2B-A §4)."""
        return self.poll_status(provider_document_id)

    def poll_status(self, document_id):
        raw = self.get_document(document_id)
        return self._normalize_document(document_id, raw)

    def _normalize_document(self, document_id, raw):
        if not isinstance(raw, dict):
            raise ProviderError("scts_malformed_document",
                                "SCTS document payload was not an object", retryable=False)
        doc_id = raw.get("id") or raw.get("documentId") or document_id
        status = raw.get("status") or raw.get("documentStatus") or raw.get("state")
        signers = [self._norm_signer(s) for s in self._as_list(
            raw.get("signers") or raw.get("signatures") or raw.get("signerSignatures"))]
        files = [self._norm_file(f) for f in self._as_list(
            raw.get("files") or raw.get("documentFiles"))]
        return NormalizedDocState(str(doc_id), status, signers=signers, files=files, raw={})

    @staticmethod
    def _norm_signer(s):
        if not isinstance(s, dict):
            return {"user_id": None, "signature_id": None, "status": "pending",
                    "signed_at": None, "is_external": False}
        raw_status = str(s.get("status") or s.get("signStatus") or "").lower()
        is_signed = s.get("isSigned")
        if is_signed is True or raw_status in ("signed", "completed", "done", "success"):
            norm = "signed"
        elif raw_status in ("rejected", "declined", "returned", "failed"):
            norm = "rejected"
        else:
            norm = "pending"
        return {"user_id": s.get("userId") or s.get("signerId") or s.get("signerUserId"),
                "signature_id": s.get("signatureId") or s.get("signerSignatureId"),
                "status": norm,
                "signed_at": s.get("signedAt") or s.get("signedDate") or s.get("signTime"),
                "is_external": bool(s.get("isExternal") or s.get("external"))}

    @staticmethod
    def _norm_file(f):
        if not isinstance(f, dict):
            return {"file_id": None, "name": None}
        return {"file_id": f.get("documentFileId") or f.get("fileId") or f.get("id"),
                "name": f.get("fileName") or f.get("name")}

    # -- deferred ops (fail closed, clearly) ----------------------------------
    def create_document(self, package_ctx):
        raise ProviderError("scts_create_document_deferred",
                            "SCTS document assembly (AddDocument) ships in a later "
                            "sub-phase; provide scts_document_id out-of-band for S2B-A.",
                            retryable=False)

    def get_pdf(self, document_id, document_file_id):
        raise ProviderError("scts_get_pdf_deferred",
                            "SCTS signed-file retrieval ships in a later sub-phase.",
                            retryable=False)

    def execute_transition(self, instance_id, transition_id, meta=None):
        raise ProviderError("scts_transition_deferred",
                            "SCTS workflow transition sync ships in a later sub-phase.",
                            retryable=False)

    # -- error normalization --------------------------------------------------
    def normalize_error(self, exc_or_response):
        if isinstance(exc_or_response, ProviderError):
            return exc_or_response
        return ProviderError("scts_error", "SCTS error", retryable=False)

    # -- helpers --------------------------------------------------------------
    @staticmethod
    def _as_list(v):
        if v is None:
            return []
        if isinstance(v, list):
            return v
        if isinstance(v, dict):
            for k in ("items", "data", "results", "signatures", "value"):
                if isinstance(v.get(k), list):
                    return v[k]
            return [v]
        return []
