# Copyright (c) 2026, eCentric and contributors
"""Bao KET QUA ky ve nghiep vu (K6, THIETKE_ky_so_hop_dong - PR-C, 22/11/2026).

Hop dong voi nghiep vu: hooks.py cua app khai
    ec_esign_outcome_handlers = {"<business doctype>": "<duong.dan.ham>"}
    ham(business_name, purpose, outcome, signed_file=None, detail=None) -> dict
outcome: "signed" (ky du; signed_file = file_url PDF ky DA dinh kem phieu) | "rejected" (nguoi ky /
doi tac tu choi tren cong) | "returned" (tra lai nguoi tao) | "destroyed" (huy tren cong).
detail: cau tieng Viet doc duoc (nghiep vu dan vao binh luan cho nguoi dung).
Nen tang KHONG import code nghiep vu; loai phieu khong khai hook (DNTT) -> khong lam gi.

Cam ket:
  * Moi (goi, outcome) bao MOT lan thanh cong (vet Completed `outcome_reported:<x>`), kiem duoi
    khoa dong goi (FOR UPDATE) - cron, job tai PDF va ops khong bao trung.
  * Ham nghiep vu chay trong SAVEPOINT: nem loi -> rollback phan cua no, ghi Failed
    `outcome_handler_failed:<x>` + Error Log; KHONG lam hong giao dich ky so dang chay.
  * "signed" CHI bao khi (a) yeu cau duyet da Approved (nghiep vu tu choi "signed" truoc do -
    chua du dieu kien thi CHO, khong tinh la mot lan loi) va (b) khong co ToDo soat PDF ky dang mo
    (PDF thieu chu ky so - su co 16/11). `sweep_unreported` thu lai o vong tai PDF.
  * purpose: goi hien chi co mot loai muc dich cho moi phieu -> "contract". (Nhieu goi / BBNT:
    cho PO chot mo hinh BBNT - xem THIETKE muc 2f.)
"""
import frappe

from ecentric_workspace.platform.esign import events
from ecentric_workspace.platform.esign.sanitize import safe_error

PKG = "EC Digital Signature Package"
DSF = "EC Digital Signature File"
EVT = "EC Digital Signature Event"
AR = "EC Approval Request"
HOOK = "ec_esign_outcome_handlers"
OUTCOMES = ("signed", "rejected", "returned", "destroyed")
DEFAULT_PURPOSE = "contract"
MAX_ATTEMPTS = 5
#: Chi quet goi tao tu ngay nay (khong bao bu "signed" cho goi cu khi moi deploy).
SWEEP_SINCE = "2026-11-22 00:00:00"
REVIEW_TODO_MARKER = "[EC-ESIGN-SIGNED-FILE-REVIEW]"     # = signed_files.REVIEW_TODO_MARKER


def handler_path(business_doctype):
    try:
        hooks = frappe.get_hooks(HOOK) or {}
    except Exception:
        return None
    path = hooks.get(business_doctype) if isinstance(hooks, dict) else None
    if isinstance(path, (list, tuple)):
        path = path[-1] if path else None
    return path or None


def _reported(pkg_name, outcome):
    return bool(frappe.get_all(EVT, filters={"package": pkg_name, "event_type": "Completed",
                                             "verification_result": "outcome_reported:%s"
                                                                    % outcome},
                               fields=["name"], limit_page_length=1))


def _failures(pkg_name, outcome):
    return frappe.db.count(EVT, {"package": pkg_name, "event_type": "Failed",
                                 "verification_result": "outcome_handler_failed:%s" % outcome})


def _review_open(pkg_name):
    return bool(frappe.db.exists("ToDo", {"reference_type": PKG, "reference_name": pkg_name,
                                          "status": "Open",
                                          "description": ["like", "%" + REVIEW_TODO_MARKER + "%"]}))


def signed_file_url(pkg_name):
    """file_url cua PDF ky (tep ky DAU TIEN theo thu tu) + danh sach tat ca, hoac (None, [])."""
    rows = frappe.get_all(DSF, filters={"package": pkg_name, "requires_signature": 1},
                          fields=["signed_file"], order_by="idx_order asc, creation asc")
    urls = []
    for r in rows:
        if r.signed_file:
            u = frappe.db.get_value("File", r.signed_file, "file_url")
            if u:
                urls.append(u)
    return (urls[0] if urls else None), urls


def report(pkg_name, outcome, file_url=None, detail=None):
    """Bao ket qua cua mot goi. KHONG BAO GIO nem loi ra nguoi goi."""
    try:
        return _report(pkg_name, outcome, file_url, detail)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "esign outcomes.report %s %s" % (pkg_name, outcome))
        return {"ok": False, "reason": "internal_error"}


