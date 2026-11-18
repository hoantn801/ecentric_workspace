# Copyright (c) 2026, eCentric and contributors
"""Huy tai lieu tren cong ky so khi phieu ERP bi TU CHOI / HUY (18/11/2026, Hoan duyet).

Vi sao. Phieu bi tu choi / huy tren ERP thi tai lieu tuong ung tren CMC van "Dang xu ly" va nam
trong danh sach viec cua nguoi ky ke tiep (quet 18/11: 34 phieu tu choi / huy tu 15/10). Khong ai
ky sai, nhung nguoi dung thay viec rac va co the ky nham vao mot phieu da chet.

Huy tren cong KHONG LAY LAI DUOC (cong dong dau "Cancelled", destroy=1). Vi vay moi chot deu
nghieng ve "khong huy":

  * Pham vi: chi AUTO_DOCTYPES (Payment Request). Hop dong (doi tac ky, WF09) chua bat.
  * Phieu phai Rejected / Cancelled (ket thuc that: _guard_open chan moi duong mo lai).
  * Tai lieu phai DANG XU LY (danh sach CHO PHEP, khong phai danh sach cam): moi trang thai la /
    khong doc duoc / moi nguoi da ky / goi da luu PDF ky -> KHONG huy.
  * Khong co chan ky dang bay (ke ca Retryable Failure).
  * Mot khoa theo goi (CHUNG voi provider_resync - tao lai va huy khong chay chong), lay TRUOC
    lan doc dau; trong khoa doc lai goi + phieu.
  * Ghi vet + commit TRUOC khi gui; MOT lenh huy bang tai khoan tich hop; cong da nhan (2xx) ma
    doc lai chua thay huy -> KHONG gui lai, danh dau "cho xac minh" + bao ops.
  * Mo ho (mang / 5xx): luot sau DOC truoc; da huy thi chi danh dau.
  * Tu dong (`sweep`, cron */10): chi phieu ket thuc (completed_at) tu AUTO_SINCE, chi khi da co
    IT NHAT MOT lan huy that qua lenh SM duoc xac minh (tu "len co" sau lan chay tay dau tien),
    va tat duoc bang site_config ec_esign_auto_cancel_disabled. Ton dong cu: chi qua lenh SM
    (`cancel_rejected_documents`), chay thu mac dinh, chay that phai liet ke phieu.
  * Thu toi da MAX_AUTO_TRIES lenh gui; het luot -> ToDo cho ops (khong im lang).

KHONG doi trang thai phieu / goi / chan ky; chi ghi error_code cua goi (provider_document_ -> moi
nut "Duyet & Ky" tren goi do bi chan, dung nhu khi tai lieu bi huy tren cong).
"""
import time
import unicodedata

import frappe
from frappe import _
from frappe.utils import add_to_date, get_datetime, now_datetime

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign.providers import get_adapter
from ecentric_workspace.platform.esign.providers.base import ProviderError
from ecentric_workspace.platform.esign.sanitize import safe_error

PKG = "EC Digital Signature Package"
DSR = "EC Digital Signature Request"
AR = "EC Approval Request"
EVT = "EC Digital Signature Event"
SETTINGS = "EC Digital Signature Provider Settings"

NEGATIVE = ("Rejected", "Cancelled")
#: Chi loai phieu nay. Hop dong: doi tac ky + buoc duyet khong ky -> chua bat (can PO quyet).
AUTO_DOCTYPES = ("EC Payment Request",)
#: Moc tu dong: phieu KET THUC (completed_at - ghi cung luc voi trang thai khi tu choi / huy) tu
#: ngay trien khai. Truoc moc (ton dong): chi qua lenh SM sau khi nguoi xem danh sach chay thu.
AUTO_SINCE = "2026-11-18 00:00:00"
CODE = "provider_document_cancelled_by_erp"
CODE_UNVERIFIED = "provider_document_cancel_unverified"
#: Chan ky con co the gui lenh vao tai lieu -> chua huy (cho luot sau).
BLOCKING = ("Prepared", "Queued", "Provider Accepted", "Verifying", "Signed",
            "Retryable Failure")
