# Copyright (c) 2026, eCentric and contributors
"""Provider-neutral adapter contract (NO frappe import). The Approval Engine and the
orchestrator never construct provider payloads - adapters own field names, Base64
conversion, provider IDs, transition payloads, async 'accepted' handling, polling
normalization, file retrieval and error mapping."""
from datetime import datetime


class ProviderError(Exception):
    """Normalized provider error. `retryable` drives Retryable vs Permanent Failure.
    `ambiguous` marks an outcome that MUST NOT be auto-resent (e.g. a lost/timeout/5xx
    response to a non-idempotent write like bulk-process): the request may already have
    been accepted provider-side, so the caller must poll to verify, never blind-retry."""

    def __init__(self, code, message, retryable=False, ambiguous=False):
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = bool(retryable)
        self.ambiguous = bool(ambiguous)


class NormalizedDocState(object):
    """Provider-agnostic snapshot of one provider document.

    signers: list of dicts {user_id, signature_id, status ('pending'|'signed'|'rejected'),
             signed_at, is_external}
    files:   list of dicts {file_id, name}
    """

    def __init__(self, document_id, status, signers=None, files=None, raw=None, identity=None):
        self.document_id = document_id
        self.status = status
        self.signers = signers or []
        self.files = files or []
        self.raw = raw or {}
        # normalized SAFE identity fields (no secrets) for reconciliation identity proof:
        # {doc_code, workflow_definition_id, document_type_id, company_id, department_id}
        self.identity = identity or {}

    def signer(self, user_id, email=None):
        """Locate the expected signer. Primary key: provider user_id. eContract's Document
        detail does NOT return signer userIds - internal signers are identifiable only by
        EMAIL - so an exact-email fallback (case-insensitive, unambiguous) is authoritative
        when user_id matching finds nothing."""
        for s in self.signers:
            if s.get("user_id") is not None and str(s.get("user_id")) == str(user_id):
                return s
        if email:
            em = str(email).strip().lower()
            hits = [s for s in self.signers
                    if str(s.get("email") or "").strip().lower() == em]
            if len(hits) == 1:
                return hits[0]
        return None


class VerificationResult(object):
    def __init__(self, ok, reason=""):
        self.ok = bool(ok)
        self.reason = reason

    def __bool__(self):
        return self.ok


