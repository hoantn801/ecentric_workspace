# Copyright (c) 2026, eCentric and contributors
"""Truy cap du lieu Cong cu dung chung - NOI DUY NHAT goi frappe.db / frappe.get_doc / frappe.cache.
Chi doc / ghi, khong quyet dinh gi (luat o queue_rules.py, dieu phoi o service.py)."""
import json

import frappe

from ecentric_workspace.shared_tools import constants as C

QUEUE_FIELDS = ["name", "user", "full_name", "status", "joined_at", "ready_at", "started_at",
                "ends_at", "ended_at", "extended", "opens", "end_reason"]
EXPORT_FIELDS = ["name", "export_id", "run_id", "part", "source", "file_name", "file_url", "rows", "columns",
                 "pages", "page_title", "exported_at", "downloaded_at", "user"]


# ------------------------------------------------------------------ cong cu --
def tool(key):
    if not frappe.db.exists(C.TOOL_DT, key):
        return None
    return frappe.db.get_value(C.TOOL_DT, key, ["name", "title", "enabled", "allowed_role", "notice",
                                               "lease_minutes", "ready_minutes", "extend_minutes",
                                               "idle_minutes"], as_dict=True)


def set_tool_enabled(key, on):
    frappe.db.set_value(C.TOOL_DT, key, "enabled", 1 if on else 0, update_modified=True)


def lock_tool(key):
    """Khoa dong cong cu den het transaction: hai nguoi bam cung luc khong cung thanh Den luot."""
    frappe.db.sql("select name from `tabEC Shared Tool` where name=%s for update", (key,))


# ---------------------------------------------------------------- hang doi --
def open_entries(key):
    return frappe.get_all(C.QUEUE_DT, filters={"tool": key, "status": ["in", list(C.OPEN_STATUSES)]},
                          fields=QUEUE_FIELDS, order_by="joined_at asc")


def recent_entries(key, user, limit=5):
    return frappe.get_all(C.QUEUE_DT, filters={"tool": key, "user": user,
                                               "status": ["not in", list(C.OPEN_STATUSES)]},
                          fields=QUEUE_FIELDS, order_by="joined_at desc", limit_page_length=limit)


def create_entry(key, user, now):
    doc = frappe.get_doc({"doctype": C.QUEUE_DT, "tool": key, "user": user, "full_name": full_name(user),
                          "status": C.ST_WAITING, "joined_at": now})
    doc.flags.ignore_permissions = True
    doc.insert()
    return doc.name


def update_entry(name, values):
    frappe.db.set_value(C.QUEUE_DT, name, values, update_modified=True)


def bump_opens(name):
    frappe.db.sql("update `tabEC Shared Tool Queue` set opens = ifnull(opens, 0) + 1 where name=%s", (name,))


def entry_of_user_at(key, user, ts):
    """Luot cua user bao trum thoi diem ts (gan file xuat vao dung luot)."""
    rows = frappe.get_all(C.QUEUE_DT, filters={"tool": key, "user": user, "started_at": ["<=", ts]},
                          fields=["name"], order_by="started_at desc", limit_page_length=1)
    return rows[0].name if rows else None


# ------------------------------------------------------------------ nhat ky --
def log(key, event, user=None, entry=None, detail=None, actor=None):
    try:
        doc = frappe.get_doc({"doctype": C.EVENT_DT, "tool": key, "event": event,
                              "event_time": frappe.utils.now_datetime(), "user": user,
                              "actor": actor, "entry": entry,
                              "detail": json.dumps(detail, ensure_ascii=False, default=str) if detail else None})
        doc.flags.ignore_permissions = True
        doc.insert()
    except Exception:
        frappe.log_error(title="shared_tools log")


# -------------------------------------------------------------------- export --
def exports_of(key, user, since, limit=600):
    return frappe.get_all(C.EXPORT_DT, filters={"tool": key, "user": user, "exported_at": [">=", since]},
                          fields=EXPORT_FIELDS, order_by="exported_at desc", limit_page_length=limit)


def entries_since(key, since):
    return frappe.get_all(C.QUEUE_DT, filters={"tool": key, "joined_at": [">=", since]},
                          fields=QUEUE_FIELDS, order_by="joined_at asc", limit_page_length=0)


