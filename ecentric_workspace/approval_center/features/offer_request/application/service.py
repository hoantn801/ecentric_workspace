# Copyright (c) 2026, eCentric and contributors
"""Offer Request over the shared engine (28/09/2026, Hoan).

Luong: Hiring Request da duyet -> HR tuyen dung (Role EC Recruiter) chot ung vien -> lap Offer
tu CHINH phieu Hiring (nut "Tao Offer") -> duyet: Line manager cua vi tri -> HR & CnB (Role
EC CnB) -> HOF -> CEO -> duyet xong TU TAO New Staff Preparation.

Luat quan tri:
  * Vi tri / loai hinh / line manager / phong ban CHEP tu Hiring (prepare_draft), khong nhan tu
    client: line manager la nguoi duyet cap 1 - de nguoi gui chon la de ho chon nguoi duyet.
  * Chi nguoi tuyen dung cua phieu Hiring (ToDo / EC Recruiter) hoac System Manager duoc tao,
    va chi khi Hiring da duyet xong va dang o buoc tuyen dung.
  * Muc luong (`compensation`) chi hien cho nguoi xem duoc phieu (nguoi gui + nguoi duyet +
    System Manager - can_view_request), khong vao danh sach, khong vao thong bao, khong chep
    sang New Staff Preparation.
Khong hardcode nguoi duyet: cap nao ai duyet la cau hinh process OFFER_REQUEST-V1."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Offer Request"
APPROVAL_TYPE = "OFFER_REQUEST"
HIRING_DT = "EC Hiring Request"
NSP_DT = "EC New Staff Preparation"

#: Chep tu Hiring, khoa sau khi gui (xem controller).
SNAPSHOT_FIELDS = ("position", "employment_type", "line_manager", "department", "company")
MATERIAL_FIELDS = ["hiring_request", "candidate_name", "onboard_date", "probation_end_date",
                   "mobile_phone", "company_laptop", "compensation", "note", "resume"]
REQUIRED_AT_SUBMIT = ["request_title", "hiring_request", "candidate_name", "onboard_date",
                      "probation_end_date", "mobile_phone", "compensation", "resume"]


def _hiring_service():
    from ecentric_workspace.approval_center.features.hiring_request.application import service
    return service


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    # V2 (23/11): luong offer dang so. Chi dua vao chu ky khi CO gia tri - phieu cu (chua co truong
    # nay) giu nguyen chu ky, gui lai khong bi tinh la "doi noi dung" va duyet lai tu dau.
    if doc.get("offered_salary"):
        vals["offered_salary"] = str(float(doc.get("offered_salary")))
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def hiring_snapshot(hiring_name):
    row = frappe.db.get_value(HIRING_DT, hiring_name,
                              ["name", "request_title", "position", "employment_type",
                               "line_manager", "department", "company", "number_of_vacancy"],
                              as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy Hiring Request {0}.").format(hiring_name))
    return row


def _assert_may_create(hiring_name, user=None):
    user = user or frappe.session.user
    if not _hiring_service().can_create_offer(hiring_name, user):
        frappe.throw(_("Chỉ người tuyển dụng của Hiring Request này (role EC Recruiter) mới tạo được "
                       "Offer, và chỉ khi Hiring đã duyệt xong và chưa đóng tuyển dụng."),
                     frappe.PermissionError)


def prepare_draft(document):
    """draft_preparer: chep ban chup tu Hiring moi lan luu nhap (khi chua gui)."""
    if not document.get("hiring_request"):
        frappe.throw(_("Offer phải được tạo từ một Hiring Request đã duyệt (nút \"Tạo Offer\")."))
    if document.get("approval_request"):
        return                      # da gui: ban chup da khoa, khong chep lai
    # Kiem MOI lan luu nhap chu khong chi luc tao: doi hiring_request cua mot ban nhap sang
    # mot Hiring khac cung la "tao Offer cho Hiring do".
    _assert_may_create(document.hiring_request, document.requested_by or frappe.session.user)
    snap = hiring_snapshot(document.hiring_request)
    for f in SNAPSHOT_FIELDS:
        document.set(f, snap.get(f))


def gen_title(document):
    parts = [document.get("candidate_name"), document.get("position"), document.get("department")]
    parts = [str(x).strip() for x in parts if x and str(x).strip()]
    return ("Offer - " + " - ".join(parts))[:255] if parts else "Offer Request"


def _validate_for_submit(doc):
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc trước khi gửi."))
    if getdate(doc.probation_end_date) < getdate(doc.onboard_date):
        frappe.throw(_("Ngày kết thúc thử việc/thực tập phải sau ngày onboard."))
    lm = (doc.line_manager or "").strip()
    row = lm and frappe.db.get_value("User", lm, ["enabled", "user_type"], as_dict=True)
    if not (row and row.enabled and row.user_type == "System User"):
        frappe.throw(_("Line manager trên Hiring Request không phải người dùng đang hoạt động - "
                       "không xác định được người duyệt cấp 1. Liên hệ HR/Admin."))


def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    user = frappe.session.user
    if doc.requested_by and doc.requested_by != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."))
    user = doc.requested_by or user
    doc.requested_by = user
    _assert_may_create(doc.hiring_request, user)
    snap = hiring_snapshot(doc.hiring_request)
    for f in SNAPSHOT_FIELDS:
        doc.set(f, snap.get(f))
    emp = frappe.db.get_value("Employee", {"user_id": user}, ["name", "company"], as_dict=True)
    if emp:
        doc.employee = emp.name
    doc.request_title = gen_title(doc)
    _validate_for_submit(doc)
    if not doc.get("offered_salary"):
        frappe.throw(_("Vui lòng nhập Lương offer (số) - dùng để so với mức đã duyệt trên Hiring."))
    skip, note = hof_decision(doc)
    doc.hof_skipped = 1 if skip else 0
    doc.hof_rule_note = note
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    # Offer dau tien cua mot Hiring chua ai nhan: nguoi lap Offer chinh la nguoi dang tuyen.
    if frappe.db.get_value(HIRING_DT, doc.hiring_request, "fulfillment_status") == "Assigned":
        _hiring_service().claim_fulfillment(doc.hiring_request, user=user)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user,
                             skip_level_nos=[skip] if skip else None,
                             skip_reason=("Offer V2: " + note) if skip else None)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


# --------------------------------------------------------------------------- HOF co dieu kien
def _hof_level_no():
    """So cap HOF KHONG bat buoc cua process Offer dang Active (tim theo ten - setup_v2.HOF_LEVEL_NAME).
    Process cu (V1: moi cap bat buoc) -> None: khong bo cap nao."""
    from ecentric_workspace.approval_center.features.offer_request.infrastructure.setup_v2 import (
        HOF_LEVEL_NAME)
    proc = frappe.get_all("EC Approval Process", filters={"approval_type": APPROVAL_TYPE, "status": "Active"},
                          pluck="name", limit_page_length=1)
    if not proc:
        return None
    row = frappe.db.get_value("EC Approval Level", {"approval_process": proc[0], "level_name": HOF_LEVEL_NAME},
                              ["level_no", "mandatory"], as_dict=True)
    return row.level_no if row and not row.mandatory else None


def hof_decision(doc):
    """-> (level_no_bo | None, ghi_chu). Luat o domain/hof_rule.py."""
    from ecentric_workspace.approval_center.features.offer_request.domain.hof_rule import bo_cap_hof
    lvl = _hof_level_no()
    muc = frappe.db.get_value(HIRING_DT, doc.hiring_request, "suggested_salary") if doc.hiring_request else None
    bo, note = bo_cap_hof(doc.get("offered_salary"), muc)
    if lvl is None:
        return None, note + " (quy trình hiện tại không có cấp HOF tuỳ chọn - giữ nguyên)"
    return (lvl if bo else None), note


# --------------------------------------------------------------------------- ung vien tu choi / huy
CANDIDATE_KINDS = {"Declined": "Ứng viên từ chối offer", "Offer Cancelled": "Huỷ offer"}
CANDIDATE_ROLES = ("EC Recruiter", "EC CnB", "HR", "System Manager")


def may_mark_candidate(doc, user=None):
    user = user or frappe.session.user
    return doc.get("requested_by") == user or bool(set(frappe.get_roles(user)) & set(CANDIDATE_ROLES))


def mark_candidate_status(name, kind, reason, actor=None):
    """Ung vien tu choi offer / huy offer (ke ca SAU khi CEO duyet): dong phieu Offer dang mo (huy co ly
    do) hoac ghi vet tren phieu da duyet, roi HUY New Staff Preparation dang mo - co audit."""
    actor = actor or frappe.session.user
    reason = (reason or "").strip()
    if kind not in CANDIDATE_KINDS:
        frappe.throw(_("Loại ghi nhận không hợp lệ."))
    if not reason:
        frappe.throw(_("Vui lòng nhập lý do."))
    frappe.db.get_value(BUSINESS_DT, name, "name", for_update=True)
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not may_mark_candidate(doc, actor):
        frappe.throw(_("Chỉ người lập Offer / tuyển dụng / CnB/HR mới ghi nhận được."), frappe.PermissionError)
    if doc.get("candidate_status"):
        frappe.throw(_("Offer này đã được ghi nhận: {0}.").format(doc.candidate_status))
    if not doc.approval_request:
        frappe.throw(_("Offer chưa gửi - xoá bản nháp nếu không dùng."))
    st = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_status")
    if st not in ("Pending", "Information Required", "Approved"):
        frappe.throw(_("Offer đã kết thúc ({0}).").format(st))
    note = "%s: %s" % (CANDIDATE_KINDS[kind], reason)
    if st == "Approved":
        engine.log_action(doc.approval_request, "Commented", actor, comment=note)
    else:
        engine.cancel(doc.approval_request, actor=actor, reason=note)
    frappe.db.set_value(BUSINESS_DT, name, {"candidate_status": kind, "candidate_status_at": now_datetime(),
                                            "candidate_status_by": actor, "candidate_status_reason": reason})
    from ecentric_workspace.approval_center.features.new_staff_preparation.application import (
        service as nsp_service)
    nsp_note = nsp_service.cancel_for_offer(name, actor, note)
    engine.notify([u for u in {doc.requested_by, doc.line_manager} if u and u != actor],
                  _("{0}: {1}").format(CANDIDATE_KINDS[kind], engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"candidate_status": kind, "new_staff_preparation": nsp_note}


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    _validate_for_submit(doc)
    if doc.get("hof_skipped"):
        # Cap HOF da bi bo luc gui (snapshot). Luong moi vuot muc Hiring thi khong the gan lai cap HOF
        # vao phieu dang chay - phai huy va lap Offer moi de HOF duyet.
        from ecentric_workspace.approval_center.features.offer_request.domain.hof_rule import bo_cap_hof
        muc = frappe.db.get_value(HIRING_DT, doc.hiring_request, "suggested_salary")
        if not bo_cap_hof(doc.get("offered_salary"), muc)[0]:
            frappe.throw(_("Lương offer mới vượt mức đã duyệt trên Hiring nhưng phiếu này đã bỏ cấp HOF lúc gửi. "
                           "Vui lòng huỷ và tạo Offer mới để HOF duyệt."))
    doc.request_title = gen_title(doc)
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    doc.save(ignore_permissions=True)
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


def offer_block(business, request):
    """Khoi doc them cho man hinh chi tiet: Hiring goc + New Staff Preparation."""
    out = {"hiring": None, "new_staff_preparation": business.get("new_staff_preparation"),
           "can_retry_nsp": False}
    if business.get("hiring_request"):
        h = frappe.db.get_value(HIRING_DT, business.hiring_request,
                                ["name", "request_title", "number_of_vacancy"], as_dict=True)
        if h:
            out["hiring"] = {"name": h.name, "request_title": h.request_title,
                             "number_of_vacancy": h.number_of_vacancy,
                             "route": "/approvals/hiring-request?id=%s" % h.name}
    out["candidate_status"] = business.get("candidate_status")
    out["hof_rule_note"] = business.get("hof_rule_note")
    out["can_mark_candidate"] = bool(
        request and request.approval_status in ("Pending", "Information Required", "Approved")
        and not business.get("candidate_status") and may_mark_candidate(business))
    if out["new_staff_preparation"]:
        out["nsp_route"] = "/approvals/new-staff-preparation?id=%s" % out["new_staff_preparation"]
    elif request and request.approval_status == "Approved" and not business.get("candidate_status"):
        user = frappe.session.user
        out["can_retry_nsp"] = (business.get("requested_by") == user
                                or "System Manager" in frappe.get_roles(user))
    return out


def on_final_approval(name):
    """Offer duyet xong -> bao nguoi gui + line manager, roi tao New Staff Preparation o
    NEN, SAU KHI giao dich duyet da commit. Tao ngay trong giao dich cua CEO thi mot loi cau
    hinh o NSP (vd role Operation chua ai giu) se lam HONG CA LAN DUYET cua CEO."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.notify([u for u in {doc.requested_by, doc.line_manager} if u],
                  _("Offer đã được duyệt: {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    frappe.enqueue("ecentric_workspace.approval_center.features.new_staff_preparation."
                   "application.service.create_from_offer",
                   queue="short", enqueue_after_commit=True, offer_name=name)
