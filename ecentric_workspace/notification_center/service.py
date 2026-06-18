# Copyright (c) 2026, eCentric and contributors
"""Notification Center: emit a Notification Log entry + a per-user realtime ping.

`emit()` is the ONE place that creates Notification Log rows for the center, so the
realtime contract lives in a single helper. The realtime payload is delivered ONLY to the
recipient (user=for_user) and contains ONLY that recipient's own item + fresh unread
count — never another user's data.

Pilot event (this batch): a Weekly Team Update was created -> tell the submitter their
report is ready. Already-Submitted / Reviewed updates are never (re)notified.
"""

import frappe

from ecentric_workspace.notification_center.resolvers import resolve_notification

WTU = "Weekly Team Update"
TERMINAL_STATES = ("Submitted", "Reviewed")
REALTIME_EVENT = "ec_notification"


def emit(for_user, subject, message="", document_type=None, document_name=None,
         from_user=None, notif_type="Alert"):
    """Create a native Notification Log for `for_user` and publish a realtime ping to
    that user only. Returns the new Notification Log name (or None if skipped)."""
    if not for_user or for_user == "Guest":
        return None
    from_user = from_user or frappe.session.user
    doc = frappe.get_doc({
        "doctype": "Notification Log",
        "for_user": for_user,
        "from_user": from_user,
        "subject": subject or "",
        "email_content": message or "",
        "type": notif_type,
        "document_type": document_type or "",
        "document_name": document_name or "",
    }).insert(ignore_permissions=True)

    # Realtime ping — scoped to the recipient; payload is ONLY their own item + count.
    try:
        item = resolve_notification({
            "name": doc.name, "subject": subject, "email_content": message,
            "document_type": document_type, "document_name": document_name,
            "from_user": from_user, "read": 0, "type": notif_type,
            "creation": doc.creation,
        })
        unread = frappe.db.count("Notification Log", {"for_user": for_user, "read": 0})
        frappe.publish_realtime(
            event=REALTIME_EVENT,
            message={"item": item, "unread": unread},
            user=for_user,          # deliver ONLY to the recipient's room
            after_commit=True,      # fire after the row is committed + queryable
        )
    except Exception:
        frappe.log_error(frappe.get_traceback(), "notification_center.emit realtime")
    return doc.name


def notify_weekly_update_created(wtu_name, for_user, week_label, due_display=""):
    """Pilot integration: a Weekly Team Update was created. Notify the submitter that
    their weekly report is ready, with a deep link to /weekly-update?week=<label>.
    Skips if the WTU is already terminal (Submitted/Reviewed)."""
    if frappe.db.get_value(WTU, wtu_name, "status") in TERMINAL_STATES:
        return None
    label = str(week_label or "")
    subject = "Báo cáo tuần " + label + " đã sẵn sàng"
    message = "Báo cáo tuần " + label + " đã sẵn sàng."
    if due_display:
        message += " Hạn nộp: " + str(due_display)
    return emit(for_user, subject, message,
                document_type=WTU, document_name=wtu_name,
                from_user="Administrator", notif_type="Alert")
