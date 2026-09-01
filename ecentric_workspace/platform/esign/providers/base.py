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
        """First signer row matching the identity, or None. Kept for callers that only need
        "is this person on the document at all"."""
        hits = self.signers_for(user_id, email)
        return hits[0] if hits else None

    def signers_for(self, user_id, email=None):
        """EVERY signer row matching the identity, in provider order.

        One person legitimately occupies SEVERAL rows on the same document - one per signing
        area - and eContract confirms this: after signing as requester AND as department
        manager, the same email appears twice with different times. The earlier
        one-row-only lookup made that ordinary case unresolvable: with two rows it returned
        nothing at all ("expected_signer_absent"), and with one it locked onto whichever came
        first, so an approver leg was judged against the requester's own older signature.
        Callers must therefore consider all rows and pick the one that satisfies them.
        """
        by_id = [s for s in self.signers
                 if s.get("user_id") is not None and str(s.get("user_id")) == str(user_id)]
        if by_id:
            return by_id
        if email:
            em = str(email).strip().lower()
            return [s for s in self.signers
                    if str(s.get("email") or "").strip().lower() == em]
        return []


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

    #: Formats that carry no date at all, resolved against the reference moment.
    _TIME_ONLY = ("%H:%M:%S", "%H:%M")
    #: Formats with day+month but no year (eContract shows "23/08 01:22" in some views).
    _NO_YEAR = ("%d/%m %H:%M:%S", "%d/%m %H:%M")

    @staticmethod
    def _parse_provider_time(value, reference=None):
        """Parse a provider timestamp into a naive datetime, or None if unreadable.

        Providers are inconsistent: eContract returns Vietnamese day-first strings, others
        ISO - and the Document detail returns the sign time as **"04:12", a bare clock with
        no date at all** (observed 2026-08-27). A bare clock cannot be compared to anything
        on its own, so it is resolved against `reference` (the moment we asked for the
        signature): same calendar day, and if that lands absurdly far from the reference we
        step a day either way to absorb a midnight crossing.

        That resolution is a heuristic, but it does NOT weaken the check it serves: a
        signature made minutes BEFORE we asked still lands before the reference and is still
        refused - which is exactly the case this guard exists for.

        Unknown shapes still return None and the caller fails closed rather than guessing.
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
        if reference is None:
            return None                      # nothing to resolve a partial timestamp against
        for fmt in SignatureProviderAdapter._NO_YEAR:
            try:
                partial = datetime.strptime(text, fmt)
                return SignatureProviderAdapter._nearest(
                    partial.replace(year=reference.year), reference)
            except ValueError:
                continue
        for fmt in SignatureProviderAdapter._TIME_ONLY:
            try:
                partial = datetime.strptime(text, fmt)
                return SignatureProviderAdapter._nearest(
                    reference.replace(hour=partial.hour, minute=partial.minute,
                                      second=partial.second, microsecond=0), reference)
            except ValueError:
                continue
        return None

    #: A signature we are verifying lands within minutes of the request, never hours later.
    #: Resolving a bare clock into the future beyond this would let a stale signature pass.
    _FORWARD_GRACE_SECONDS = 3600

    @staticmethod
    def _nearest(candidate, reference):
        """Resolve a date-less clock to a real day, WITHOUT inventing a future signature.

        Choosing the arithmetically closest day is wrong: from a 19:58 reference, a "04:12"
        signature made sixteen hours earlier is closer to TOMORROW's 04:12, so a plain
        nearest-match would move a stale signature into the future and let it pass the
        freshness guard. Caught by test_all_rows_too_old_is_still_refused.

        Rule: take the LATEST day that still sits at or before `reference` plus a small
        forward grace. Only if no such day exists do we accept the earliest later one, which
        covers a provider clock running slightly ahead of ours.
        """
        from datetime import timedelta
        limit = reference + timedelta(seconds=SignatureProviderAdapter._FORWARD_GRACE_SECONDS)
        options = sorted(candidate + timedelta(days=d) for d in (-1, 0, 1))
        allowed = [o for o in options if o <= limit]
        return allowed[-1] if allowed else options[0]

    @staticmethod
    def verify_signed_result(doc_state, expected):
        """Pure check: doc_state (NormalizedDocState) vs expected dict
        {document_id, user_id, signature_id (optional), file_count (optional)}.
        Strict and explainable - SCTS authorization is never trusted."""
        if not isinstance(doc_state, NormalizedDocState):
            return VerificationResult(False, "no_document_state")
        if str(doc_state.document_id) != str(expected.get("document_id")):
            return VerificationResult(False, "document_id_mismatch")
        fc = expected.get("file_count")
        if fc is not None and len(doc_state.files) != int(fc):
            return VerificationResult(False, "file_count_mismatch")
        candidates = doc_state.signers_for(expected.get("user_id"), expected.get("email"))
        if not candidates:
            # NOI RO DANG TIM AI, VA TAI LIEU DANG CO MAY CHAN KY.
            #
            # 02/09/2026: mot chan ky quay `PollTick -> expected_signer_absent` bay lan lien
            # tiep tren mot tai lieu co NAM nguoi ky. Cau do dung, nhung no khong tra loi
            # duoc cau hoi duy nhat dang can: thieu AI, va SCTS co dang liet ke ho khong.
            # Voi nam nguoi thi doc nhat ky xong van phai di doan.
            #
            # Hai tinh huong nay trong y het nhau neu chi in mot chuoi tran:
            #   * SCTS chua kip them dong chan ky (cho them chut la xong);
            #   * dinh danh minh tra khong khop cai SCTS bao (cho mai cung khong xong) -
            #     da tung xay ra khi mot nguoi co NHIEU mau chu ky ben SCTS.
            # `of<N>` tach duoc hai cai do: N=0 la tai lieu chua co ai, N>0 la co nguoi khac
            # ma khong co nguoi nay.
            #
            # CHI ghi dinh danh dung de doi chieu (user id noi bo cua nha cung cap, hoac email
            # cong viec) - khong ten, khong so tien, khong noi dung tai lieu.
            who = expected.get("user_id") or expected.get("email") or "?"
            return VerificationResult(
                False, "expected_signer_absent:%s/of%d" % (who, len(doc_state.signers)))
        # ANY row that satisfies every condition proves this leg. Rejecting because some OTHER
        # row of the same person is older would refuse a perfectly good signature - which is
        # exactly what happened on 2026-08-27 once the same person held two signing areas.
        first_failure = None
        for signer in candidates:
            res = SignatureProviderAdapter._check_one_signer(signer, expected)
            if res.ok:
                return res
            first_failure = first_failure or res
        return first_failure

    @staticmethod
    def _check_one_signer(signer, expected):
        """All per-signer conditions for one candidate row."""
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
            signed_at = SignatureProviderAdapter._parse_provider_time(
                signer.get("signed_at"), reference=after)
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
        return VerificationResult(True, "verified")
