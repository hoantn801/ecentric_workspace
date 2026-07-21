# Copyright (c) 2026, eCentric and contributors
"""Action Center: canonical route resolvers.

Single source of truth for converting (reference_type, reference_name) into:
  - source_key / source_label / action_label   (UI metadata)
  - action_url                                  (the link the user clicks)

The previous homepage widget hard-coded `/approval?id=...&type=...` for
EVERY ToDo, which broke Weekly Team Update and Task items. Centralise the
mapping here so the rule lives in one place and is reused by:
  - ecentric_workspace.action_center.api.get_action_items  (homepage feed)
  - ecentric_workspace.api._notify_approver                 (email link)

All path/query params are URL-encoded via urllib.parse.quote.
"""

from urllib.parse import quote as _q

import frappe


WTU = "Weekly Team Update"
TASK = "Task"

# Approval-style DocTypes (route /approval?id=&type=).
APPROVAL_DOCTYPES = frozenset({
    "GBS Purchase Order",
    "GBS Sales Order",
    "MSO Request",
    "SO Request",
    "PO Request",
    "REC Request",
    "Vendor Code Request",
    "Brand Approver",
    "Sales Order",
    "Leave Application",
})


def build_approval_url(doctype, name):
    """Canonical /approval URL.

    Shared by Action Center feed and ecentric_workspace.api._notify_approver
    so the email and the homepage card always point at the same URL.
    """
    t = (doctype or "").lower().replace(" ", "_")
    return "/approval?id=" + _q(str(name or ""), safe="") + "&type=" + _q(t, safe="")


def build_wtu_url(week_label):
    """Weekly Update form deep-link. UI reads URLSearchParams.get('week')."""
    return "/weekly-update?week=" + _q(str(week_label or ""), safe="")


def build_task_url(name):
    """Frappe-native Task desk form (the only canonical individual-Task URL)."""
    return "/app/task/" + _q(str(name or ""), safe="")


def build_desk_fallback_url(doctype, name):
    """Frappe Desk fallback for unknown DocTypes.

    DocType slug: lowercase, spaces -> dashes (also underscores -> dashes to
    match Frappe's website route slugging).
    """
    slug = (doctype or "").lower().replace(" ", "-").replace("_", "-")
    return "/app/" + _q(slug, safe="") + "/" + _q(str(name or ""), safe="")


_WTU_SRC = {
    "source_key": "weekly_report",
    "source_label": "BÁO CÁO TUẦN",
    "action_label": "Điền báo cáo",
}
_TASK_SRC = {
    "source_key": "task",
    "source_label": "CÔNG VIỆC",
    "action_label": "Xem công việc",
}
_APPROVAL_SRC = {
    "source_key": "approval",
    "source_label": "PHÊ DUYỆT",
    "action_label": "Phê duyệt",
}
_GENERIC_SRC = {
    "source_key": "generic",
    "source_label": "VIỆC",
    "action_label": "Mở",
}


def resolve_item(todo_row):
    """Build the canonical Action Center item from a tabToDo row.

    todo_row keys (from gbs_user_pending_todos SQL or equivalent):
      name, description, reference_type, reference_name, priority, modified
    Optional: date (ToDo.date / due date)
    """
    ref_type = (todo_row.get("reference_type") or "").strip()
    ref_name = (todo_row.get("reference_name") or "").strip()
    description = todo_row.get("description") or ""
    todo_name = todo_row.get("name") or ""
    priority = todo_row.get("priority") or "Medium"
    modified = todo_row.get("modified")
    due = todo_row.get("date") or todo_row.get("due_at") or ""

    title = ""
    subtitle = ""
    action_url = ""
    src = _GENERIC_SRC

    if ref_type == WTU and ref_name:
        src = _WTU_SRC
        wl = frappe.db.get_value(WTU, ref_name, "week_label") or ""
        title = ("Báo cáo tuần " + wl) if wl else "Báo cáo tuần"
        subtitle = ref_name
        action_url = build_wtu_url(wl)
    elif ref_type == TASK and ref_name:
        src = _TASK_SRC
        title = frappe.db.get_value(TASK, ref_name, "subject") or ref_name
        subtitle = ref_name
        action_url = build_task_url(ref_name)
    elif ref_type in APPROVAL_DOCTYPES and ref_name:
        src = _APPROVAL_SRC
        info = frappe.db.get_value(ref_type, ref_name, ["title", "name"], as_dict=True) or {}
        title = info.get("title") or info.get("name") or ref_name
        subtitle = ref_type + " · " + ref_name
        action_url = build_approval_url(ref_type, ref_name)
    elif ref_type and ref_name:
        # Unknown DocType with a reference -> safe Desk fallback.
        src = _GENERIC_SRC
        title = ref_name
        subtitle = ref_type
        action_url = build_desk_fallback_url(ref_type, ref_name)
    else:
        # Bare ToDo with no reference -> link to the ToDo itself in Desk.
        src = _GENERIC_SRC
        title = (description[:80] or todo_name) if description else todo_name
        subtitle = ""
        action_url = "/app/todo/" + _q(str(todo_name or ""), safe="")

    return {
        "todo_name": todo_name,
        "reference_type": ref_type,
        "reference_name": ref_name,
        "source_key": src["source_key"],
        "source_label": src["source_label"],
        "action_label": src["action_label"],
        "title": title,
        "subtitle": subtitle,
        "action_url": action_url,
        "priority": priority,
        "due_at": str(due) if due else "",
        "modified": str(modified) if modified else "",
        # ---- v1 additive canonical fields (2C.2 shared provider) ----------
        # Aliases + derived state; NOTHING above changed or removed, so the
        # existing homepage widget / any consumer of v0 keeps working.
        "source_type": src["source_key"],
        "source_id": (ref_type + "/" + ref_name) if (ref_type and ref_name) else todo_name,
        "status": todo_row.get("status") or "Open",
        # resolution is DERIVED: an item exists only while its governed source
        # keeps the ToDo open (engine/WTU/PM close it); never stored here.
        "resolution_state": "open",
        # bucket is filled by the API layer (needs "today"); default here so
        # the key always exists for consumers.
        "bucket": "undated",
    }


# ---- v1 pure helpers (no frappe import: unit-testable) -----------------------

BUCKETS = ("overdue", "today", "upcoming", "undated")


def bucket_for(due_at, today):
    """Classify a due datetime/date/ISO-string against `today` (a date).

    Contract (2C.2): a missing/unparseable due date is EXPLICITLY "undated"
    (hiển thị "Không hạn") -- never infer or fake a date.
    """
    if not due_at:
        return "undated"
    s = str(due_at).strip()
    if not s:
        return "undated"
    d = _parse_date(s)
    if d is None:
        return "undated"
    if d < today:
        return "overdue"
    if d == today:
        return "today"
    return "upcoming"


def _parse_date(s):
    """date part of 'YYYY-MM-DD[ HH:MM:SS]' -> datetime.date, else None."""
    import datetime
    part = s[:10]
    try:
        return datetime.date(int(part[0:4]), int(part[5:7]), int(part[8:10]))
    except (ValueError, IndexError):
        return None
