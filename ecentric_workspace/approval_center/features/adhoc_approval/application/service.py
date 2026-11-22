# Copyright (c) 2026, eCentric and contributors
"""Phe duyet dot xuat gui CEO (Dot 0 quy trinh nhan su, Hoan chot 22-23/11/2026).

Thay email xin CEO duyet bang phieu RIENG TU tren ERP: ai cung gui duoc, MOT cap CEO (Any One,
role EC CEO - cau hinh o process, khong viet ten ai trong code), Duyet / Tra lai bo sung / Tu choi.
Da duyet thi gan duoc lam chung tu cho phieu khac (shared/requests/approval_links.py).

PHIEU NAY KHONG THAY cac cap duyet bat buoc cua form khac - chi la chung tu.

Muc Gap: truong `urgency` theo quy uoc engine -> thong bao "Can duyet" di severity urgent (xuyen
gio yen lang). Gap bat buoc ly do. SLA: Binh thuong 2 ngay lam viec (policy cua process), Gap 4 gio
lam viec (`engine.submit(sla_overrides=...)`, policy ADHOC_APPROVAL_URGENT_4H).
"""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Adhoc Approval Request"
APPROVAL_TYPE = "ADHOC_APPROVAL"
URGENT = "Gấp"
NORMAL = "Bình thường"
URGENT_SLA_POLICY = "ADHOC_APPROVAL_URGENT_4H"
MATERIAL_FIELDS = ["request_title", "content", "urgency", "urgency_reason", "desired_by"]
MAX_TITLE = 140


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def gen_title(doc):
    return ((doc.get("request_title") or "").strip() or _("Phê duyệt đột xuất"))[:MAX_TITLE]


def validate_business(doc):
    """Luat nghiep vu khi gui / gui lai (cau tieng Viet de nguoi dung sua duoc)."""
    if not (doc.get("request_title") or "").strip():
        frappe.throw(_("Vui lòng nhập tiêu đề."))
    if not (doc.get("content") or "").strip():
        frappe.throw(_("Vui lòng nhập nội dung đề xuất."))
    urg = doc.get("urgency") or NORMAL
    if urg not in (NORMAL, URGENT):
        frappe.throw(_("Mức độ không hợp lệ."))
    if urg == URGENT and not (doc.get("urgency_reason") or "").strip():
        frappe.throw(_("Phiếu Gấp bắt buộc ghi lý do gấp."))
    if doc.get("desired_by") and getdate(doc.get("desired_by")) < getdate(nowdate()):
        frappe.throw(_("Ngày mong muốn có kết quả không được ở quá khứ."))


def sla_overrides_for(doc):
    """{level_no: policy} cho phieu Gap; phieu thuong dung SLA cua process."""
    return {1: URGENT_SLA_POLICY} if (doc.get("urgency") == URGENT) else None


def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    user = frappe.session.user
    if doc.requested_by and doc.requested_by != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."), frappe.PermissionError)
    requester = doc.requested_by or user
    doc.requested_by = requester
    emp = frappe.db.get_value("Employee", {"user_id": requester},
                              ["name", "department", "company"], as_dict=True)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    doc.urgency = doc.urgency or NORMAL
    if doc.urgency != URGENT:
        doc.urgency_reason = None
    validate_business(doc)
    doc.approval_type = APPROVAL_TYPE
    doc.request_title = gen_title(doc)
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, requester,
                             sla_overrides=sla_overrides_for(doc))
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    if doc.urgency == URGENT:
        engine.log_action(req_name, "Commented", requester,
                          comment=_("Phiếu Gấp - lý do: {0}").format((doc.urgency_reason or "")[:500]))
    return req_name


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    if doc.urgency != URGENT and doc.urgency_reason:
        frappe.db.set_value(BUSINESS_DT, doc.name, "urgency_reason", None)
        doc.urgency_reason = None
    validate_business(doc)
    new_sig = _signature(doc)
    changed = new_sig != (doc.material_signature or "")
    frappe.db.set_value(BUSINESS_DT, doc.name, "request_title", gen_title(doc))
    # SLA cua cap CEO theo muc do MOI (nguoi gui co the doi Binh thuong <-> Gap khi bo sung).
    rl = frappe.db.get_value("EC Approval Request Level",
                             {"approval_request": doc.approval_request, "level_no": 1}, "name")
    if rl:
        src = frappe.db.get_value("EC Approval Request Level", rl, "source_process_level")
        base = frappe.db.get_value("EC Approval Level", src, "sla_policy") if src else None
        pol = URGENT_SLA_POLICY if doc.urgency == URGENT else base
        frappe.db.set_value("EC Approval Request Level", rl, "sla_policy", pol or None)
    res = engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    out = {"restarted": changed}
    if isinstance(res, dict) and res.get("esign"):
        out["esign"] = res["esign"]
    return out


def on_final_approval(name):
    """Khong co buoc xu ly sau duyet: chi ghi moc hoan tat (engine da bao nguoi gui)."""
    frappe.db.set_value(BUSINESS_DT, name, "completed_at", now_datetime())
