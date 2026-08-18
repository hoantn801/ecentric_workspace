"""Immutable command adapters and validation for the four legacy finance forms."""
from dataclasses import dataclass
from importlib import import_module


class _LazyFrappe:
    def __getattr__(self, name):
        return getattr(import_module("frappe"), name)


frappe = _LazyFrappe()


def _(message):
    return frappe._(message)


def getdate(value):
    return import_module("frappe.utils").getdate(value)


def now_datetime():
    return import_module("frappe.utils").now_datetime()


def _employee(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "company"], as_dict=True)


def _manager(user):
    employee = frappe.db.get_value("Employee", {"user_id": user},
                                   ["name", "reports_to"], as_dict=True)
    manager = employee and employee.reports_to and frappe.db.get_value(
        "Employee", employee.reports_to, "user_id")
    row = manager and frappe.db.get_value("User", manager, ["enabled", "user_type"], as_dict=True)
    return manager if row and row.enabled and row.user_type == "System User" else None


@dataclass(frozen=True, slots=True)
class Submitter:
    doctype: str
    code: str
    validator: object
    title_builder: object
    manager_required: bool = False
    requester_esign: bool = False

    def __call__(self, name):
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        user = frappe.session.user
        document = frappe.get_doc(self.doctype, name)
        if document.approval_request:
            frappe.throw(_("YÃƒÆ’Ã‚Âªu cÃƒÂ¡Ã‚ÂºÃ‚Â§u nÃƒÆ’Ã‚Â y Ãƒâ€žÃ¢â‚¬ËœÃƒÆ’Ã‚Â£ Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c gÃƒÂ¡Ã‚Â»Ã‚Â­i."))
        if (document.requested_by and document.requested_by != user
                and "System Manager" not in frappe.get_roles(user)):
            frappe.throw(_("BÃƒÂ¡Ã‚ÂºÃ‚Â¡n chÃƒÂ¡Ã‚Â»Ã¢â‚¬Â° cÃƒÆ’Ã‚Â³ thÃƒÂ¡Ã‚Â»Ã†â€™ gÃƒÂ¡Ã‚Â»Ã‚Â­i yÃƒÆ’Ã‚Âªu cÃƒÂ¡Ã‚ÂºÃ‚Â§u cÃƒÂ¡Ã‚Â»Ã‚Â§a chÃƒÆ’Ã‚Â­nh mÃƒÆ’Ã‚Â¬nh."), frappe.PermissionError)
        document.requested_by = document.requested_by or user
        employee = _employee(document.requested_by)
        if employee:
            document.employee = employee.name
            document.company = document.company or employee.company
        self.validator(document)
        if self.manager_required and not _manager(document.requested_by):
            frappe.throw(_("KhÃƒÆ’Ã‚Â´ng xÃƒÆ’Ã‚Â¡c Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¹nh Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c QuÃƒÂ¡Ã‚ÂºÃ‚Â£n lÃƒÆ’Ã‚Â½ trÃƒÂ¡Ã‚Â»Ã‚Â±c tiÃƒÂ¡Ã‚ÂºÃ‚Â¿p cÃƒÂ¡Ã‚Â»Ã‚Â§a bÃƒÂ¡Ã‚ÂºÃ‚Â¡n. Vui lÃƒÆ’Ã‚Â²ng liÃƒÆ’Ã‚Âªn hÃƒÂ¡Ã‚Â»Ã¢â‚¬Â¡ HR/Admin "
                           "Ãƒâ€žÃ¢â‚¬ËœÃƒÂ¡Ã‚Â»Ã†â€™ cÃƒÂ¡Ã‚ÂºÃ‚Â­p nhÃƒÂ¡Ã‚ÂºÃ‚Â­t 'BÃƒÆ’Ã‚Â¡o cÃƒÆ’Ã‚Â¡o cho' (reports_to) trong hÃƒÂ¡Ã‚Â»Ã¢â‚¬Å“ sÃƒâ€ Ã‚Â¡ nhÃƒÆ’Ã‚Â¢n sÃƒÂ¡Ã‚Â»Ã‚Â± trÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã¢â‚¬Âºc khi gÃƒÂ¡Ã‚Â»Ã‚Â­i yÃƒÆ’Ã‚Âªu cÃƒÂ¡Ã‚ÂºÃ‚Â§u."))
        document.request_title = self.title_builder(document)
        document.submitted_at = now_datetime()
        document.save(ignore_permissions=True)
        signature_required = False
        if self.requester_esign:
            from ecentric_workspace.platform.esign import guard
            signature_required = guard.requester_signature_required(self.doctype, self.code)
        previous = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            request_name = engine.submit(
                self.doctype, document.name, self.code, document.requested_by,
                **({"activate_first_level": not signature_required} if self.requester_esign else {}))
        finally:
            frappe.flags.mute_messages = previous
        frappe.db.set_value(self.doctype, document.name, "approval_request", request_name)
        if signature_required:
            frappe.db.set_value("EC Approval Request", request_name,
                                "requester_signature_status", "Pending")
        frappe.local.message_log = []
        return request_name


@dataclass(frozen=True, slots=True)
class Resubmitter:
    doctype: str
    title_builder: object

    def __call__(self, name, actor=None):
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        document = frappe.get_doc(self.doctype, name)
        if not document.approval_request:
            frappe.throw(_("YÃƒÆ’Ã‚Âªu cÃƒÂ¡Ã‚ÂºÃ‚Â§u nÃƒÆ’Ã‚Â y chÃƒâ€ Ã‚Â°a Ãƒâ€žÃ¢â‚¬ËœÃƒâ€ Ã‚Â°ÃƒÂ¡Ã‚Â»Ã‚Â£c gÃƒÂ¡Ã‚Â»Ã‚Â­i."))
        frappe.db.set_value(self.doctype, name, "request_title", self.title_builder(document))
        previous = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            engine.resubmit(document.approval_request, actor=actor or frappe.session.user)
        finally:
            frappe.flags.mute_messages = previous
        return {"restarted": True}

