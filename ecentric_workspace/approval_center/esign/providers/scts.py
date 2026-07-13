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
import base64
import hashlib

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
# Max signed-PDF size (bytes); defensive cap so a runaway response can't exhaust memory.
_MAX_SIGNED_PDF_BYTES = 50 * 1024 * 1024


def _sval(settings, key, default=None):
    if isinstance(settings, dict):
        return settings.get(key, default)
    return getattr(settings, key, default)


class SctsAdapter(SignatureProviderAdapter):
    def __init__(self, settings, transport=None, sleeper=None):
        super().__init__(settings)
        self._name = _sval(settings, "name")
        base_url = _sval(settings, "base_url")
        # SSRF / URL safety (fail-closed): require https + non-private host + a NON-EMPTY
        # app-owned host allowlist (empty => no request). Convert to ProviderError so no
        # provider internals leak above the adapter boundary.
        from ecentric_workspace.approval_center.esign import netguard
        allow_hosts = _sval(settings, "base_url_allowlist") or ""
        try:
            netguard.assert_base_url_safe(base_url, allow_hosts=allow_hosts,
                                          require_allowlist=True)
        except ValueError as e:
            raise ProviderError("scts_unsafe_base_url", str(e), retryable=False)

        # per-request revalidation (re-checks the allowlist AND, on the real transport,
        # re-resolves DNS immediately before every request so rebinding cannot slip in a
        # private address). With an injected test transport no real socket is opened, so DNS
        # resolution is skipped while the allowlist check is still enforced.
        from urllib.parse import urlsplit
        _do_dns = transport is None
        _host = urlsplit(str(base_url)).hostname

        def _preflight(method, url):
            ok, reason = netguard.validate_base_url(base_url, allow_hosts=allow_hosts,
                                                    require_allowlist=True)
            if not ok:
                raise ProviderError("scts_unsafe_base_url",
                                    "unsafe_base_url:%s" % reason, retryable=False)
            if _do_dns:
                rok, rreason, _ips = netguard.resolve_and_validate(_host)
                if not rok:
                    raise ProviderError("scts_unsafe_base_url",
                                        "unsafe_base_url:%s" % rreason, retryable=False)

        self._client = SctsClient(
            base_url=base_url,
            timeout=_sval(settings, "request_timeout") or 30,
            retry_limit=_HTTP_RETRY_LIMIT,
            transport=transport, sleeper=sleeper, preflight=_preflight)

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
    def _resolve_active(x):
        """FAIL-CLOSED usability. An explicit isActive/active flag wins; otherwise a
        recognized status may activate. Anything else - explicit false/inactive/revoked/
        expired, an unrecognized value, OR missing all activity/status evidence - is
        treated as INACTIVE/unverified."""
        for key in ("isActive", "active"):
            if key in x and x[key] is not None:
                v = x[key]
                if isinstance(v, bool):
                    return v
                s = str(v).strip().lower()
                if s in ("true", "1", "yes"):
                    return True
                # explicit-but-not-true (false/0/no/anything unrecognized) -> fail closed
                return False
        st = str(x.get("status") or "").strip().lower()
        return st in ("active", "valid", "usable")  # inactive/revoked/expired/"" -> False

    @staticmethod
    def _norm_signature(x):
        if not isinstance(x, dict):
            return {"id": None, "signerId": None, "type": None, "company": None, "active": False}
        sig_id = x.get("id") or x.get("signatureId") or x.get("signerSignatureId")
        signer = x.get("signerId") or x.get("userId") or x.get("signerUserId")
        return {"id": sig_id, "signerId": signer,
                "type": x.get("type") or x.get("signatureType"),
                "company": x.get("company") or x.get("companyName"),
                "active": SctsAdapter._resolve_active(x)}

    def validate_signature_owner(self, mapped_user, signature_id):
        """LIVE ownership + usability check against GetSignatures. Returns a
        VerificationResult; the binding layer converts a False into a hard block BEFORE
        any bulk-process write. SCTS's own authorization is never trusted - ERP proves
        ownership from the provider's signature list for THIS mapped user."""
        # A transient provider error (network/5xx) is NOT swallowed into a False: it
        # PROPAGATES with its original retryable classification, so a provider outage is
        # never misclassified as a security failure. A False result means a real
        # ownership/usability mismatch and is a non-retryable security refusal.
        sigs = self.list_user_signatures(mapped_user)  # transient ProviderError propagates
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
            raw.get("files") or raw.get("documentFiles") or raw.get("Documents"))]
        identity = {
            "doc_code": (raw.get("docCode") or raw.get("documentCode") or raw.get("code")
                         or raw.get("reference") or raw.get("referenceCode")),
            "workflow_definition_id": raw.get("workflowDefinitionId"),
            "document_type_id": raw.get("documentTypeId"),
            "company_id": raw.get("companyId"),
            "department_id": raw.get("departmentId"),
        }
        return NormalizedDocState(str(doc_id), status, signers=signers, files=files, raw={},
                                  identity=identity)

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
        """POST /api/AddDocument (SCTS V1). package_ctx: provider-neutral dict with
        {doc_code, title, amount?, files:[{order, name, content(bytes), can_be_signed,
        is_supporting_document, share_with_partner}], placements:[...]}. Base64 conversion
        of the private PDF bytes happens HERE (the adapter owns the provider payload); the
        base64 is never logged. Returns {document_id, files:[{order, file_id}]}. On an
        ambiguous outcome the client raises ProviderError(ambiguous=True) - the caller must
        reconcile, never blind-recreate."""
        files = package_ctx.get("files") or []
        order_by_dsf = {f.get("file_dsf"): f.get("order") for f in files}
        documents = [{
            "order": f.get("order"),
            "fileName": f.get("name"),
            "originalBase64": self._b64(f.get("content")),
            "canBeSigned": bool(f.get("can_be_signed")),
            "isSupportingDocument": bool(f.get("is_supporting_document")),
            "sharedWithPartner": bool(f.get("share_with_partner")),
        } for f in files]
        signatures = [{
            "documentIndex": order_by_dsf.get(p.get("signature_file")),
            "page": p.get("page_index"),
            "x": p.get("x"), "y": p.get("y"),
            "width": p.get("width"), "height": p.get("height"),
            "levelNo": p.get("level_no"),
            "signatureType": p.get("signature_type"),
            "roleTitle": p.get("scts_role_title"),
        } for p in (package_ctx.get("placements") or [])]
        payload = {
            "workflowDefinitionId": package_ctx.get("workflow_definition_id"),
            "documentTypeId": package_ctx.get("document_type_id"),
            "companyId": package_ctx.get("company_id"),
            "departmentId": package_ctx.get("department_id"),
            "documentTemplateId": package_ctx.get("document_template_id"),
            "Documents": documents,
            "Signatures": signatures,
            "ExternalHandlers": [],  # external signer handlers disabled this phase
        }
        raw = self._with_auth(lambda t: self._client.add_document(payload, t))
        return self._normalize_create(raw, files)

    @staticmethod
    def _b64(content):
        if content is None:
            return None
        if isinstance(content, str):
            content = content.encode("utf-8")
        return base64.b64encode(content).decode("ascii")

    @staticmethod
    def _normalize_create(raw, files):
        doc_id = None
        rawfiles = []
        if isinstance(raw, dict):
            doc_id = raw.get("documentId") or raw.get("id") or raw.get("instanceId")
            data = raw.get("data") if isinstance(raw.get("data"), dict) else None
            if not doc_id and data:
                doc_id = data.get("documentId") or data.get("id")
            rawfiles = (raw.get("files") or raw.get("documentFiles") or raw.get("Documents")
                        or (data.get("files") if data else None) or [])
        if not doc_id:
            raise ProviderError("scts_create_no_document_id",
                                "AddDocument returned no documentId", retryable=False)
        by_order = {}
        for rf in rawfiles:
            if isinstance(rf, dict):
                o = rf.get("order")
                if o is None:
                    o = rf.get("index")
                by_order[o] = rf.get("documentFileId") or rf.get("fileId") or rf.get("id")
        out = [{"order": f.get("order"), "file_id": by_order.get(f.get("order"))}
               for f in files]
        return {"document_id": str(doc_id), "files": out}

    def get_signed_document(self, provider_document_id, provider_file_id=None):
        """Retrieve one signed PDF (backend-only). Validates the response is a non-empty,
        size-bounded PDF (%PDF- magic) and returns {content(bytes), sha256, size}. Binary/
        base64 content is NEVER logged. The CALLER must first confirm a terminal signed
        state via GET /api/Document/{id}; this method does not re-check completion."""
        raw = self._with_auth(
            lambda t: self._client.get_pdf(provider_document_id, provider_file_id, t))
        if not isinstance(raw, (bytes, bytearray)) or len(raw) == 0:
            raise ProviderError("scts_signed_pdf_empty",
                                "SCTS returned an empty signed PDF", retryable=False)
        raw = bytes(raw)
        if len(raw) > _MAX_SIGNED_PDF_BYTES:
            raise ProviderError("scts_signed_pdf_too_large",
                                "signed PDF exceeds the configured maximum size",
                                retryable=False)
        if raw[:5] != b"%PDF-":
            raise ProviderError("scts_signed_pdf_not_pdf",
                                "signed content is not a PDF (bad magic header)",
                                retryable=False)
        return {"content": raw, "sha256": hashlib.sha256(raw).hexdigest(), "size": len(raw)}

    def get_pdf(self, document_id, document_file_id):
        """Base-interface alias -> raw signed PDF bytes."""
        return self.get_signed_document(document_id, document_file_id)["content"]

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