ACTIVE_PKG = ("Active", "Locked", "Provider Created", "Provider Creating",
              "Provider Create Failed")
SOURCE_AUTO = "auto_cancel"
SOURCE_SM = "sm_cancel"
MAX_AUTO_TRIES = 3          # so LENH HUY da gui (khong dem lan doc / lan bo qua)
MAX_POLL_FAILS = 6          # loi doc tam thoi lien tiep (~1 gio) -> dung + bao ops
RETRY_MINUTES = 30
AUTO_BATCH = 10             # so goi CO GOI CONG moi luot cron
SM_MAX_LIVE = 3             # chay that qua lenh SM: toi da 3 phieu / lan (request web ~120s)
SWEEP_BUDGET_SECONDS = 120  # cron khong BAT DAU goi moi sau moc nay (RQ timeout 300s)
POLL_FAIL_MIN_AGE_HOURS = 24
VERIFY_WAITS = (2, 3, 5, 8)  # doc lai sau lenh huy (cong co the dat destroy tre)
ARM_ENVIRONMENT = "Production"
LOCK_SECONDS = 600
TODO_MARKER = "[EC-ESIGN-AUTO-CANCEL]"

_MSG = {"Rejected": "bị từ chối", "Cancelled": "bị huỷ"}


class _Stop(Exception):
    pass


def _canon(status):
    """Trang thai tai lieu -> 'processing' / 'cancelled' / 'completed' / 'rejected' / 'unknown'.
    Chu tieng Viet co dau / khong dau / NFD / 'huỷ' lan 'hủy'. La -> unknown (KHONG huy)."""
    s = unicodedata.normalize("NFC", str(status or "")).strip().lower()
    s2 = "".join(ch for ch in unicodedata.normalize("NFD", s)
                 if unicodedata.category(ch) != "Mn").replace("đ", "d")
    if s in ("processing", "pending", "in_progress") or s2 in ("dang xu ly",):
        return "processing"
    if s == "cancelled" or s2 in ("da huy",):
        return "cancelled"
    if s in ("completed", "signed", "done") or s2 in ("hoan thanh", "da ket thuc"):
        return "completed"
    if s == "rejected" or s2 in ("tu choi", "da tu choi"):
        return "rejected"
    return "unknown"


def _state_status(state):
    """Trang thai chuan cua tai lieu: co destroy (identity.destroyed) uu tien hon chu."""
    if (getattr(state, "identity", None) or {}).get("destroyed"):
        return "cancelled"
    return _canon(getattr(state, "status", None))


def _transient(code):
    """Loi doc TAM THOI (mang / 5xx). 401/403 / 4xx / payload la: ben vung (khong doc lai mai)."""
    c = str(code or "")
    return c == "scts_network_error" or c.startswith(("scts_server_error",
                                                      "scts_document_error_5"))


def _ar(ar_name):
    if not ar_name:
        return None
    return frappe.db.get_value(AR, ar_name, ["name", "approval_status", "completed_at"],
                               as_dict=True)


def _prior_sent(pkg_name):
    return bool(frappe.get_all(EVT, filters={"package": pkg_name, "event_type": "PollTick",
                                             "verification_result": "cancel_sent"},
                               fields=["name"], limit_page_length=1))


def _live_legs(pkg_name):
    return frappe.get_all(DSR, filters={"package": pkg_name, "status": ["in", list(BLOCKING)]},
                          fields=["name", "status"], limit_page_length=20)


def _settings(provider, environment):
    return frappe.db.get_value(SETTINGS, {"provider": provider, "environment": environment},
                               "*", as_dict=True)


def _pkg(pkg_name):
    return frappe.db.get_value(PKG, pkg_name, ["name", "status", "provider", "environment",
                                               "scts_document_id", "approval_request",
                                               "business_doctype", "business_name",
                                               "error_code", "signed_bundle_complete"],
                               as_dict=True)


