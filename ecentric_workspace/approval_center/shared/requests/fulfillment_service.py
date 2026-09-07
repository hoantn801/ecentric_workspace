"""Shared application service for request-type fulfillment endpoints."""
import frappe

from ecentric_workspace.approval_center.shared.workflow import transitions
from ecentric_workspace.approval_center.shared.workflow.permissions import is_eligible_fulfiller
from ecentric_workspace.approval_center.shared.workflow.permissions import is_system_manager


def list_queue(definition, section, fields, order_by):
    user = frappe.session.user
    if not is_eligible_fulfiller(user, approval_type=definition.code,
                                 business_doctype=definition.business_doctype):
        return {"rows": []}
    if section == "unclaimed":
        filters = {"fulfillment_status": "Assigned"}
    elif section == "mine":
        filters = {"fulfillment_owner": user,
                   "fulfillment_status": ["in", ["Assigned", "In Progress"]]}
    else:
        filters = {"fulfillment_status": "In Progress", "fulfillment_owner": ["!=", user]}
    return {"rows": frappe.get_all(
        definition.business_doctype, filters=filters, fields=list(fields),
        order_by=order_by, limit_page_length=200)}


def claim(definition, name):
    service = __import__(
        "ecentric_workspace.approval_center.features.%s.application.service" % definition.feature,
        fromlist=["claim_fulfillment"])
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        result = service.claim_fulfillment(name)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []
    return result


def complete(definition, name, payload=None):
    service = __import__(
        "ecentric_workspace.approval_center.features.%s.application.service" % definition.feature,
        fromlist=["complete_fulfillment"])
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        service.complete_fulfillment(name, payload=payload)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []






_ACTIVE_FULFILLMENT = ("Assigned", "In Progress")


def _reassign_snapshot(definition, name):
    snap = frappe.db.get_value(
        definition.business_doctype, name,
        ["fulfillment_status", "fulfillment_owner", "approval_request", "requested_by"],
        as_dict=True)
    if not snap:
        frappe.throw(frappe._("Khong tim thay yeu cau."))
    return snap


def _assert_may_reassign(snap):
    """Cung luat voi engine (`_assert_owner_or_sm`), kiem SOM de UI khong chao mot
    danh sach nguoi nhan cho ai do khong co quyen chuyen. Engine van kiem lai khi ghi -
    day chi la cua truoc, khong phai luat thu hai."""
    user = frappe.session.user
    if snap.get("fulfillment_owner") != user and not is_system_manager(user):
        frappe.throw(frappe._("Chi nguoi dang xu ly hoac quan tri moi chuyen duoc viec nay."),
                     frappe.PermissionError)


def reassign_targets(definition, name):
    """Nhung nguoi CO THE nhan viec cua chinh phieu nay = Fulfiller da cau hinh tren quy
    trinh dang Active, tru chinh nguoi dang giu. Tra ve ca `full_name` de man hinh khong
    bat nguoi dung doc email tran."""
    snap = _reassign_snapshot(definition, name)
    _assert_may_reassign(snap)
    if snap.get("fulfillment_status") not in _ACTIVE_FULFILLMENT:
        return {"targets": [], "current_owner": snap.get("fulfillment_owner")}
    users = transitions.resolve_fulfillers(
        snap.get("approval_request"), snap.get("requested_by")) or set()
    users.discard(snap.get("fulfillment_owner"))
    rows = []
    if users:
        rows = frappe.get_all("User", filters={"name": ["in", sorted(users)], "enabled": 1},
                              fields=["name", "full_name"], order_by="full_name asc")
    return {"targets": rows, "current_owner": snap.get("fulfillment_owner")}


def reassign(definition, name, new_user):
    """Chuyen viec sang nguoi khac. Uy quyen TOAN BO luat cho engine
    (`transitions.reassign_fulfillment`): no kiem nguoi chuyen, kiem nguoi nhan co thuc su
    du dieu kien khong, dong ToDo cu, mo dung mot ToDo moi, ghi audit va bao Teams.
    Khong tu che luat thu hai o day."""
    snap = _reassign_snapshot(definition, name)
    _assert_may_reassign(snap)
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        result = transitions.reassign_fulfillment(definition.business_doctype, name, new_user)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []
    return result
