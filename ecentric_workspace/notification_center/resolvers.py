# Copyright (c) 2026, eCentric and contributors
"""Notification Center: map a native Notification Log row to a canonical item.

Notification Log is keyed on (document_type, document_name) plus subject / email_content.
The clickable `action_url` is built by REUSING the Action Center URL builders, so the
"which DocType -> which route" rule lives in ONE place
(ecentric_workspace.action_center.resolvers). Notification Center never re-implements URL
logic and the frontend never builds routes.

Canonical item shape (the only contract the frontend depends on):
    {name, subject, message, source_type, source_label,
     action_url, is_read, created_at, from_user}
"""

import frappe

from ecentric_workspace.action_center import resolvers as ac

WTU = "Weekly Team Update"
TASK = "Task"

# document_type -> (source_type, source_label) for the UI chip. Unknown -> generic.
_SOURCE = {
    WTU: ("weekly_report", "BÁO CÁO TUẦN"),
    TASK: ("task", "CÔNG VIỆC"),
}


def _action_url(document_type, document_name):
    """Canonical click target, delegated to the Action Center builders (all of which
    URL-encode their params). An item with no source reference yields '' (the frontend
    renders it as non-clickable)."""
    dt = (document_type or "").strip()
    dn = (document_name or "").strip()
    if not dt or not dn:
        return ""
    if dt == WTU:
        wl = frappe.db.get_value(WTU, dn, "week_label") or ""
        return ac.build_wtu_url(wl)
    if dt == TASK:
        return ac.build_task_url(dn)
    if dt in ac.APPROVAL_DOCTYPES:
        return ac.build_approval_url(dt, dn)
    return ac.build_desk_fallback_url(dt, dn)


def _source(document_type):
    return _SOURCE.get((document_type or "").strip(), ("system", "HỆ THỐNG"))


def resolve_notification(row):
    """row: a Notification Log dict (name, subject, email_content, document_type,
    document_name, from_user, read, type, creation). Returns the canonical item.
    `message` is treated as TEXT by the frontend (escaped on render)."""
    dt = row.get("document_type") or ""
    dn = row.get("document_name") or ""
    source_type, source_label = _source(dt)
    return {
        "name": row.get("name"),
        "subject": row.get("subject") or "",
        "message": row.get("email_content") or "",
        "source_type": source_type,
        "source_label": source_label,
        "action_url": _action_url(dt, dn),
        "is_read": 1 if row.get("read") else 0,
        "created_at": str(row.get("creation") or ""),
        "from_user": row.get("from_user") or "",
    }