def _check_pkg(pkg, ar):
    """Ly do KHONG duoc huy (chuoi) hoac None - phan doc ERP, khong goi cong."""
    if not pkg:
        return "no_package"
    if pkg.business_doctype not in AUTO_DOCTYPES:
        return "doctype_not_enabled:%s" % pkg.business_doctype
    if pkg.status not in ACTIVE_PKG:
        return "package_status:%s" % pkg.status
    if not pkg.scts_document_id:
        return "no_provider_document"
    if str(pkg.error_code or "").startswith("provider_document_"):
        return "already_marked:%s" % pkg.error_code
    if int(pkg.signed_bundle_complete or 0):
        return "signed_bundle_complete"
    if not ar or ar.approval_status not in NEGATIVE:
        return "request_not_rejected:%s" % (ar.approval_status if ar else None)
    live = _live_legs(pkg.name)
    if live:
        return "live_legs:%s" % ",".join("%s/%s" % (x.name, x.status) for x in live)
    return None


def _mark(pkg, code, how, ar_status, source, detail=None):
    if code == CODE_UNVERIFIED:
        msg = ("Phiếu trên ERP %s - đã gửi lệnh huỷ tài liệu trên CMC nhưng chưa xác minh được; "
               "ops kiểm tra trên cổng." % _MSG.get(ar_status, "đã kết thúc"))
    elif how == "cancelled_on_portal":
        msg = ("Phiếu trên ERP %s - tài liệu trên CMC đã bị huỷ trên cổng."
               % _MSG.get(ar_status, "đã kết thúc"))
    else:
        msg = ("Phiếu trên ERP %s - tài liệu ký số trên CMC đã được huỷ theo."
               % _MSG.get(ar_status, "đã kết thúc"))
    frappe.db.set_value(PKG, pkg.name, {"error_code": code, "error_message": msg})
    events.emit("Cancelled" if code == CODE else "Failed", package=pkg.name,
                erp_actor=frappe.session.user, verification_result="%s:%s" % (code, how),
                request_meta={"source": source, "document_id": pkg.scts_document_id,
                              "approval_status": ar_status, "how": how, "detail": detail,
                              "environment": pkg.environment})


def _alert(pkg_name, reason):
    """Mot ToDo mo cho ops / goi (khong trung)."""
    try:
        if frappe.db.exists("ToDo", {"reference_type": PKG, "reference_name": pkg_name,
                                     "status": "Open",
                                     "description": ["like", "%" + TODO_MARKER + "%"]}):
            return
        frappe.get_doc({"doctype": "ToDo", "allocated_to": "Administrator",
                        "reference_type": PKG, "reference_name": pkg_name,
                        "description": "%s esign: chua huy duoc tai lieu tren cong - %s"
                                       % (TODO_MARKER, reason),
                        "assigned_by": "Administrator"}).insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign provider_cancel alert")


def _lock(pkg_name):
    # CHUNG khoa voi provider_resync: tao lai tai lieu (pha 2 go error_code) va huy khong duoc
    # chay chong len nhau.
    key = "esign:provider_resync:%s" % pkg_name
    try:
        ok = frappe.cache().set(key, "1", nx=True, ex=LOCK_SECONDS)
    except Exception:
        ok = False
    return key if ok else None


def _unlock(key):
    try:
        frappe.cache().delete(key)
    except Exception:
        pass


