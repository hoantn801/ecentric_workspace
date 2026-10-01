# Copyright (c) 2026, eCentric and contributors
"""Daily Target orchestration over the shared engine. One business DocType, two
scopes -> two configured Approval Processes (selected by scope; approvers still
come from process participants/snapshot).

01/10/2026 (Hoan): sau khi duyet xong -> buoc "Data xu ly" (fulfillment, Role `EC Data Team`,
cung khuon Hiring / Booking): mot nguoi nhan phieu, cap nhat muc tieu vao he thong du lieu,
"Hoan tat" kem ghi chu bat buoc."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Daily Target Request"
APPROVAL_TYPE = "DAILY_TARGET"
PROCESS_PROJECT = "DAILY_TARGET_PROJECT-V1"
PROCESS_CONSOLIDATED = "DAILY_TARGET_CONSOLIDATED-V1"

MATERIAL_FIELDS = ["request_scope", "brand", "channels", "channel_other", "target_month",
                   "target_setting_type", "justification"]
REQUIRED_AT_SUBMIT = ["request_title", "request_scope", "brand", "channels", "target_month",
                      "target_setting_type", "justification", "request_attachment"]


def process_for_scope(scope):
    return PROCESS_PROJECT if scope == "Project level" else PROCESS_CONSOLIDATED


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _requester_context(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    chans = [c.strip() for c in (doc.channels or "").split(",") if c.strip()]
    if "Other" in chans and not (doc.channel_other or "").strip():
        frappe.throw(_("Vui lòng nhập kênh khác khi chọn 'Other'."))
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user,
                             process_code=process_for_scope(doc.request_scope))
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


# =============================================================================
# Buoc "Data xu ly" sau khi duyet (01/10/2026, Hoan: "team data co linh.vuong va minh")
# =============================================================================
FULFILLER_ROLE = "EC Data Team"


def on_final_approval(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    proc = frappe.get_doc("EC Approval Process", proc_name)
    fulfillers = [u for u, _lbl in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]
    if not [p for p in proc.participants if p.participant_purpose == "Fulfiller"]:
        return                                   # process nay khong cau hinh buoc xu ly
    emp = frappe.db.get_value("Employee", {"user_id": doc.requested_by}, ["name", "company"], as_dict=True)
    sla = engine.resolve_sla(proc.fulfillment_sla_policy,
                             employee=emp.name if emp else None,
                             company=(emp.company if emp else None) or doc.company)
    frappe.db.set_value(BUSINESS_DT, name, {
        "fulfillment_status": "Assigned",
        "fulfillment_due_at": sla["due_at"] if sla else None,
        "fulfillment_sla_calendar": sla["calendar"] if sla else None,
        "fulfillment_sla_holiday_list": sla["holiday_list"] if sla else None,
    })
    if fulfillers:
        engine.assign(BUSINESS_DT, name, fulfillers, _("Daily Target - Data xu ly"),
                      date=sla["due_at"] if sla else None, fulfillment=True)
    else:
        frappe.log_error(title="Daily Target: chua co ai giu role %s" % FULFILLER_ROLE,
                         message="%s da duyet nhung khong co nguoi Data nhan viec." % name)
    engine.notify([doc.requested_by] + fulfillers,
                  _("Da duyet - chuyen team Data xu ly: {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)


def _may_work(user, name):
    return bool(frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                          "allocated_to": user, "status": "Open"})
                or engine.is_active_process_fulfiller(APPROVAL_TYPE, user)
                or "System Manager" in frappe.get_roles(user))


def claim_fulfillment(name, user=None):
    user = user or frappe.session.user
    if not _may_work(user, name):
        frappe.throw(_("Bạn không thuộc team Data (EC Data Team) của yêu cầu này."))
    cur = frappe.db.get_value(BUSINESS_DT, name, ["fulfillment_status", "fulfillment_owner"],
                              as_dict=True) or {}
    if cur.get("fulfillment_status") == "In Progress" and cur.get("fulfillment_owner") == user:
        return {"owner": user, "claimed": True, "idempotent": True}
    if cur.get("fulfillment_owner") and cur.get("fulfillment_owner") != user:
        frappe.throw(_("Yêu cầu này đã được người khác nhận xử lý."))
    if cur.get("fulfillment_status") == "Completed":
        frappe.throw(_("Yêu cầu này đã hoàn tất."))
    frappe.db.sql(
        """update `tabEC Daily Target Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC Daily Target Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Yêu cầu này đã được người khác nhận xử lý."))
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Daily Target - Data xu ly"),
                            date=frappe.db.get_value(BUSINESS_DT, name, "fulfillment_due_at"))
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Started", user, comment=_("Data nhận xử lý"),
                      new_status="In Progress")
    engine.notify([doc.requested_by], _("Team Data đã nhận xử lý bởi {0}: {1}").format(
        user, engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
    return {"owner": user, "claimed": True}


def complete_fulfillment(name, user=None, payload=None):
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chỉ người đã nhận xử lý hoặc System Manager mới được hoàn tất."))
    if doc.fulfillment_status not in ("Assigned", "In Progress"):
        frappe.throw(_("Yêu cầu này không ở bước Data xử lý."))
    summary = (data.get("fulfillment_summary") or doc.fulfillment_summary or "").strip()
    if not summary:
        frappe.throw(_("Vui lòng ghi chú kết quả xử lý trước khi hoàn tất."))
    doc.fulfillment_summary = summary
    doc.fulfillment_status = "Completed"
    doc.completed_by = user
    doc.completed_at = now_datetime()
    from ecentric_workspace.approval_center.shared.requests.command_service import (
        attach_extra_files)
    attach_extra_files(doc, data.get("_attachments"))
    doc.save(ignore_permissions=True)
    engine.close_fulfillment_todos(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Completed", user, comment=summary, new_status="Completed")
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Team Data đã hoàn tất: {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"completed": True}
