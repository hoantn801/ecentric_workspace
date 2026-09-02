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

from ecentric_workspace.platform.esign.providers.base import (
    NormalizedDocState, ProviderError, SignatureProviderAdapter, VerificationResult,
)
from ecentric_workspace.platform.esign.providers.scts_client import SctsClient

SETTINGS_DT = "EC Digital Signature Provider Settings"

# Per-call HTTP retry bound (network / 5xx) is a conservative code constant; higher-level
# reconciler retry is governed by the existing max_poll_attempts setting. Keeping it a
# constant avoids a schema/migration change in S2B-A (see report §3).
_HTTP_RETRY_LIMIT = 2
# Refresh the cached token this many minutes BEFORE its stated expiry (clock skew guard).
_TOKEN_SKEW_MIN = 5
# Max signed-PDF size (bytes); defensive cap so a runaway response can't exhaust memory.
_MAX_SIGNED_PDF_BYTES = 50 * 1024 * 1024


# --------------------------------------------------------------------------- #
# he don vi toa do chu ky cua SCTS (HIEU CHINH TU DO DAC, khong phai tu dac ta)
# --------------------------------------------------------------------------- #
#
# DO DAC 02/09/2026 tren tai lieu that (EC-DSP-2026-00028, A4 595x842, 2 chu ky):
#
#     chan ky          ERP GUI (llx, lly, w, h)   SCTS DAT THUC (llx, lly, w, h)
#     Nguoi de nghi    355.0  721.0  240  120     286.2  588.8  180   90
#     Direct Manager   263.0  606.0  240  120     217.2  502.5  180   90
#
# Bon phep do DOC LAP deu ra dung mot ty le:
#     theo vi tri : (286.2-217.2)/(355-263) = 0.7500 ; (588.8-502.5)/(721-606) = 0.7504
#     theo kich co: 180/240 = 0.7500          ; 90/120 = 0.7500
#
# 0.75 = 72/96 - dung ty le point / pixel o 96 DPI. Tuc SCTS doc con so minh gui nhu PIXEL,
# roi quy ra point. Minh dang gui POINT.
#
# Phan du sau khi bo ty le la HANG SO, giong nhau den hai chu so thap phan tren ca hai chu
# ky - va hai chu ky co x lech nhau 92 diem, y lech 115 diem:
#     dx = 19.95 va 19.95      dy = 47.74 va 47.74
#
# Da loai tru kha nang "SCTS bo qua toa do minh gui, dat theo vung cua sign-template": neu
# vay phan du da khac nhau giua hai chu ky, chu khong trung khit. Cung da loai tru "SCTS co
# ca trang lai": doc lai PDF da ky thi dong chu tieu de van nam nguyen o (60, 760) voi co
# chu 14 va MediaBox van 595x842 - trang khong bi dung toi, chi rieng toa do chu ky.
#
# [TEMP-WORKAROUND 2026-09-02 — hieu chinh tu do dac, chua co xac nhan cua SCTS]
# Rui ro: neu SCTS sua phia ho thi phep bu nay lam lech NGUOC LAI. Vi vay con so nam o mot
# cho duy nhat, co ten, va co test ghim lai phep do - doi lai chi la sua ba con so.
# Viec dung: hoi SCTS API nhan don vi nao (point hay pixel 96 DPI) roi bo hang so nay di.
# Xem BACKLOG_ESIGN.md muc "Toa do chu ky".
#
#: Ty le SCTS ap len moi con so toa do minh gui (do duoc, = 72/96).
SCTS_SCALE = 0.75
#: Do lech hang so con lai sau khi bo ty le, tinh bang POINT tren trang PDF.
SCTS_OFFSET_X = 19.95
SCTS_OFFSET_Y = 47.74


def to_provider_box(x_pt, y_pt, w_pt, h_pt):
    """Doi mot o ky tu POINT-tren-trang sang he don vi SCTS thuc su dung.

    Nghich dao cua phep bien doi do duoc o tren:  ket qua = SCTS_SCALE * gui + offset
    nen                                            gui    = (mong muon - offset) / SCTS_SCALE

    Kich co khong co offset (do dac: 180/240 va 90/120 deu dung 0.75), nen chi chia ty le.
    """
    return {
        "x": round((float(x_pt) - SCTS_OFFSET_X) / SCTS_SCALE, 2),
        "y": round((float(y_pt) - SCTS_OFFSET_Y) / SCTS_SCALE, 2),
        "w": int(round(float(w_pt) / SCTS_SCALE)),
        "h": int(round(float(h_pt) / SCTS_SCALE)),
    }