def cancel_one(pkg_name, reason=None, dry_run=True, source=SOURCE_SM):
    """Huy tai lieu cua MOT goi. Tra dong ket qua (khong nem loi nghiep vu).

    CANH BAO: chay that se frappe.db.rollback() ngay sau khi lay khoa (bo snapshot) - nguoi goi
    PHAI commit moi thu minh ghi truoc khi goi ham nay."""
    pkg = _pkg(pkg_name)
    row = {"package": pkg_name, "business_name": pkg.business_name if pkg else None,
           "document_id": pkg.scts_document_id if pkg else None}
    why = _check_pkg(pkg, _ar(pkg.approval_request) if pkg else None)
    if why:
        return dict(row, result="stop", reason=why)
    key = None if dry_run else _lock(pkg.name)
    if not dry_run and not key:
        return dict(row, result="stop", reason="locked")
    try:
        if key:
            # Trong khoa: BO snapshot cu (REPEATABLE READ - lan doc dau cua transaction da lap
            # snapshot truoc khi khoa; chua ghi gi nen rollback an toan) roi doc lai TAT CA.
            frappe.db.rollback()
            pkg = _pkg(pkg_name)
            ar = _ar(pkg.approval_request) if pkg else None
            why = _check_pkg(pkg, ar)
            if why:
                return dict(row, result="stop", reason=why)
        else:
            ar = _ar(pkg.approval_request)
        row["approval_status"] = ar.approval_status
        settings = _settings(pkg.provider, pkg.environment)
        if not settings or not int(settings.get("integration_enabled") or 0):
            return dict(row, result="stop", reason="integration_closed")
        adapter = get_adapter(settings)
        try:
            state = adapter.poll_status(pkg.scts_document_id)
        except ProviderError as e:
            # 404 co the chi la "token khong thay" (QC 16/11) - KHONG coi la da huy; nguoi xem.
            return dict(row, result="stop", reason="poll_failed:%s" % e.code, polled=True,
                        transient=_transient(e.code))
        row["polled"] = True
        status = _state_status(state)
        signers = getattr(state, "signers", None) or []
        signed = len([s for s in signers if str((s or {}).get("status") or "").lower()
                      == "signed"])
        row.update(provider_status=status, provider_signed=signed, provider_signers=len(signers),
                   creator=(getattr(state, "identity", None) or {}).get("creator_email"))
        if status == "cancelled":
            if dry_run:
                return dict(row, result="would_mark", reason="already_cancelled_on_portal")
            # Lan truoc ERP da gui lenh (mo ho) -> khong do cho "nguoi tren cong huy".
            how = "cancelled_after_prior_send" if _prior_sent(pkg.name) else "cancelled_on_portal"
            _mark(pkg, CODE, how, ar.approval_status, source)
            frappe.db.commit()
            return dict(row, result="marked", reason=how)
        if status != "processing":
            # Danh sach CHO PHEP: xong / tu choi / la -> KHONG BAO GIO huy.
            return dict(row, result="stop", reason="provider_status:%s" % status)
        if not signers:
            return dict(row, result="stop", reason="no_signers")      # khong biet -> khong huy
        if signed >= len(signers):
            return dict(row, result="stop", reason="all_signers_signed")
        if not hasattr(adapter, "cancel_document"):
            return dict(row, result="stop", reason="adapter_no_cancel")
        if dry_run:
            return dict(row, result="would_cancel")
        why_txt = (reason or "Phiếu ERP %s %s" % (pkg.business_name,
                                                  _MSG.get(ar.approval_status,
                                                           "đã kết thúc")))[:300]
        events.emit("PollTick", package=pkg.name, erp_actor=frappe.session.user,
                    verification_result="cancel_sent",
                    request_meta={"source": source, "document_id": pkg.scts_document_id,
                                  "approval_status": ar.approval_status, "ly_do": why_txt})
        frappe.db.commit()               # vet "da gui lenh huy" ton tai ke ca khi buoc sau hong
        err, acked = None, False
        try:
            adapter.cancel_document(pkg.scts_document_id, why_txt)
            acked = True
        except ProviderError as e:
            err = e
        after = "not_polled"
        definite = bool(err and not getattr(err, "ambiguous", False))
        # Cong tu choi CHAC CHAN: doc lai mot lan, khong cho (khong ton thoi gian).
        for wait in ((0,) if definite else VERIFY_WAITS):
            if wait:
                time.sleep(wait)
            try:
                after = _state_status(adapter.poll_status(pkg.scts_document_id))
            except ProviderError as e:
                after = "poll_failed:%s" % e.code
            if after == "cancelled":
                break
        if after == "cancelled":
            # "cancelled" (co len co tu dong) CHI khi cong DA NHAN lenh cua ERP; doc lai thay huy
            # sau mot lenh bi tu choi / mo ho -> nhan khac.
            _mark(pkg, CODE, "cancelled" if acked else "cancelled_read_back", ar.approval_status,
                  source, detail=("acked" if acked else (err.code if err else "?")))
            frappe.db.commit()
            return dict(row, result="cancelled")
        if acked:
            # Cong DA NHAN lenh (2xx) ma doc lai chua thay huy: KHONG gui lai (lenh khong lay lai
            # duoc). Danh dau cho xac minh + bao ops (QC 18/11).
            _mark(pkg, CODE_UNVERIFIED, "acked_not_cancelled", ar.approval_status, source,
                  detail="after=%s" % after)
            _alert(pkg.name, "cong da nhan lenh huy nhung doc lai: %s" % after)
            frappe.db.commit()
            return dict(row, result="unverified", after=after)
        events.emit("Failed", package=pkg.name, erp_actor=frappe.session.user,
                    error_summary=safe_error(err) if err else "cancel_failed",
                    verification_result="cancel_failed:%s" % (err.code if err else "?"),
                    request_meta={"source": source, "document_id": pkg.scts_document_id,
                                  "after": after,
                                  "ambiguous": bool(err and getattr(err, "ambiguous", False))})
        frappe.db.commit()
        return dict(row, result="failed", reason=err.code if err else "cancel_failed",
                    after=after)
    finally:
        if key:
            _unlock(key)


