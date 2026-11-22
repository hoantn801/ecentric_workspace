# Copyright (c) 2026, eCentric and contributors
"""Resignation orchestration over the shared approval engine.

V2 (23/11/2026, Hoan chot): NV -> Quan ly truc tiep -> CnB/HR -> CEO (process RESIGNATION-V2).
  * KHONG co "Tu choi" (ApprovalDefinition.allow_reject=False - may chu chan, UI an nut): NLD co
    quyen don phuong nghi khi bao truoc du ngay (Dieu 35 BLLD 2019). Nguoi duyet chi "Duyet" hoac
    "Yeu cau bo sung" (tra lai dieu chinh).
  * NV "Rut don" (`withdraw`) truoc ngay lam viec cuoi - ke ca sau khi da co cap duyet / da duyet xong.
  * He thong tinh NGAY NGHI SOM NHAT hop le theo loai HD trong Employee.ec_contracts
    (domain/notice.py); chon som hon -> phieu ghi "xin nghi som hon han bao truoc" de cac cap thay.
  * Chan trung: moi NV mot don dang mo.
  * Khao sat nghi viec TACH khoi don: gui qua module Khao sat khi don duyet xong (chi HR xem).
    Truong khao sat tren DON CU duoc an voi nguoi khong phai HR (application/redact.py).
  * Duyet xong -> ghi relieving_date (module HR) + tao Clearance (module clearance_request).
Nguoi duyet lay tu cau hinh process - khong viet cung o day. Hang doi "HR xu ly" cu (V1) giu nguyen
cho cac don da vao hang doi truoc day (claim_fulfillment / complete_fulfillment)."""
import hashlib
import json
import re

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, nowdate

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Resignation Request"
APPROVAL_TYPE = "RESIGNATION"
OPEN = ("Pending", "Information Required")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MATERIAL_FIELDS = ["resignation_for", "employee_email", "personal_email", "last_working_day",
                   "resignation_reason"]
#: V2: bo 3 cau danh gia (khao sat tach sang module Khao sat, khong bat buoc).
REQUIRED_AT_SUBMIT = ["request_title", "resignation_for", "employee_email", "personal_email",
                      "last_working_day", "resignation_reason"]
