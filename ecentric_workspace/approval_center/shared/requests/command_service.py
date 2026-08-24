"""Generic request commands delegating authoritative transitions to the engine."""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.requests import capabilities, query_service


def claim_uploaded_files(document):
    """Stop Frappe creating a SECOND File row for the same upload.

    The forms upload through /api/method/upload_file without a `fieldname`, so the File row
    is stored with attached_to_field empty. Frappe's attach_files_to_document hook (on_update)
    looks for an existing File matching doctype+name+url+FIELD; the empty field never matches,
    so it inserts a duplicate row for the Attach field and the attachment list shows every
    file twice.

    Called right before save: for each Attach field carrying a value, adopt the orphan row
    (same doc + same url, no field yet) by stamping the fieldname on it, so the hook's check
    matches and no duplicate is inserted. Best-effort: never blocks the save."""
    try:
        attach_fields = [df.fieldname for df in document.meta.fields
                         if df.fieldtype in ("Attach", "Attach Image")]
    except Exception:
        return
    for fieldname in attach_fields:
        url = (document.get(fieldname) or "").strip()
        if not url.startswith(("/files", "/private/files")):
            continue
        try:
            if frappe.db.exists("File", {"file_url": url, "attached_to_doctype": document.doctype,
                                         "attached_to_name": document.name,
                                         "attached_to_field": fieldname}):
                continue
            orphan = frappe.db.get_value("File", {"file_url": url,
                                                  "attached_to_doctype": document.doctype,
                                                  "attached_to_name": document.name,
                                                  "attached_to_field": ["in", ["", None]]}, "name")
            if orphan:
                frappe.db.set_value("File", orphan, "attached_to_field", fieldname)
        except Exception:
            frappe.logger("approval_center").warning(
                "claim_uploaded_files: could not adopt file for %s.%s" % (document.doctype, fieldname))


def save_draft(definition, name=None, payload=None):
    user = frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    if name:
        document = frappe.get_doc(definition.business_doctype, name)
        request = capabilities.approval_request_for(definition, name)
        if document.requested_by != user and not capabilities.is_system_manager(user):
            frappe.throw(_("Bạn chỉ có thể sửa yêu cầu của mình."), frappe.PermissionError)
        if request and request.approval_status != "Information Required":
            frappe.throw(_("Chỉ có thể sửa yêu cầu ở trạng thái Nháp hoặc Cần bổ sung."))
    else:
        document = frappe.new_doc(definition.business_doctype)
        document.requested_by = user
    for fieldname in definition.editable_fields:
        if fieldname in data:
            document.set(fieldname, data.get(fieldname))
    context = query_service.employee_context(document.requested_by)
    document.employee = context["employee"]
    document.department = document.department or context["department"]
    document.company = document.company or context["company"]
    if definition.draft_preparer:
        definition.draft_preparer(document)
    if definition.title_builder:
        document.request_title = definition.title_builder(document)
    if document.name:
        claim_uploaded_files(document)   # adopt orphan File rows so the save does not duplicate them
    document.save(ignore_permissions=True)
    request = capabilities.approval_request_for(definition, document.name)
    return {"name": document.name,
            "capabilities": capabilities.derive(user, document, request)}


def submit(definition, name):
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        request_name = definition.submitter(name)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []
    return {"approval_request": request_name, "submitted": True,
            "detail": query_service.detail(definition, name)}


def resolve_request(definition, name):
    document = frappe.get_doc(definition.business_doctype, name)
    if not document.approval_request:
        frappe.throw(_("Yêu cầu này chưa được gửi."))
    return document, document.approval_request


def approve(definition, name, comment=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    engine.approve(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def approve_with_operation_date(definition, name, comment=None,
                                operation_expected_completion_date=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    current_level = frappe.db.get_value("EC Approval Request", request_name, "current_level")
    level_name = (frappe.db.get_value(
        "EC Approval Request Level",
        {"approval_request": request_name, "level_no": current_level}, "level_name")
        if current_level else None)
    if level_name == "Operation Review":
        new_value = operation_expected_completion_date or ""
        new_value = new_value.strip() if isinstance(new_value, str) else new_value
        existing = frappe.db.get_value(
            definition.business_doctype, name, "operation_expected_completion_date")
        if not existing and not new_value:
            frappe.throw(_("Vui long nhap ngay du kien hoan thanh (Operation) truoc khi duyet."))
        if new_value:
            frappe.db.set_value(
                definition.business_doctype, name,
                "operation_expected_completion_date", new_value)
    engine.approve(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def reject(definition, name, comment=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    engine.reject(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def request_information(definition, name, comment=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    _, request_name = resolve_request(definition, name)
    engine.request_information(request_name, comment=comment)
    return {"detail": query_service.detail(definition, name)}


def resubmit(definition, name, payload=None):
    if payload:
        save_draft(definition, name=name, payload=payload)
    result = definition.resubmitter(name, frappe.session.user)
    return {"restarted": bool(result.get("restarted")),
            "detail": query_service.detail(definition, name)}


def cancel(definition, name, reason=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    user = frappe.session.user
    document = frappe.get_doc(definition.business_doctype, name)
    request = capabilities.approval_request_for(definition, name)
    if not capabilities.derive(user, document, request)["can_cancel"]:
        frappe.throw(_("Bạn không được phép hủy yêu cầu này."), frappe.PermissionError)
    if request:
        engine.cancel(request.name, reason=reason)
        return {"detail": query_service.detail(definition, name)}
    frappe.delete_doc(definition.business_doctype, name, ignore_permissions=True)
    return {"deleted": True}


def admin_approve_current_level(definition, name, reason=None):
    from ecentric_workspace.approval_center.shared.workflow import transitions as engine
    if not capabilities.is_system_manager():
        frappe.throw(_("Chỉ System Manager mới được duyệt thay."), frappe.PermissionError)
    if not (reason or "").strip():
        frappe.throw(_("Vui lòng nhập lý do duyệt thay."))
    document, request_name = resolve_request(definition, name)
    request = capabilities.approval_request_for(definition, name)
    if not capabilities.derive(
            frappe.session.user, document, request)["can_admin_approve_current_level"]:
        frappe.throw(_("Không thể duyệt thay ở trạng thái hiện tại."))
    previous = frappe.flags.mute_messages
    frappe.flags.mute_messages = True
    try:
        engine.admin_override_current_level(
            request_name, actor=frappe.session.user, reason=reason)
    finally:
        frappe.flags.mute_messages = previous
    frappe.local.message_log = []
    return {"admin_approved": True, "detail": query_service.detail(definition, name)}