def _negative_requests(include_before):
    filters = {"approval_status": ["in", list(NEGATIVE)],
               "reference_doctype": ["in", list(AUTO_DOCTYPES)]}
    if not include_before:
        filters["completed_at"] = [">=", AUTO_SINCE]
    return [r.name for r in frappe.get_all(AR, filters=filters, fields=["name"],
                                           limit_page_length=0)]


def candidates(include_before=False, business_names=None):
    """Goi con tai lieu + chua danh dau chet, cua phieu Rejected / Cancelled. Chi doc."""
    ars = _negative_requests(include_before)
    if not ars:
        return []
    filters = {"approval_request": ["in", ars], "status": ["in", list(ACTIVE_PKG)],
               "scts_document_id": ["is", "set"],
               "business_doctype": ["in", list(AUTO_DOCTYPES)]}
    if business_names:
        filters["business_name"] = ["in", list(business_names)]
    rows = frappe.get_all(PKG, filters=filters,
                          fields=["name", "business_name", "error_code"],
                          order_by="creation asc", limit_page_length=0)
    return [r for r in rows if not str(r.error_code or "").startswith("provider_document_")]


def _sent_tries(pkg_name):
    """(so LENH HUY da gui - MOI nguon, ke ca lenh SM; lan gan nhat)."""
    rows = frappe.get_all(EVT, filters={"package": pkg_name, "event_type": "PollTick",
                                        "verification_result": "cancel_sent"},
                          fields=["creation"], order_by="creation desc", limit_page_length=50)
    return len(rows), (rows[0].creation if rows else None)


def _poll_fails(pkg_name):
    """(so lan doc loi tam thoi, lan loi DAU TIEN)."""
    rows = frappe.get_all(EVT, filters={"package": pkg_name, "event_type": "PollTick",
                                        "verification_result": ["like", "cancel_poll_failed:%"]},
                          fields=["creation"], order_by="creation asc", limit_page_length=50)
    return len(rows), (rows[0].creation if rows else None)


def _skipped(pkg_name):
    return bool(frappe.get_all(EVT, filters={"package": pkg_name, "event_type": "PollTick",
                                             "verification_result": ["like", "cancel_skip:%"]},
                               fields=["name"], limit_page_length=1))