#: Ai xem duoc thong tin HD cua nguoi khac khi lap don ho (ngoai chinh nguoi do + quan ly truc tiep).
HR_ROLES = ("EC CnB", "HR", "HR Manager", "System Manager")
#: Khao sat nghi viec - ham cua module Khao sat (Agent D). Chua co thi bo qua + ghi log.
SURVEY_FN = "ecentric_workspace.surveys.application.ca_nhan.giao_khao_sat"
SURVEY_TEMPLATE = "NGHI_VIEC"
SURVEY_VIEW_ROLES = ["EC CnB", "HR"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


def _rule():
    from ecentric_workspace.approval_center.features.resignation.domain import notice
    return notice


def _repo():
    from ecentric_workspace.approval_center.features.resignation.infrastructure import hr_repo
    return hr_repo


def _ngay_le():
    from ecentric_workspace.approval_center.shared.sla_ngay_lam_viec import ngay_le
    return ngay_le()


# --------------------------------------------------------------------------- ngay bao truoc
def compute_notice(employee_email, notice_date=None):
    emp = _repo().employee_of(employee_email)
    contracts = _repo().contracts_of(emp.name) if emp else []
    return _rule().tinh_bao_truoc(contracts, notice_date or getdate(nowdate()), _ngay_le())


def _may_read_notice(employee_email, user):
    if (employee_email or "").strip().lower() == (user or "").lower():
        return True
    if set(frappe.get_roles(user)) & set(HR_ROLES):
        return True
    emp = _repo().employee_of(employee_email)
    return bool(emp and _repo().manager_user_of(emp) == user)


def notice_info(employee_email, user=None):
    """Cho form: ngay nghi som nhat hop le. Chi tra chi tiet cho chinh NV, quan ly truc tiep, HR."""
    user = user or frappe.session.user
    if not employee_email or not _EMAIL_RE.match(employee_email.strip()):
        return {"known": False}
    if not _may_read_notice(employee_email, user):
        return {"known": False, "hidden": True}
    r = compute_notice(employee_email)
    return {"known": bool(r.get("ngay_som_nhat")), "earliest": str(r["ngay_som_nhat"]) if r.get("ngay_som_nhat") else None,
            "rule": r.get("quy_tac"), "notes": r.get("ghi_chu") or [], "contract_type": r.get("loai_hd")}


def _apply_notice(doc):
    r = compute_notice(doc.employee_email, getdate(nowdate()))
    doc.earliest_valid_last_day = r.get("ngay_som_nhat")
    doc.notice_rule = r.get("quy_tac")
    doc.early_leave_requested = 1 if _rule().som_hon_han(doc.last_working_day, r) else 0


# --------------------------------------------------------------------------- chan trung
def open_duplicate(employee_email, exclude=None):
    """Don khac cua cung NV con hieu luc: dang duyet, hoac da duyet + chua rut + chua qua ngay cuoi."""
    email = (employee_email or "").strip()
    if not email:
        return None
    rows = frappe.get_all(BUSINESS_DT, filters={"employee_email": email, "name": ["!=", exclude or ""],
                                                "approval_request": ["is", "set"]},
                          fields=["name", "approval_request", "last_working_day", "withdrawn_at"])
    today = getdate(nowdate())
    for r in rows:
        if r.withdrawn_at:
            continue
        st = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
        if st in OPEN:
            return r.name
        if st == "Approved" and r.last_working_day and getdate(r.last_working_day) >= today:
            return r.name
    return None


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yeu cau nay da duoc gui."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Ban chi co the gui yeu cau cua chinh minh."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _requester_context(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if not _EMAIL_RE.match((doc.employee_email or "").strip()):
        frappe.throw(_("Email cong ty (Employee Email) khong hop le."))
    if not _EMAIL_RE.match((doc.personal_email or "").strip()):
        frappe.throw(_("Email ca nhan (Personal Email) khong hop le."))
    if getdate(doc.last_working_day) < getdate(nowdate()):
        frappe.throw(_("Ngày làm việc cuối không được ở quá khứ."))
    # Khoa theo NV truoc khi kiem trung: hai lan bam "Gui" cung luc khong lot ca hai.
    frappe.db.sql("select name from `tabEC Resignation Request` where employee_email=%s for update",
                  ((doc.employee_email or "").strip(),))
    dup = open_duplicate(doc.employee_email, exclude=doc.name)
    if dup:
        frappe.throw(_("Nhân viên này đã có đơn nghỉ việc đang mở ({0}). Mỗi người chỉ một đơn - "
                       "rút đơn cũ trước nếu muốn gửi lại.").format(dup))
    _apply_notice(doc)
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    if doc.early_leave_requested:
        engine.log_action(req_name, "Commented", user,
                          comment=_("Xin nghỉ sớm hơn hạn báo trước: ngày làm việc cuối {0}, sớm nhất hợp lệ {1} "
                                    "({2}). Cần các cấp đồng ý.").format(
                              doc.last_working_day, doc.earliest_valid_last_day, doc.notice_rule))
    return req_name


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yeu cau chua duoc gui."))
    if doc.last_working_day and getdate(doc.last_working_day) < getdate(nowdate()):
        frappe.throw(_("Ngày làm việc cuối không được ở quá khứ."))
    _apply_notice(doc)
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    doc.save(ignore_permissions=True)
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


# --------------------------------------------------------------------------- rut don
def _leaver_user(doc):
    emp = _repo().employee_of(doc.get("employee_email"))
    return (emp and emp.user_id) or doc.get("employee_email")


def withdraw_state(doc, user=None):
    """(duoc_rut, ly_do_khong) - mot luat cho ca nut tren UI lan duong ghi."""
    user = user or frappe.session.user
    if doc.get("withdrawn_at"):
        return False, _("Đơn đã được rút.")
    if user not in (doc.get("requested_by"), _leaver_user(doc)) \
            and "System Manager" not in frappe.get_roles(user):
        return False, _("Chỉ người nghỉ việc / người lập đơn mới rút được đơn.")
    if not doc.get("approval_request"):
        return False, _("Đơn chưa gửi - hãy xoá bản nháp.")
    st = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_status")
    if st not in OPEN + ("Approved",):
        return False, _("Đơn đã kết thúc ({0}).").format(st)
    if doc.get("last_working_day") and getdate(nowdate()) >= getdate(doc.last_working_day):
        return False, _("Đã tới ngày làm việc cuối - không rút đơn được nữa, liên hệ HR.")
    return True, None


def withdraw(name, reason=None, actor=None):
    """NV rut don. Dang duyet -> huy phieu duyet. Da duyet -> giu phieu duyet (Approved), danh dau
    don da rut, xoa relieving_date tren ho so (neu con dung ngay cua don nay) va huy Clearance dang mo.
    Moi buoc ghi vet. Khong goi ra ngoai ngoai thong bao he thong."""
    actor = actor or frappe.session.user
    reason = (reason or "").strip()
    if not reason:
        frappe.throw(_("Vui lòng nhập lý do rút đơn."))
    frappe.db.get_value(BUSINESS_DT, name, "name", for_update=True)
    doc = frappe.get_doc(BUSINESS_DT, name)
    ok, why = withdraw_state(doc, actor)
    if not ok:
        frappe.throw(why, frappe.PermissionError)
    note = _("NV rút đơn: {0}").format(reason)
    st = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_status")
    ket = []
    if st in OPEN:
        engine.cancel(doc.approval_request, actor=actor, reason=note)
        ket.append("huy phieu duyet")
    else:
        engine.log_action(doc.approval_request, "Commented", actor,
                          comment=_("{0} (sau khi đơn đã duyệt xong).").format(note))
        try:
            from ecentric_workspace.hr.offboarding import service as offboarding
            ket.append(offboarding.unmark_resignation(doc.employee_email,
                                                      relieving_date=doc.last_working_day, source=name))
        except Exception:
            frappe.log_error(title="Resignation %s: rut don - khong xoa duoc ngay nghi" % name,
                             message=frappe.get_traceback())
            ket.append("LOI xoa ngay nghi - HR xoa tay relieving_date")
    try:
        from ecentric_workspace.approval_center.features.clearance_request.application import (
            service as clearance)
        ket.append(clearance.cancel_for_resignation(name, actor, note) or "khong co clearance mo")
    except Exception:
        frappe.log_error(title="Resignation %s: rut don - khong huy duoc Clearance" % name,
                         message=frappe.get_traceback())
        ket.append("LOI huy clearance")
    frappe.db.set_value(BUSINESS_DT, name, {"withdrawn_at": now_datetime(), "withdrawn_by": actor,
                                            "withdrawal_reason": reason})
    engine.log_action(doc.approval_request, "Commented", "Administrator",
                      comment="Rút đơn: " + "; ".join(str(k) for k in ket))
    people = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": doc.approval_request}, pluck="approver")
    engine.notify(sorted(set(people + [doc.requested_by]) - {actor}),
                  _("Đơn nghỉ việc đã được rút: {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"withdrawn": True, "steps": ket}


# --------------------------------------------------------------------------- man hinh chi tiet
def resignation_block(business, request):
    user = frappe.session.user
    ok, why = withdraw_state(business, user) if request else (False, None)
    out = {"can_withdraw": ok, "withdraw_blocked_reason": why if request else None,
           "earliest_valid_last_day": business.get("earliest_valid_last_day"),
           "notice_rule": business.get("notice_rule"),
           "early_leave_requested": business.get("early_leave_requested"),
           "withdrawn_at": business.get("withdrawn_at"), "withdrawal_reason": business.get("withdrawal_reason"),
           "clearance": None}
    clr = frappe.db.get_value("EC Clearance Request", {"resignation_request": business.get("name")},
                              ["name", "approval_request"], as_dict=True)
    if clr:
        out["clearance"] = {"name": clr.name, "route": "/approvals/clearance-request?id=%s" % clr.name,
                            "status": clr.approval_request and frappe.db.get_value(
                                "EC Approval Request", clr.approval_request, "approval_status")}
    elif business.get("clearance_error"):
        out["clearance_error"] = business.get("clearance_error")
    return out


# --------------------------------------------------------------------------- #
# Sau khi duyet xong - dispatched by engine.complete_approval (_FULFILLMENT_HANDLERS)
# --------------------------------------------------------------------------- #
def on_final_approval(name):
    """29/09/2026 (Hoan chot, file Excel): Don nghi viec duyet xong thi DI TIEP Clearance Request
    (Line Manager / Operation / HR / HOF ban giao song song) - thay cho buoc "HR xu ly" rieng
    truoc day. Ghi ngay nghi vao ho so + tao Clearance chay NEN sau commit: loi o hai viec do
    khong bao gio lam hong luot duyet. Don da o hang doi HR tu truoc van xu ly nhu cu.
    23/11: neu job nen bi mat (worker khoi dong lai...) job quet hang ngay cua Clearance tao bu."""
    frappe.enqueue("ecentric_workspace.approval_center.features.resignation.application.service."
                   "after_approval", queue="short", enqueue_after_commit=True, name=name)


def after_approval(name):
    """(1) Ghi Employee.resignation_letter_date / relieving_date (module HR - job 00:30 khoa tai
    khoan doc relieving_date). (2) Tao Clearance (ket qua / loi GHI LEN DON - khong chi Error Log).
    (3) Giao khao sat nghi viec. Moi viec mot try: viec nay hong khong chan viec kia."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.get("withdrawn_at"):
        return ["don da rut - bo qua"]
    ket = []
    try:
        from ecentric_workspace.hr.offboarding import service as offboarding
        ket.append(offboarding.mark_resignation(
            doc.employee_email, letter_date=doc.submitted_at or doc.creation,
            relieving_date=doc.last_working_day, source=name))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Resignation %s: khong ghi duoc ngay nghi vao ho so" % name,
                         message=frappe.get_traceback())
        ket.append("LOI ghi ho so")
    from ecentric_workspace.approval_center.features.clearance_request.application import (
        service as clearance)
    clr = clearance.create_from_resignation(name)
    ket.append("clearance=%s" % (clr or "LOI"))
    ket.append("khao_sat=%s" % giao_khao_sat_nghi_viec(doc))
    if doc.approval_request:
        engine.log_action(doc.approval_request, "Commented", "Administrator",
                          comment="; ".join(str(k) for k in ket))
        frappe.db.commit()
    if not clr:
        hr = frappe.get_all("EC Approval Request Approver",
                            filters={"approval_request": doc.approval_request}, pluck="approver")
        engine.notify(sorted(set(hr + [doc.requested_by])),
                      _("Chưa tạo được Clearance cho {0} - báo quản trị viên.").format(name),
                      BUSINESS_DT, name)
        frappe.db.commit()
    return ket


def giao_khao_sat_nghi_viec(doc):
    """Khao sat nghi viec qua module Khao sat (khong bat buoc, chi HR xem). Han = ngay lam viec cuoi;
    module Khao sat tu nhac mot lan truoc han. Ham chua co / loi -> bo qua + Error Log, khong chan."""
    try:
        fn = frappe.get_attr(SURVEY_FN)
    except Exception:
        # Module Khao sat chua co ham nay (Dot 2) -> bo qua; ket qua nam trong nhat ky duyet cua don.
        return "chua co module"
    user = _leaver_user(doc)
    if not user or not frappe.db.exists("User", user):
        return "khong co tai khoan"
    try:
        from ecentric_workspace.approval_center.shared import sla_ngay_lam_viec as nlv
        han = max(1, nlv.dem_ngay_lam_viec(getdate(nowdate()), getdate(doc.last_working_day), _ngay_le()))
        # Hop dong module Khao sat (Dot 2): "khoa" = khoa chong trung (goi lai -> tra lan giao cu);
        # ket qua {"ok", "assignment", "duplicate", "due_date", "ly_do"}.
        res = fn(user, SURVEY_TEMPLATE, han,
                 {"khoa": doc.name, "reference_doctype": BUSINESS_DT, "reference_name": doc.name,
                  "loai": "nghi_viec"},
                 SURVEY_VIEW_ROLES) or {}
        if isinstance(res, dict):
            return "da giao" if res.get("ok") else "khong giao (%s)" % (res.get("ly_do") or "?")
        return "da giao" if res else "khong giao"
    except Exception:
        frappe.log_error(title="Resignation %s: khong giao duoc khao sat nghi viec" % doc.name,
                         message=frappe.get_traceback())
        return "LOI"


def claim_fulfillment(name, user=None):
    """Idempotent claim. First claim of an Assigned request logs exactly one "Started" timeline
    entry; a repeat claim by the SAME owner returns success without a duplicate entry and without
    resetting owner/status; a claim while another user owns it is blocked. complete_fulfillment
    behavior is unchanged."""
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Ban khong thuoc nhom HR xu ly yeu cau nay."))
    cur = frappe.db.get_value(BUSINESS_DT, name,
                              ["fulfillment_status", "fulfillment_owner"], as_dict=True) or {}
    status, owner = cur.get("fulfillment_status"), cur.get("fulfillment_owner")
    # Idempotent: already claimed by this user -> no duplicate timeline, no state reset.
    if status == "In Progress" and owner == user:
        return {"owner": user, "claimed": True, "idempotent": True}
    # Already owned by someone else -> block (do not steal).
    if owner and owner != user:
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    if status == "Completed":
        frappe.throw(_("Yeu cau nay da hoan tat."))
    # Waiting (Assigned): atomic claim; the WHERE guard also settles concurrent double-claims.
    frappe.db.sql(
        """update `tabEC Resignation Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC Resignation Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Yeu cau nay da duoc nguoi khac nhan xu ly."))
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Resignation HR fulfillment queue"),
                            date=frappe.db.get_value(BUSINESS_DT, name, "fulfillment_due_at"))
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Started", user, comment=_("HR fulfillment claimed"),
                      new_status="In Progress")
    engine.notify([doc.requested_by], _("HR da nhan xu ly boi {0}: {1}").format(user, engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"owner": user, "claimed": True}


def complete_fulfillment(name, user=None, payload=None):
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chi nguoi nhan xu ly hoac System Manager moi duoc hoan tat."))
    summary = (data.get("fulfillment_summary") or doc.fulfillment_summary or "").strip()
    if not summary:
        frappe.throw(_("Vui long nhap Ghi chu xu ly cua HR truoc khi hoan tat."))
    doc.fulfillment_summary = summary
    if "completed_attachment" in data:
        doc.completed_attachment = data.get("completed_attachment")
    doc.fulfillment_status = "Completed"
    doc.completed_by = user
    doc.completed_at = now_datetime()
    from ecentric_workspace.approval_center.shared.requests.command_service import (
        attach_extra_files)
    # Tep duoc tai len KHONG kem doctype/docname: `upload_file` co hai truong do se kiem quyen
    # GHI tren chinh DocType ho so, ma cac DocType nay chi cho System Manager ghi - nguoi xu ly
    # that (Dong, Linh Vuong, Thuong, Tuan) deu khong co, nen ho khong tai duoc file (08/09).
    # Doi lai, file sinh ra la File mo coi; gan vao ho so o day - TRUOC khi save - de hook
    # attach_files_to_document cua Frappe nhan ra va khong tao dong thu hai.
    attach_extra_files(doc, [u for u in (doc.completed_attachment,) if u])
    doc.save(ignore_permissions=True)
    engine.close_fulfillment_todos(BUSINESS_DT, name)
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Yeu cau nghi viec da hoan tat: {0}").format(engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
    return {"completed": True}
