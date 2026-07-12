# Copyright (c) 2026, eCentric and contributors
"""Provider-neutral adapter contract (NO frappe import). The Approval Engine and the
orchestrator never construct provider payloads - adapters own field names, Base64
conversion, provider IDs, transition payloads, async 'accepted' handling, polling
normalization, file retrieval and error mapping."""


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

    def __init__(self, document_id, status, signers=None, files=None, raw=None):
        self.document_id = document_id
        self.status = status
        self.signers = signers or []
        self.files = files or []
        self.raw = raw or {}

    def signer(self, user_id):
        for s in self.signers:
            if str(s.get("user_id")) == str(user_id):
                return s
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

    # --- status ---------------------------------------------------------------
    def poll_status(self, document_id):
        """Returns NormalizedDocState."""
        raise NotImplementedError

    def normalize_error(self, exc_or_response):
        raise NotImplementedError

    @staticmethod
    def verify_signed_result(doc_state, expected):
        """Pure check: doc_state (NormalizedDocState) vs expected dict
        {document_id, user_id, signature_id (optional), file_count (optional)}.
        Strict and explainable - SCTS authorization is never trusted."""
        if not isinstance(doc_state, NormalizedDocState):
            return VerificationResult(False, "no_document_state")
        if str(doc_state.document_id) != str(expected.get("document_id")):
            return VerificationResult(False, "document_id_mismatch")
        signer = doc_state.signer(expected.get("user_id"))
        if not signer:
            return VerificationResult(False, "expected_signer_absent")
        if signer.get("status") != "signed":
            return VerificationResult(False, "signer_not_signed:%s" % signer.get("status"))
        exp_sig = expected.get("signature_id")
        if exp_sig and signer.get("signature_id") and str(signer["signature_id"]) != str(exp_sig):
            return VerificationResult(False, "signature_id_mismatch")
        fc = expected.get("file_count")
        if fc is not None and len(doc_state.files) != int(fc):
            return VerificationResult(False, "file_count_mismatch")
        return VerificationResult(True, "verified")