def _report(pkg_name, outcome, file_url, detail):
    if outcome not in OUTCOMES:
        return {"ok": False, "reason": "bad_outcome"}
    pkg = frappe.db.get_value(PKG, pkg_name, ["name", "business_doctype", "business_name",
                                              "approval_request"], as_dict=True)
    if not pkg or not pkg.business_doctype:
        return {"ok": False, "reason": "no_package"}
    path = handler_path(pkg.business_doctype)
    if not path:
        return {"ok": False, "reason": "no_handler"}
    # Khoa dong goi roi doc vet "da bao" bang doc CO KHOA (QC 22/11 vong 2: REPEATABLE READ -
    # doc thuong thay anh chup cu, worker thu hai van goi ham lan nua).
    frappe.db.get_value(PKG, pkg_name, "name", for_update=True)
    if frappe.db.get_value(EVT, {"package": pkg_name, "event_type": "Completed",
                                 "verification_result": "outcome_reported:%s" % outcome},
                           "name", for_update=True):
        return {"ok": True, "reason": "already_reported"}
    if outcome == "signed":
        if pkg.approval_request and frappe.db.get_value(
                AR, pkg.approval_request, "approval_status") != "Approved":
            return {"ok": False, "reason": "request_not_approved"}     # cho - khong tinh lan loi
        if _review_open(pkg_name):
            return {"ok": False, "reason": "signed_file_review_open"}
        if not file_url:
            file_url, _all = signed_file_url(pkg_name)
            if not file_url:
                return {"ok": False, "reason": "no_signed_file"}
    purpose = DEFAULT_PURPOSE
    sp = "esign_outcome"
    msg_mark = len(getattr(frappe.local, "message_log", None) or [])
    frappe.db.savepoint(sp)
    try:
        res = frappe.get_attr(path)(pkg.business_name, purpose, outcome,
                                    signed_file=file_url, detail=detail)
    except Exception as e:
        frappe.db.rollback(save_point=sp)
        # Thong bao msgprint cua ham da rollback khong duoc toi tay nguoi dung.
        log = getattr(frappe.local, "message_log", None)
        if isinstance(log, list):
            del log[msg_mark:]
        frappe.log_error(frappe.get_traceback(), "esign outcome handler %s" % path)
        events.emit("Failed", package=pkg_name, verification_result="outcome_handler_failed:%s"
                    % outcome, error_summary=safe_error(e),
                    request_meta={"purpose": purpose, "outcome": outcome, "handler": path})
        return {"ok": False, "reason": "handler_failed", "error": type(e).__name__}
    events.emit("Completed", package=pkg_name, verification_result="outcome_reported:%s" % outcome,
                request_meta={"purpose": purpose, "outcome": outcome, "signed_file": file_url,
                              "detail": (str(detail)[:300] if detail else None),
                              "result": res if isinstance(res, dict) else None})
    return {"ok": True, "result": res}


def sweep_unreported(limit=50, commit=None):
    """Goi da luu du PDF ky nhung "signed" chua bao (ham nghiep vu loi / phieu chua Approved /
    dang soat PDF) -> thu lai. Chi loai phieu co khai hook, goi tao tu SWEEP_SINCE, chua bao va
    chua qua MAX_ATTEMPTS lan loi - loc NGAY trong SQL (goi da xong khong chiem cho). Goi o vong
    tai PDF (*/30). `commit()` sau moi goi (khong giu khoa ca lo)."""
    try:
        hooks = frappe.get_hooks(HOOK) or {}
    except Exception:
        return 0
    doctypes = list(hooks.keys()) if isinstance(hooks, dict) else []
    if not doctypes:
        return 0
    rows = frappe.db.sql("""
        select p.name from `tabEC Digital Signature Package` p
        where p.business_doctype in %(dts)s and p.signed_bundle_complete = 1
          and p.creation >= %(since)s
          and not exists (select 1 from `tabEC Approval Request` a
                          where a.name = p.approval_request
                            and a.approval_status in ('Rejected', 'Cancelled'))
          and not exists (select 1 from `tabEC Digital Signature Event` e
                          where e.package = p.name and e.event_type = 'Completed'
                            and e.verification_result = 'outcome_reported:signed')
          and (select count(*) from `tabEC Digital Signature Event` f
               where f.package = p.name and f.event_type = 'Failed'
                 and f.verification_result = 'outcome_handler_failed:signed') < %(max)s
        order by p.modified desc limit %(lim)s""",
        {"dts": tuple(doctypes), "since": SWEEP_SINCE, "max": MAX_ATTEMPTS, "lim": int(limit)},
        as_dict=True)
    n = 0
    for r in rows:
        report(r.name, "signed")
        n += 1
        if commit:
            commit()
    return n