def from_provider_box(x, y, w, h):
    """Phep bien doi SCTS ap len con so minh gui - dung de KIEM, khong dung khi gui.

    Co mat de test co the hoi "gui cai nay thi no ra dau" bang chinh phep do, thay vi lap
    lai cong thuc trong test (test lap lai cong thuc thi no tu tra loi lay minh).
    """
    return {
        "x": SCTS_SCALE * float(x) + SCTS_OFFSET_X,
        "y": SCTS_SCALE * float(y) + SCTS_OFFSET_Y,
        "w": SCTS_SCALE * float(w),
        "h": SCTS_SCALE * float(h),
    }


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
        from ecentric_workspace.platform.esign import netguard
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
        """Persist through the ORM so the Password field is encrypted (controller rule).

        HAI LOP BAO VE, vi day chi la CACHE va no da tung lam hong mot lan duyet that.

        02/09/2026, 03:25:50 va 03:25:56 - Provider Settings la MOT ban ghi dung chung cho
        moi chan ky. Hai cong viec ky chay cach nhau sau giay cung lam moi token, ca hai cung
        `get_doc` roi cung `save`, va Frappe nem

            EC-DSPS-00001 has been modified after you have opened it. Please refresh.

        Nguoi duyet nhan dung cau do giua man hinh phe duyet chi tien, va phai tai lai trang.
        Mot lan ghi bo nho dem hong KHONG duoc phep lam hong viec ky.

        1. Khoa hang truoc khi doc: hai tien trinh nhu tren se noi duoi nhau thay vi dam nhau,
           nen truong hop kia gan nhu khong con xay ra.
        2. Neu van hong: ghi log roi DI TIEP. Token da nam trong bo nho cho lan goi nay, viec
           ky van chay binh thuong; lan sau chi phai dang nhap lai mot lan nua. Danh doi dung
           chieu: cham hon mot chut > chan mot chu ky.
        """
        if not self._name:
            return
        try:
            mins = int(expires_in_minutes or 0)
        except (TypeError, ValueError):
            mins = 0
        try:
            frappe.db.get_value(SETTINGS_DT, self._name, "name", for_update=True)
            doc = frappe.get_doc(SETTINGS_DT, self._name)
            doc.token_cache = token
            doc.token_expires_at = add_to_date(now_datetime(), minutes=mins) if mins else None
            doc.save(ignore_permissions=True)
            # keep the in-memory settings snapshot coherent for the rest of this call
            if isinstance(self.settings, dict):
                self.settings["token_expires_at"] = doc.token_expires_at
        except Exception:
            frappe.log_error(frappe.get_traceback(), "esign scts token cache write")

    # -- session --------------------------------------------------------------
    def authenticate(self):
        """Force a fresh login and cache the token. Returns a SAFE summary (no token). The
        SCTS login contract requires Site, read from Provider Settings.site; a blank Site
        fails closed BEFORE any network call. Credentials are never logged."""
        site = _sval(self.settings, "site")
        username = _sval(self.settings, "username")
        password = self._password("password")
        if not site:
            raise ProviderError("scts_site_missing",
                                "SCTS Site (Provider Settings.site) is not configured",
                                retryable=False)
        if not username or not password:
            raise ProviderError("scts_credentials_missing",
                                "SCTS username/password not configured", retryable=False)
        raw = self._client.login(site, username, password)
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
        """Usability. An explicit isActive/active flag wins; an explicit status may
        activate or deactivate. eContract (2026-08): GetSignatures returns ONLY the user's
        usable signatures and carries NO activity/status fields at all - in that case
        presence in the list is the usability evidence, so no-evidence => ACTIVE.
        Any EXPLICIT negative (false/0/no, inactive/revoked/expired) still fails closed."""
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
        if not st:
            return True   # eContract: no flag, no status -> presence in the list = usable
        return st in ("active", "valid", "usable")  # inactive/revoked/expired -> False

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

    def signature_image(self, provider_user_id, signature_id):
        """Base64 PNG of ONE owned signature (size preview in the placement drawer).
        Read-only GetSignatures; returns None when not found. Never logged."""
        img, _name = self.signature_image_and_name(provider_user_id, signature_id)
        return img

    def signature_image_and_name(self, provider_user_id, signature_id):
        """Anh + TEN HIEN THI cua mot chu ky. Giu lai cho cho goi cu; doc qua signature_record."""
        rec = self.signature_record(provider_user_id, signature_id)
        if not rec:
            return None, None
        return rec.get("base64Image"), rec.get("name")

    def signature_record(self, provider_user_id, signature_id):
        """Ban ghi chu ky THO tu GetSignatures - toan bo truong, khong cat gon.

        Vi sao can nguyen ban ghi: capture 28/08 21:35 cho thay signatureInfo cua portal
        mang TAM truong (id, name, image, signerId, hsmId, companyId, signType, signToken),
        va tat ca deu nam san trong GetSignatures. Cat gon o day la tu bit mat minh -
        phien ban chi tra (image, name) da che mat hsmId sau ngay lien.
        """
        raw = self._with_auth(lambda t: self._client.get_signatures(provider_user_id, t))
        for x in self._as_list(raw):
            if str(x.get("id")) == str(signature_id):
                return x
        return None

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

    def transition_with_recipients(self, instance_id, provider_user_id, to_users, config,
                                   signature_id, signature_name=None, comment=None):
        """POST /api/Workflow/transition - the governed path: names WHO acts next.

        `config` comes from the profile (transition id/name/action code/sign type); this
        adapter never invents those values. Same async ACCEPTED semantics as
        approve_and_sign: a 2xx means queued, not signed.
        """
        # Anh chu ky la truong BAT BUOC cua eContract o buoc nay. Lay hong thi van gui di
        # va de provider tu tu choi, chu khong tu suy ra ket luan thay no.
        rec = None
        try:
            rec = self.signature_record(provider_user_id, signature_id)
        except Exception:
            rec = None
        rec = rec or {}
        image = rec.get("base64Image")
        provider_name = rec.get("name")
        # signatureInfo DAY DU nhu portal gui (capture bung het 28/08 21:35). Nam lenh
        # transition truoc do deu 2xx-roi-im; chung chi mang {id, name, image} trong khi
        # portal mang them signerId + hsmId (chung thu HSM) + companyId + signType +
        # signToken. Khong co chung thu thi khong tao duoc chu ky - day la khac biet cuoi
        # cung con lai giua hai payload. Moi gia tri doc tu GetSignatures, khong bia.
        extra = {
            "signerId": rec.get("signerId") or provider_user_id,
            "hsmId": rec.get("hsmCertId") or rec.get("hsmId") or "",
            "companyId": rec.get("companyId") or "",
            "signType": config.get("sign_type") or "",
            "signToken": 0,
        }
        raw = self._with_auth(lambda t: self._client.transition(
            instance_id, provider_user_id, to_users,
            config.get("transition_id"), config.get("transition_name"),
            config.get("process_action"), config.get("sign_type"),
            signature_id,
            signature_name or provider_name or config.get("sign_type") or "",
            comment, t, signature_image=image, signature_extra=extra))
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

    # -- live workflow state --------------------------------------------------
    def available_transitions(self, instance_id, provider_user_id):
        """What this user can actually do on this document RIGHT NOW, straight from the
        provider. Returns [] when the call fails - the caller keeps its old path and records
        why, rather than acting on a guess."""
        raw = self._with_auth(
            lambda t: self._client.get_workflow_instance(instance_id, provider_user_id, t))
        data = raw.get("data") if isinstance(raw, dict) and isinstance(raw.get("data"), dict) else raw
        if not isinstance(data, dict):
            return []
        out = []
        for t in (data.get("availableTransitions") or []):
            if not isinstance(t, dict):
                continue
            out.append({
                "transition_id": t.get("transitionId"),
                "transition_name": t.get("transitionName"),
                "process_action": t.get("processAction"),
                "sign_type": t.get("signType"),
                "requires_signature": bool(t.get("isSigned")),
                "transition_type": t.get("transitionType"),
                "to_state": t.get("toState"),
                "terminal": bool(t.get("forceStop")) or str(t.get("toState") or "") == "STOP",
                "all_required": bool(t.get("isAllRequired")),
            })
        return out

    def eligible_recipients(self, instance_id, transition_id, provider_user_id):
        """ID cua nhung nguoi eContract CHAP NHAN cho buoc nay. None = khong hoi duoc.

        Phan biet ro "hoi duoc va danh sach RONG" (-> set()) voi "khong hoi duoc" (-> None).
        Hai cai do dan toi hai quyet dinh khac han o tang tren: mot cai la bang chung, cai
        kia la thieu thong tin.
        """
        try:
            raw = self._with_auth(lambda t: self._client.users_for_transition(
                instance_id, transition_id, provider_user_id, t))
        except Exception as exc:
            # NOI RO vi sao khong hoi duoc, dung nuot.
            #
            # Day la lop bao ve chan viec gui mot lenh ma eContract chac chan bo qua. Khi no
            # tra None, tang tren ghi `recipients_unverified: true` va GUI DAI theo chuoi cua
            # ERP. 02/09, chan ky HOF: recipients_unverified=true -> gui -> eContract nhan
            # 2xx kem ma giao dich -> 20 phut sau khong co chu ky nao -> Manual Review.
            #
            # Khong ai biet vi sao lop bao ve khong chay, vi cho nay nuot sach loi. Cung lop
            # sai da phai sua hai lan trong cung mot ngay: mot nhanh im lang, va mot cau bao
            # loi khong noi thieu ai. Mot cong cu de nhin ma tu bit mat o dong cuoi thi khong
            # phai cong cu.
            from ecentric_workspace.platform.esign.sanitize import safe_error
            self._last_eligible_error = safe_error(exc)
            frappe.log_error(
                "users_for_transition that bai (instance=%s transition=%s): %s"
                % (instance_id, transition_id, safe_error(exc)),
                "esign scts eligible_recipients")
            return None
        rows = raw
        if isinstance(raw, dict):
            for key in ("data", "items", "users", "result"):
                v = raw.get(key)
                if isinstance(v, list):
                    rows = v
                    break
                if isinstance(v, dict) and isinstance(v.get("data"), list):
                    rows = v["data"]
                    break
        if not isinstance(rows, list):
            return None
        out = set()
        for r in rows:
            if isinstance(r, dict):
                for key in ("id", "userId", "userID", "guid"):
                    if r.get(key):
                        out.add(str(r[key]))
                        break
            elif r:
                out.add(str(r))
        return out

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
        if isinstance(raw.get("data"), dict):                 # eContract: body boc trong "data"
            raw = raw.get("data")
        doc_id = raw.get("id") or raw.get("documentId") or document_id
        status = (raw.get("status") or raw.get("documentStatus") or raw.get("state")
                  or raw.get("statusName"))
        status = SctsAdapter._canon_doc_status(status)
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

    # eContract tra statusName/tinh trang ky bang TIENG VIET - canon hoa ve tap tu vung cu
    _VN_DOC_STATUS = {"hoàn thành": "completed", "hoan thanh": "completed",
                      "đang xử lý": "processing", "dang xu ly": "processing",
                      "từ chối": "rejected", "tu choi": "rejected",
                      "đã hủy": "cancelled", "da huy": "cancelled"}
    _VN_SIGN_STATUS = {"đã ký": "signed", "da ky": "signed",
                       "chưa ký": "pending", "chua ky": "pending",
                       "từ chối": "rejected", "tu choi": "rejected",
                       "trả lại": "rejected", "tra lai": "rejected"}

    @staticmethod
    def _canon_doc_status(status):
        if status is None:
            return status
        low = str(status).strip().lower()
        return SctsAdapter._VN_DOC_STATUS.get(low, status)

    @staticmethod
    def _norm_signer(s):
        if not isinstance(s, dict):
            return {"user_id": None, "signature_id": None, "status": "pending",
                    "signed_at": None, "is_external": False}
        raw_status = str(s.get("status") or s.get("signStatus") or "").strip().lower()
        raw_status = SctsAdapter._VN_SIGN_STATUS.get(raw_status, raw_status)
        is_signed = s.get("isSigned")
        if is_signed is True or raw_status in ("signed", "completed", "done", "success"):
            norm = "signed"
        elif raw_status in ("rejected", "declined", "returned", "failed"):
            norm = "rejected"
        else:
            norm = "pending"
        return {"user_id": s.get("userId") or s.get("signerId") or s.get("signerUserId"),
                "signature_id": s.get("signatureId") or s.get("signerSignatureId"),
                "display_name": s.get("user") or s.get("fullName"),
                "email": (str(s.get("email") or "").strip().lower() or None),
                # eContract noi ro moi o ky thuoc VAI TRO nao ("Ke toan truong", "CEO"...)
                # va o do thuoc loai gi ("Ky chinh" / "Tham gia"). Ban chuan hoa cu vut het,
                # chi giu email + status - nen mot o CHUA AI KY hien ra la "(chua gan)" vo
                # danh, khong biet cua cap nao. Dem 27/08 mat nhieu gio vi khong doc duoc
                # dieu nay, trong khi provider da noi san.
                "role": s.get("role"),
                "role_text": s.get("roleText"),
                "sign_type": s.get("signType") or s.get("signTypeName"),
                "status": norm,
                "signed_at": SctsAdapter._signed_at(s),
                "is_external": bool(s.get("isExternal") or s.get("external"))}

    @staticmethod
    def _signed_at(s):
        """Moc ky, GHEP ngay voi gio khi provider gui rieng hai truong.

        eContract tra `date` VA `time` tren tung dong nguoi ky. Ban truoc chi doc `time` -
        mot dong ho tran nhu "11:48" - roi de tang tren phai TU DOAN ngay. Doan sai la
        chuyen som muon: mot chu ky luc 11:48 HOM NAY, doi chieu voi mot yeu cau tao luc
        23:23 HOM QUA, se bi suy ra thanh 11:48 hom qua va bi tu choi la "chu ky co truoc
        yeu cau". Ca mot heuristic doan ngay ton hai dem, trong khi provider da noi san ngay
        o ngay dong ben canh.
        """
        for key in ("signedAt", "signedDate", "signTime"):
            v = s.get(key)
            if v and str(v).strip() not in ("", "Chưa có"):
                return v
        t = str(s.get("time") or "").strip()
        if t in ("", "Chưa có"):
            return None
        d = str(s.get("date") or "").strip()
        if d and d not in ("Chưa có",):
            return "%s %s" % (d, t)
        return t

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
        placements = package_ctx.get("placements") or []
        # eContract: Signatures are nested INSIDE each Documents[] entry, and EVERY signature
        # MUST carry the signatureId of a sign AREA defined by the workflow's sign template
        # (probed live 2026-08-23: AddDocument 400s without it). The area list comes from
        # ConvertPdfFile; we match each placement to an area by its role TITLE (the governed
        # scts_role_title from profile levels / requester_role_title). Fail-closed on mismatch.
        by_dsf = {}
        for pl in placements:
            by_dsf.setdefault(pl.get("signature_file"), []).append(pl)
        # MOI tep ky duoc phai co bang vung ky CUA RIENG NO.
        #
        # Ban dau chi goi ConvertPdfFile cho tep signable DAU TIEN roi ap bang vung do cho
        # MOI tep. Mot tep thi khong lo ra; hai tep tro len la moi chu ky tren tep thu hai
        # deu mang signatureId cua vung thuoc tep thu nhat - sai, va sai IM LANG. Day la lo
        # QC #8 ghi ngay 28/08, va no chan dung ke hoach ky Payment Request kem Purchase
        # Request trong mot lan.
        areas_by_file = {}
        if placements:
            for f in files:
                if not f.get("can_be_signed"):
                    continue
                key = f.get("file_dsf")
                if key in areas_by_file:
                    continue
                defs = self._with_auth(lambda t: self._client.convert_pdf_file(
                    package_ctx.get("workflow_definition_id"),
                    self._b64(f.get("content")), t))
                areas_by_file[key] = {self._norm_title(d.get("title")): d
                                      for d in (defs or []) if isinstance(d, dict)}

        def _area_for(pl, file_dsf):
            areas = areas_by_file.get(file_dsf) or {}
            key = self._norm_title(pl.get("scts_role_title"))
            d = areas.get(key)
            if not d or not d.get("signatureId"):
                raise ProviderError(
                    "scts_signature_area_unmatched",
                    "no sign-template area titled %r on file %r (available: %s)"
                    % (pl.get("scts_role_title"), file_dsf,
                       ", ".join(sorted(a.get("title") or "?" for a in areas.values()))),
                    retryable=False)
            return d
        documents = []
        for f in files:
            b64 = self._b64(f.get("content"))
            sigs = []
            for pl in by_dsf.get(f.get("file_dsf"), []):
                d = _area_for(pl, f.get("file_dsf"))
                # ERP canonical geometry is TOP-left-origin points; SCTS expects PDF
                # coordinates (BOTTOM-left origin, "Toa do diem dat chu ky (PDF Coordinate)").
                # Live evidence 2026-08-23: without the flip the signature rendered mirrored
                # vertically. Lower-left corner: y_pdf = page_height - y_top - height.
                # KHONG doan chieu cao trang. Ban truoc lay 792 (Letter) khi khong doc
                # duoc; giay A4 cao 842, nen moi chu ky tren tai lieu A4 bi day xuong 50
                # diem - dung kieu "lech" ma khong ai chi ra duoc vi sao. Doan mot con so
                # de dat chu ky len chung tu that la sai lang: tha tu choi.
                if not pl.get("page_height"):
                    raise ProviderError(
                        "scts_page_height_unknown",
                        "khong doc duoc chieu cao trang %s cua tep %s - khong dat duoc vi "
                        "tri chu ky chinh xac" % (pl.get("page_index"), f.get("name")),
                        retryable=False)
                page_h = float(pl.get("page_height"))
                x = float(pl.get("x") or 0)
                h = float(pl.get("height") or 0)
                y_pdf = max(0.0, page_h - float(pl.get("y") or 0) - h)
                # Doi sang he don vi ma SCTS THUC SU dung - xem `to_provider_box`.
                bx = to_provider_box(x, y_pdf, float(pl.get("width") or 0), h)
                sigs.append({
                    "signatureId": d.get("signatureId"),
                    "title": d.get("title"),
                    "role": d.get("role") or "",
                    "signatureType": "position",
                    "keyword": "",
                    "margin": 0,
                    "canBeSigned": True,
                    "added": 1,
                    "isPlaced": True,
                    "pageIndex": int(pl.get("page_index") or 1),
                    "x": bx["x"], "y": bx["y"],
                    "Llx": bx["x"], "Lly": bx["y"],
                    "Width": bx["w"],
                    "Height": bx["h"],
                })
            documents.append({
                "FileName": f.get("name"),
                "FileType": "pdf",
                "file_kind": 1 if f.get("can_be_signed") else 2,   # 1: tep chinh, 2: phu luc
                "CanBeSigned": bool(f.get("can_be_signed")),
                "uploadBct": False,
                "IsSharedWithPartner": bool(f.get("share_with_partner")),
                "PdfBase64": b64,
                "OriginalBase64": b64,
                "Signatures": sigs,
            })
        payload = {
            "docCode": package_ctx.get("doc_code"),
            "docBatchCode": package_ctx.get("doc_batch_code") or "",
            "docAmount": package_ctx.get("amount") or 0,
            "docTitle": package_ctx.get("title") or package_ctx.get("doc_code"),
            "docDescription": package_ctx.get("description") or "",
            "documentTemplateId": package_ctx.get("document_template_id") or "",
            "documentTypeId": package_ctx.get("document_type_id"),
            "workflowDefinitionId": package_ctx.get("workflow_definition_id"),
            "companyId": package_ctx.get("company_id"),
            "departmentId": package_ctx.get("department_id"),
            "deadlineDate": package_ctx.get("deadline") or "",
            "fields": package_ctx.get("fields") or [],
            "Documents": documents,
            "ExternalHandlers": [],  # external signer handlers disabled this phase
            "DocumentRefIds": [],
        }
        raw = self._with_auth(lambda t: self._client.add_document(payload, t))
        return self._normalize_create(raw, files)

    @staticmethod
    def _norm_title(t):
        return " ".join(str(t or "").split()).casefold()

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
            if not doc_id and isinstance(raw.get("data"), str) and raw.get("data").strip():
                doc_id = raw.get("data").strip()          # eContract: data = "<DocumentId>"
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