class SignatureProviderAdapter(object):
    """Interface. Every method may raise ProviderError (normalized)."""

    def __init__(self, settings):
        self.settings = settings

    # --- session -----------------------------------------------------------
    def authenticate(self):
        raise NotImplementedError

    def refresh_or_get_token(self):
        raise NotImplementedError

    def test_connection(self):
        raise NotImplementedError

    # --- catalog (S2B; optional per provider) --------------------------------
    def list_companies(self):
        raise NotImplementedError

    def list_departments(self):
        raise NotImplementedError

    def list_document_types(self):
        raise NotImplementedError

    def list_workflows(self):
        raise NotImplementedError

    # --- documents -----------------------------------------------------------
    def convert_pdf(self, file_bytes):
        raise NotImplementedError

    def create_document(self, package_ctx):
        """package_ctx: provider-neutral dict (doc meta + ordered files + placements
        + signer chain). Returns {document_id, files: [{order, file_id}]}."""
        raise NotImplementedError

    def get_document(self, document_id):
        raise NotImplementedError

    def get_pdf(self, document_id, document_file_id):
        raise NotImplementedError

    # --- identity ------------------------------------------------------------
    def list_user_signatures(self, provider_user_id):
        raise NotImplementedError

    # --- actions ---------------------------------------------------------------
    def approve_and_sign(self, instance_ids, provider_user_id, signature_id, transition_type=None):
        """Async accepted semantics: returns {bulk_job_transaction_id}. Acceptance is
        NEVER success - callers must poll + verify."""
        raise NotImplementedError

    def execute_transition(self, instance_id, transition_id, meta=None):
        raise NotImplementedError

    def transition_with_recipients(self, instance_id, provider_user_id, to_users, config,
                                   signature_id, signature_name=None, comment=None):
        """Sign AND name the next handler(s). Providers whose workflow would otherwise
        broadcast to a role pool must implement this; the orchestrator prefers it and only
        falls back to `approve_and_sign` when the next handler cannot be determined."""
        raise NotImplementedError

    # --- status ---------------------------------------------------------------
    def poll_status(self, document_id):
        """Returns NormalizedDocState."""
        raise NotImplementedError

    def normalize_error(self, exc_or_response):
        raise NotImplementedError

    #: Clock skew + minute-granularity slack when comparing provider sign time against the
    #: moment we queued the request. Wide enough for a provider that reports HH:MM only,
    #: far narrower than any realistic "somebody else signed earlier" gap.
    SIGN_TIME_TOLERANCE_SECONDS = 120

    @staticmethod
    def _parse_provider_time(value):
        """Parse a provider timestamp into a naive datetime, or None if unreadable.

        Providers are inconsistent: eContract returns Vietnamese day-first strings, others
        ISO. Unknown shapes return None and the caller fails closed rather than guessing.
        """
        if value is None:
            return None
        if isinstance(value, datetime):
            return value.replace(tzinfo=None) if value.tzinfo else value
        text = str(value).strip()
        if not text or text.lower() in ("none", "null", "chưa có", "chua co"):
            return None
        text = text.replace("T", " ").replace("Z", "").strip()
        if "+" in text[10:]:
            text = text[:10] + text[10:].split("+")[0]
        text = text.strip()
        for fmt in ("%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M",
                    "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d-%m-%Y %H:%M:%S",
                    "%d-%m-%Y %H:%M", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(text, fmt)
            except ValueError:
                continue
        return None

    @staticmethod
    def verify_signed_result(doc_state, expected):
        """Pure check: doc_state (NormalizedDocState) vs expected dict
        {document_id, user_id, signature_id (optional), file_count (optional)}.
        Strict and explainable - SCTS authorization is never trusted."""
        if not isinstance(doc_state, NormalizedDocState):
            return VerificationResult(False, "no_document_state")
        if str(doc_state.document_id) != str(expected.get("document_id")):
            return VerificationResult(False, "document_id_mismatch")
        signer = doc_state.signer(expected.get("user_id"), expected.get("email"))
        if not signer:
            return VerificationResult(False, "expected_signer_absent")
        if signer.get("status") != "signed":
            return VerificationResult(False, "signer_not_signed:%s" % signer.get("status"))
        # FRESHNESS (2026-08-27). Without this, "did this email sign the document?" is true
        # as soon as the person signed ANY area - so an approver leg was reported verified
        # while the only signature present was that person's own REQUESTER signature from
        # minutes earlier (pilot UAT VOID 5: DSR marked Approval Completed with zero
        # approver signatures on the PDF). The signature that satisfies this leg must be
        # NEWER than the moment we asked for it.
        after = expected.get("signed_after")
        if after:
            signed_at = SignatureProviderAdapter._parse_provider_time(signer.get("signed_at"))
            if not signed_at:
                # Fail CLOSED: an unreadable timestamp cannot prove freshness. The raw value
                # is echoed so an unknown provider format is diagnosable in one look.
                return VerificationResult(
                    False, "signed_at_unreadable:%s" % (signer.get("signed_at") or "none"))
            if signed_at < after:
                return VerificationResult(
                    False, "signature_predates_request:%s" % signer.get("signed_at"))
        exp_sig = expected.get("signature_id")
        if exp_sig and signer.get("signature_id") and str(signer["signature_id"]) != str(exp_sig):
            return VerificationResult(False, "signature_id_mismatch")
        fc = expected.get("file_count")
        if fc is not None and len(doc_state.files) != int(fc):
            return VerificationResult(False, "file_count_mismatch")
        return VerificationResult(True, "verified")