def exports_since(key, since):
    return frappe.get_all(C.EXPORT_DT, filters={"tool": key, "exported_at": [">=", since]},
                          fields=["name", "user", "rows", "pages", "run_id", "part", "exported_at"],
                          limit_page_length=0)


def export_by_name(name):
    return frappe.db.get_value(C.EXPORT_DT, name, EXPORT_FIELDS + ["tool"], as_dict=True)


def exports_of_run(run_id):
    return frappe.get_all(C.EXPORT_DT, filters={"run_id": run_id}, fields=EXPORT_FIELDS + ["tool"],
                          order_by="part asc", limit_page_length=0)


def export_exists(export_id):
    return bool(frappe.db.exists(C.EXPORT_DT, {"export_id": export_id}))


def save_export(values, content):
    """Luu file rieng tu (is_private) gan vao ban ghi EC Shared Tool Export."""
    doc = frappe.get_doc(dict(values, doctype=C.EXPORT_DT))
    doc.flags.ignore_permissions = True
    doc.insert()
    f = frappe.get_doc({"doctype": "File", "file_name": values["file_name"], "is_private": 1,
                        "attached_to_doctype": C.EXPORT_DT, "attached_to_name": doc.name,
                        "content": content})
    f.flags.ignore_permissions = True
    f.insert()
    frappe.db.set_value(C.EXPORT_DT, doc.name, "file_url", f.file_url, update_modified=False)
    return doc.name


def file_content(file_url):
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        return None
    return frappe.get_doc("File", name).get_content()


def mark_downloaded(name, now):
    frappe.db.set_value(C.EXPORT_DT, name, "downloaded_at", now, update_modified=False)


def old_exports(before):
    return frappe.get_all(C.EXPORT_DT, filters={"exported_at": ["<", before]}, pluck="name")


def delete_export(name):
    for f in frappe.get_all("File", filters={"attached_to_doctype": C.EXPORT_DT, "attached_to_name": name},
                            pluck="name"):
        frappe.delete_doc("File", f, ignore_permissions=True, force=True)
    frappe.delete_doc(C.EXPORT_DT, name, ignore_permissions=True, force=True)


# --------------------------------------------------------------- nguoi dung --
def full_name(user):
    return frappe.db.get_value("User", user, "full_name") or user


def user_meta(users):
    """{user: {full_name, department}} - phong ban lay tu Employee.user_id (co thi hien)."""
    users = [u for u in set(users) if u]
    if not users:
        return {}
    out = {u: {"full_name": u, "department": ""} for u in users}
    for r in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"]):
        out[r.name]["full_name"] = r.full_name or r.name
    if frappe.db.exists("DocType", "Employee"):
        for r in frappe.get_all("Employee", filters={"user_id": ["in", users], "status": "Active"},
                                fields=["user_id", "department"]):
            dep = (r.department or "").rsplit(" - ", 1)[0]
            out[r.user_id]["department"] = dep
    return out


def user_exists(user):
    return bool(frappe.db.exists("User", user))


def roles_of(user):
    return frappe.get_roles(user)


def is_system_user(user):
    return frappe.db.get_value("User", user, "user_type") == "System User"


def notify(user, subject, link):
    """Chuong thong bao Frappe + day realtime de trang dang mo cap nhat ngay. Loi khong lam hong thao tac."""
    try:
        doc = frappe.get_doc({"doctype": "Notification Log", "for_user": user, "type": "Alert",
                              "subject": subject[:140], "email_content": subject, "link": link})
        doc.flags.ignore_permissions = True
        doc.insert()
    except Exception:
        frappe.log_error(title="shared_tools notify")
    try:
        frappe.publish_realtime("ec_shared_tool", {"event": "ready"}, user=user, after_commit=True)
    except Exception:
        pass


def publish_changed(key):
    try:
        frappe.publish_realtime("ec_shared_tool", {"event": "changed", "tool": key}, after_commit=True)
    except Exception:
        pass


# --------------------------------------------------------------------- cache --
def cache_get(k):
    v = frappe.cache().get_value(k)
    return v


def cache_set(k, v, ttl):
    frappe.cache().set_value(k, v, expires_in_sec=ttl)


def try_lock(k, ttl):
    """True neu lay duoc khoa (chua ai giu)."""
    return bool(frappe.cache().set(k, "1", nx=True, ex=ttl))


def commit():
    frappe.db.commit()


def rollback():
    frappe.db.rollback()
