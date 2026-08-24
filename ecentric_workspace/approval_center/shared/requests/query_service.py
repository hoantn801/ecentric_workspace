"""Permission-safe generic queries and projections for approval request types."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.requests import capabilities


def requester_display(user):
    """Resolve Employee/User display name without leaking lookup failures."""
    if not user:
        return None
    try:
        employee_name = frappe.db.get_value(
            "Employee", {"user_id": user}, "employee_name")
        if employee_name:
            return employee_name
        return frappe.db.get_value("User", user, "full_name") or user
    except Exception:
        return user


def employee_context(user=None):
    user = user or frappe.session.user
    employee = frappe.db.get_value(
        "Employee", {"user_id": user},
        ["name", "employee_name", "department", "company", "reports_to"], as_dict=True)
    manager_user = None
    if employee and employee.reports_to:
        manager_user = frappe.db.get_value("Employee", employee.reports_to, "user_id")
    return {
        "user": user,
        "employee": employee.name if employee else None,
        "employee_name": employee.employee_name if employee else None,
        "department": employee.department if employee else None,
        "company": employee.company if employee else None,
        "manager_user": manager_user,
        "manager_resolvable": bool(manager_user),
    }


def process_preview(approval_type):
    processes = frappe.get_all(
        "EC Approval Process", filters={"approval_type": approval_type, "status": "Active"},
        pluck="name")
    if not processes:
        processes = frappe.get_all(
            "EC Approval Process", filters={"approval_type": approval_type, "status": "Draft"},
            order_by="creation desc", pluck="name")
    if not processes:
        return []
    return frappe.get_all(
        "EC Approval Level", filters={"approval_process": processes[0]},
        fields=["level_no", "level_name"], order_by="level_no asc")


def _can_fulfil(user, definition):
    """Canonical engine rule for 'may this user work the fulfillment queue'.

    The form pages gate their Operation/fulfillment tab on tabs.fulfillment; the shared
    bootstrap never set it (only ai_topup, which kept a bespoke controller, did), so after
    the forms moved onto the shared adapter the tab silently disappeared and nobody could
    claim an approved request -- even though list_fulfillment_queue happily returned it.
    Best-effort: any failure hides the tab rather than breaking the page."""
    try:
        from ecentric_workspace.approval_center.shared.workflow import permissions as _perm
        return bool(_perm.is_eligible_fulfiller(user, definition.code, definition.business_doctype))
    except Exception:
        return False


def bootstrap(definition):
    user = frappe.session.user
    admin = capabilities.is_system_manager(user)
    return {
        "context": employee_context(user),
        "is_system_manager": admin,
        "tabs": {"create": True, "my_requests": True,
                 "my_approvals": capabilities.has_any_approver_row(user) or admin,
                 "fulfillment": _can_fulfil(user, definition)},
        "form_options": definition.options_provider(),
    }


def list_my_requests(definition, filters=None, start=0, page_length=20):
    user = frappe.session.user
    db_filters = {"requested_by": user}
    supplied = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    if definition.filter_builder:
        definition.filter_builder(db_filters, supplied)
    page_length = min(int(page_length or 20), definition.max_page_length)
    total = frappe.db.count(definition.business_doctype, db_filters)
    rows = frappe.get_all(
        definition.business_doctype, filters=db_filters, fields=list(definition.my_request_fields),
        limit_start=int(start), limit_page_length=page_length, order_by="modified desc")
    active_level_count = None
    for row in rows:
        approval = row.approval_request and frappe.db.get_value(
            "EC Approval Request", row.approval_request,
            ["approval_status", "current_level"], as_dict=True)
        row["approval_status"] = approval.approval_status if approval else "Draft"
        row["current_level"] = approval.current_level if approval else 0
        row["requested_at"] = row.get("creation")
        row["requester_name"] = requester_display(user)
        if row.approval_request:
            row["total_levels"] = frappe.db.count(
                "EC Approval Request Level", {"approval_request": row.approval_request})
            row["current_level_name"] = (
                frappe.db.get_value(
                    "EC Approval Request Level",
                    {"approval_request": row.approval_request,
                     "level_no": row["current_level"]}, "level_name")
                if row["current_level"] else None)
        else:
            if active_level_count is None:
                active_level_count = len(process_preview(definition.code))
            row["total_levels"] = active_level_count
            row["current_level_name"] = None
    return {"rows": rows, "total": total}


def list_my_approvals(definition, section="pending"):
    user = frappe.session.user
    statuses = (["Pending"] if section == "pending"
                else ["Approved", "Rejected", "Information Requested", "Skipped"])
    rows = frappe.get_all(
        "EC Approval Request Approver",
        filters={"approver": user, "status": ["in", statuses]},
        fields=["approval_request", "level_no", "status", "decided_at"],
        order_by="modified desc", limit_page_length=200)
    output = []
    for row in rows:
        request = frappe.db.get_value(
            "EC Approval Request", row.approval_request,
            ["reference_name", "approval_status", "current_level", "requested_by"], as_dict=True)
        if not request:
            continue
        if (section == "pending"
                and (request.approval_status not in capabilities.OPEN_STATUSES
                     or request.current_level != row.level_no)):
            continue
        business = frappe.db.get_value(
            definition.business_doctype, request.reference_name,
            list(definition.approval_list_fields), as_dict=True)
        if not business:
            continue
        current_name = (
            frappe.db.get_value(
                "EC Approval Request Level",
                {"approval_request": row.approval_request,
                 "level_no": request.current_level}, "level_name")
            if request.current_level else None)
        business["requested_at"] = business.get("creation")
        business["requester_name"] = requester_display(request.requested_by)
        projection = {
            "approval_request": row.approval_request, "level_no": row.level_no,
            "approval_status": request.approval_status,
            "requested_by": request.requested_by, "my_status": row.status,
            "total_levels": frappe.db.count(
                "EC Approval Request Level", {"approval_request": row.approval_request}),
        }
        if definition.approval_projection == "legacy_level_name":
            projection["level_name"] = frappe.db.get_value(
                "EC Approval Request Level",
                {"approval_request": row.approval_request, "level_no": row.level_no},
                "level_name")
        else:
            projection.update({"current_level": request.current_level,
                               "current_level_name": current_name})
        business.update(projection)
        output.append(business)
    return {"rows": output}


def dedupe_attachments(rows):
    """One row per physical file.

    Uploading through the form creates TWO File records for the same upload: the
    /api/method/upload_file call stores one with attached_to_field empty, then Frappe's
    standard attach_files_to_document hook -- whose duplicate check includes
    attached_to_field -- does not recognise it and stores a second one for the Attach
    field. Both point at the SAME file_url, so the attachment list showed every file
    twice. Collapse by file_url, keeping the earliest record."""
    seen, out = set(), []
    for r in rows or []:
        key = (r.get("file_url") or "").strip() or ("name:" + str(r.get("file_name") or ""))
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def detail(definition, name):
    user = frappe.session.user
    business = frappe.get_doc(definition.business_doctype, name)
    request = capabilities.approval_request_for(definition, name)
    if not capabilities.can_view(user, business, request):
        frappe.throw(_("Bạn không có quyền xem yêu cầu này."), frappe.PermissionError)
    levels, approvers, timeline = [], [], []
    if request:
        levels = frappe.get_all(
            "EC Approval Request Level", filters={"approval_request": request.name},
            fields=["level_no", "level_name", "approval_mode", "minimum_approvals",
                    "mandatory", "level_status", "activated_at", "completed_at", "due_at"],
            order_by="level_no asc")
        approvers = frappe.get_all(
            "EC Approval Request Approver", filters={"approval_request": request.name},
            fields=["level_no", "approver", "source", "status", "decided_at", "comment"],
            order_by="level_no asc")
        timeline = frappe.get_all(
            "EC Approval Action", filters={"approval_request": request.name},
            fields=["seq", "request_level", "actor", "action", "comment", "action_time",
                    "previous_status", "new_status"], order_by="seq asc")
        levels_by_name = {row.name: row for row in frappe.get_all(
            "EC Approval Request Level", filters={"approval_request": request.name},
            fields=["name", "level_no", "level_name"])}
        for action in timeline:
            level = levels_by_name.get(action.get("request_level"))
            if level:
                action["level_no"] = level.level_no
                action["level_name"] = level.level_name
    attachments = dedupe_attachments(frappe.get_all(
        "File", filters={"attached_to_doctype": definition.business_doctype,
                         "attached_to_name": name},
        fields=["file_name", "file_url", "is_private", "owner", "creation"],
        order_by="creation asc"))
    status = request.approval_status if request else "Draft"
    return {
        "business": business.as_dict(),
        "approval": {
            "name": request.name if request else None,
            "approval_status": status,
            "current_level": request.current_level if request else 0,
            "information_requested_from_level": (
                request.information_requested_from_level if request else None),
            "status_label": definition.status_label_map.get(status),
        },
        "levels": levels, "approvers": approvers, "attachments": attachments,
        "timeline": timeline,
        "process_preview": ([] if request else process_preview(
            business.approval_type or definition.code)),
        "capabilities": capabilities.derive(user, business, request),
    }