def auto_armed():
    """Tu dong chi chay khi: khong bi tat (site_config) VA da co mot lan huy that qua lenh SM duoc
    xac minh (chung minh tai khoan tich hop huy duoc va doc lai thay destroy - QC 18/11)."""
    try:
        if int(frappe.conf.get("ec_esign_auto_cancel_disabled") or 0):
            return False
    except Exception:
        return False
    return bool(frappe.get_all(EVT, filters=[
        ["event_type", "=", "Cancelled"],
        ["verification_result", "=", CODE + ":cancelled"],          # cong DA NHAN lenh ERP
        ["request_meta", "like", '%"source": "' + SOURCE_SM + '"%'],
        ["request_meta", "like", '%"environment": "' + ARM_ENVIRONMENT + '"%']],
        fields=["name"], limit_page_length=1))


def _skip(pkg_name, reason, alert=True):
    """Dung vi ly do BEN VUNG: ghi mot lan (cron bo qua goi nay tu do) + bao ops mot lan."""
    events.emit("PollTick", package=pkg_name,
                verification_result="cancel_skip:%s" % str(reason)[:100],
                request_meta={"source": SOURCE_AUTO})
    if alert:
        _alert(pkg_name, str(reason)[:120])


#: Dung ma KHONG can nguoi xem (tai lieu da ra khoi danh sach viec / da xu ly o noi khac).
_QUIET = ("provider_status:completed", "provider_status:rejected", "all_signers_signed",
          "already_marked", "package_status", "signed_bundle_complete",
          "request_not_rejected", "doctype_not_enabled", "no_provider_document")
#: Dung TAM - luot sau thu lai, khong ghi gi.
_RETRY_LATER = ("live_legs", "locked", "integration_closed")


def sweep():
    """Cron */10. Kill switch esign (ec_esign_scheduler_disabled) + ec_esign_auto_cancel_disabled."""
    from ecentric_workspace.platform.esign import tasks
    if tasks._disabled() or not auto_armed():
        return
    started = time.time()
    done = 0
    for c in candidates(include_before=False):
        if done >= AUTO_BATCH or time.time() - started > SWEEP_BUDGET_SECONDS:
            break
        try:
            if _skipped(c.name):
                continue
            n, last = _sent_tries(c.name)
            if n >= MAX_AUTO_TRIES:
                _skip(c.name, "retries_exhausted:%d" % n)
                frappe.db.commit()
                continue
            if last and get_datetime(last) > add_to_date(now_datetime(),
                                                         minutes=-RETRY_MINUTES):
                continue
            res = cancel_one(c.name, dry_run=False, source=SOURCE_AUTO)
            if res.get("polled"):
                done += 1                    # chi dem goi CO goi cong (khong de goi dung chiem cho)
            reason = str(res.get("reason") or "")
            if res.get("result") == "stop":
                if res.get("transient"):
                    events.emit("PollTick", package=c.name,
                                verification_result="cancel_poll_failed:%s" % reason[:80],
                                request_meta={"source": SOURCE_AUTO})
                    k, first = _poll_fails(c.name)
                    if k >= MAX_POLL_FAILS and first and get_datetime(first) < add_to_date(
                            now_datetime(), hours=-POLL_FAIL_MIN_AGE_HOURS):
                        _skip(c.name, "poll_failed_repeatedly:%s" % reason[:80])
                    frappe.db.commit()
                    break                    # cong dang loi: dung ca luot (khong tinh loi cho goi khac)
                if not reason.startswith(_RETRY_LATER):
                    _skip(c.name, reason, alert=not reason.startswith(_QUIET))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "esign provider_cancel.sweep %s" % c.name)
            try:
                frappe.db.commit()           # giu Error Log (cancel_one sau se rollback)
            except Exception:
                pass


