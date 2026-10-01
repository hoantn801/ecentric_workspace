# Copyright (c) 2026, eCentric and contributors
"""Nut "Nhac nguoi xu ly" cho moi form phe duyet (01/10/2026, Hoan).

Ai bam: CHI nguoi gui phieu (requested_by).
Nhac ai: DUNG nguoi dang giu phieu luc bam - khong nhac nguoi chua toi luot hay da xong:
  * phieu "Pending" -> cac dong duyet con Pending o CAP HIEN TAI (Any One: ca nhom con lai;
    Each Group: chi nhom chua xac nhan - dong da Skipped / Approved khong nhac);
  * phieu da duyet, dang o buoc xu ly (fulfillment Assigned / In Progress) -> nguoi da nhan
    xu ly; chua ai nhan thi nhung nguoi dang co ToDo xu ly mo.
  * "Information Required" -> bong o san nguoi gui, khong co ai de nhac.
Bao qua ERP + Teams (engine.notify - cung kenh voi thong bao duyet, ton trong cai dat thong
bao tung nguoi). Moi phieu 15 phut mot lan (tinh tu lan nhac truoc, ai bam cung vay); vet
ghi vao nhat ky duyet (action "Reminded") de nguoi duyet va quan tri thay ai da nhac luc nao."""
import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

COOLDOWN_SECONDS = 15 * 60
ACTION = "Reminded"
_REQ = "EC Approval Request"


def current_handlers(approval_request, business_doc):
    """Nguoi dang giu phieu NGAY LUC NAY. [] neu khong co ai de nhac."""
    if not approval_request:
        return []
    st = approval_request.get("approval_status")
    if st == "Pending" and approval_request.get("current_level"):
        rows = frappe.get_all("EC Approval Request Approver",
                              filters={"approval_request": approval_request.name,
                                       "level_no": approval_request.current_level,
                                       "status": "Pending"}, pluck="approver")
        return sorted({u for u in rows if u})
    if st == "Approved" and business_doc.get("fulfillment_status") in ("Assigned", "In Progress"):
        owner = business_doc.get("fulfillment_owner")
        if owner:
            return [owner]
        rows = frappe.get_all("ToDo", filters={"reference_type": business_doc.doctype,
                                               "reference_name": business_doc.name,
                                               "status": "Open"}, pluck="allocated_to")
        return sorted({u for u in rows if u})
    return []


def last_reminded_at(approval_request_name):
    rows = frappe.get_all("EC Approval Action", filters={"approval_request": approval_request_name,
                                                         "action": ACTION},
                          pluck="action_time", order_by="action_time desc", limit_page_length=1)
    return rows[0] if rows else None


def wait_seconds(approval_request_name, now=None):
    last = last_reminded_at(approval_request_name)
    if not last:
        return 0
    passed = (get_datetime(now or now_datetime()) - get_datetime(last)).total_seconds()
    return max(0, int(COOLDOWN_SECONDS - passed))


def capability(user, business_doc, approval_request):
    """-> (can_remind, wait_seconds). Chi tinh cho nguoi gui (do ton truy van voi nguoi khac)."""
    if not approval_request or business_doc.get("requested_by") != user:
        return False, 0
    if not current_handlers(approval_request, business_doc):
        return False, 0
    return True, wait_seconds(approval_request.name)


def remind(definition, name):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    user = frappe.session.user
    doc = frappe.get_doc(definition.business_doctype, name)
    if doc.get("requested_by") != user:
        frappe.throw(_("Chỉ người gửi phiếu mới nhắc được."), frappe.PermissionError)
    if not doc.get("approval_request"):
        frappe.throw(_("Phiếu chưa được gửi."))
    frappe.db.get_value(_REQ, doc.approval_request, "name", for_update=True)   # chong bam dup
    req = frappe.get_doc(_REQ, doc.approval_request)
    who = current_handlers(req, doc)
    if not who:
        frappe.throw(_("Hiện không có ai đang xử lý phiếu này để nhắc."))
    wait = wait_seconds(req.name)
    if wait:
        frappe.throw(_("Vừa nhắc xong. Nhắc lại được sau {0} phút.").format(max(1, (wait + 59) // 60)))
    sender = frappe.db.get_value("User", user, "full_name") or user
    engine.notify(who, _("🔔 {0} nhắc bạn xử lý: {1}").format(
        sender, engine.request_label(definition.business_doctype, name)),
        definition.business_doctype, name)
    engine.log_action(req.name, ACTION, user, req.get("current_level") or None,
                      comment=_("Nhắc: {0}").format(", ".join(who)))
    return {"reminded": who, "wait_seconds": COOLDOWN_SECONDS}
