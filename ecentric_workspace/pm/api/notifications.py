"""PM v2 - Notifications (basic, in-app only).

Uses NATIVE Frappe `Notification Log` (the desk bell / in-app notifications). NO
email in this phase. Triggers: task assigned, workflow transition, overdue (daily
scheduler), recurring task generated.

Anti-spam:
  - never notify the actor (from_user) or duplicates within a call,
  - overdue: deduped to once per day per task per user (dedup_key "[Overdue]"),
  - transition/assign: one-off events (fired only by the action itself).
"""

import frappe
from frappe import _
from frappe.utils import nowdate, getdate, today

from ecentric_workspace.pm import permissions as pmperm


def notify_users(users, subject, task_name, from_user=None, dedup_key=None):
    """Create in-app Notification Log entries (no email) for `users` (emails)."""
    from_user = from_user or frappe.session.user
    seen = set()
    for u in users or []:
        if not u or u == from_user or u in seen or u == "Administrator":
            continue
        seen.add(u)
        if dedup_key and frappe.db.exists("Notification Log", {
            "for_user": u, "document_type": "Task", "document_name": task_name,
            "subject": ["like", "%" + dedup_key + "%"],
            "creation": [">=", today() + " 00:00:00"],
        }):
            continue
        try:
            frappe.get_doc({
                "doctype": "Notification Log", "for_user": u, "from_user": from_user,
                "subject": subject, "type": "Alert",
                "document_type": "Task", "document_name": task_name,
            }).insert(ignore_permissions=True)
        except Exception:
            frappe.log_error(frappe.get_traceback(), "PM notify_users")


def _task_recipients(doc, exclude=None):
    """Owner + assignees of a task, excluding `exclude` (e.g. the actor)."""
    users = []
    if doc.get("owner"):
        users.append(doc["owner"])
    if doc.get("_assign"):
        try:
            users += (frappe.parse_json(doc["_assign"]) or [])
        except Exception:
            pass
    return [u for u in users if u and u != exclude]


# --------------------------------------------------------------------------
# Read (PM "Thong bao" page)
# --------------------------------------------------------------------------
@frappe.whitelist()
def list_mine(limit=30):
    pmperm.require_pm_access()
    user = frappe.session.user
    rows = frappe.get_all(
        "Notification Log", filters={"for_user": user, "document_type": "Task"},
        fields=["name", "subject", "document_name", "read", "creation", "from_user", "type"],
        order_by="creation desc", limit_page_length=int(limit))
    unread = frappe.db.count("Notification Log", {"for_user": user, "document_type": "Task", "read": 0})
    return {"rows": rows, "unread": unread}


@frappe.whitelist()
def mark_read(name=None):
    user = frappe.session.user
    if name:
        if frappe.db.get_value("Notification Log", name, "for_user") == user:
            frappe.db.set_value("Notification Log", name, "read", 1)
    else:
        frappe.db.sql("update `tabNotification Log` set `read`=1 where for_user=%s and document_type='Task'", user)
    frappe.db.commit()
    return {"ok": True}


# --------------------------------------------------------------------------
# Overdue daily scheduler
# --------------------------------------------------------------------------
def pm_overdue_scan():
    """Daily: notify assignees (or owner) of overdue tasks, once/day/task/user."""
    today_d = getdate(nowdate())
    tasks = frappe.get_all(
        "Task", filters={"exp_end_date": ["<", today_d],
                         "workflow_state": ["not in", ["Done", "Cancelled"]]},
        fields=["name", "subject", "_assign", "owner"], limit_page_length=0)
    for t in tasks:
        users = []
        if t.get("_assign"):
            try:
                users = frappe.parse_json(t["_assign"]) or []
            except Exception:
                users = []
        if not users and t.get("owner"):
            users = [t["owner"]]
        if not users:
            continue
        subject = "[Overdue] Nhiem vu qua han: " + (t.get("subject") or t["name"])
        notify_users(users, subject, t["name"], from_user="Administrator", dedup_key="[Overdue]")
    frappe.db.commit()


@frappe.whitelist()
def overdue_scan_once():
    """Admin/test trigger to run the overdue scan now (daily scheduler equivalent)."""
    if frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles():
        frappe.throw(_("Admin only."), frappe.PermissionError)
    pm_overdue_scan()
    return {"ok": True}