def cancel_rejected_documents(dry_run=True, business_names=None, include_before=True,
                              reason=None):
    """Lenh SM (qua api): liet ke / huy tai lieu cua phieu da tu choi / huy. Chay thu mac dinh.
    Chay that PHAI liet ke phieu (toi da SM_MAX_LIVE) - khong huy ca danh sach mot luc."""
    if not dry_run:
        if not business_names:
            frappe.throw(_("Chạy thật phải liệt kê mã phiếu (business_names)."))
        if len(business_names) > SM_MAX_LIVE:
            frappe.throw(_("Chạy thật tối đa {0} phiếu mỗi lần.").format(SM_MAX_LIVE))
    rows = []
    cands = candidates(include_before=include_before, business_names=business_names)
    for c in cands:
        try:
            rows.append(cancel_one(c.name, reason=reason, dry_run=dry_run, source=SOURCE_SM))
        except Exception as e:
            if not dry_run:
                frappe.db.rollback()
            rows.append({"package": c.name, "business_name": c.business_name,
                         "result": "error", "reason": "%s: %s" % (type(e).__name__,
                                                                  str(e)[:120])})
    if business_names:
        seen = {c.business_name for c in cands}
        for b in business_names:
            if b not in seen:
                rows.append({"business_name": b, "result": "not_candidate",
                             "reason": "khong phai phieu tu choi/huy con tai lieu"})
    summary = {}
    for r in rows:
        summary[r.get("result")] = summary.get(r.get("result"), 0) + 1
    return {"dry_run": bool(dry_run), "count": len(rows), "summary": summary, "rows": rows,
            "auto_armed": auto_armed()}


def resolve_unverified(pkg_name, reason):
    """SM: goi dang provider_document_cancel_unverified -> DOC lai cong (CHI DOC, khong gui lenh).
    Da huy -> ghi CODE + su kien. Chua huy -> go moc (kem ly do, co vet) de lenh SM / cron xu ly
    lai tu dau (luc do van doc truoc khi gui)."""
    reason = (reason or "").strip()
    if len(reason) < 10:
        frappe.throw(_("Bắt buộc nêu lý do (tối thiểu 10 ký tự)."))
    key = _lock(pkg_name)
    if not key:
        return {"package": pkg_name, "result": "stop", "reason": "locked"}
    try:
        frappe.db.rollback()
        pkg = _pkg(pkg_name)
        if not pkg or pkg.error_code != CODE_UNVERIFIED:
            return {"package": pkg_name, "result": "stop",
                    "reason": "not_unverified:%s" % (pkg.error_code if pkg else None)}
        ar = _ar(pkg.approval_request)
        settings = _settings(pkg.provider, pkg.environment)
        if not settings:
            return {"package": pkg_name, "result": "stop", "reason": "settings_missing"}
        try:
            st = _state_status(get_adapter(settings).poll_status(pkg.scts_document_id))
        except ProviderError as e:
            return {"package": pkg_name, "result": "stop", "reason": "poll_failed:%s" % e.code}
        if st == "cancelled":
            _mark(pkg, CODE, "cancelled_confirmed", ar.approval_status if ar else None,
                  SOURCE_SM, detail=reason[:200])
            frappe.db.commit()
            return {"package": pkg_name, "result": "marked", "provider_status": st}
        frappe.db.set_value(PKG, pkg.name, {"error_code": None, "error_message": None})
        events.emit("Failed", package=pkg.name, erp_actor=frappe.session.user,
                    verification_result="cancel_unverified_cleared:%s" % st,
                    request_meta={"source": SOURCE_SM, "ly_do": reason[:200],
                                  "document_id": pkg.scts_document_id})
        # Cron KHONG tu gui lai sau khi go moc: gui lai la quyet dinh cua SM (lenh SM liet ke
        # phieu) - QC vong 3.
        events.emit("PollTick", package=pkg.name,
                    verification_result="cancel_skip:unverified_cleared",
                    request_meta={"source": SOURCE_AUTO})
        frappe.db.commit()
        return {"package": pkg_name, "result": "cleared", "provider_status": st}
    finally:
        _unlock(key)
