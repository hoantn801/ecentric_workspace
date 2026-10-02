# Copyright (c) 2026, eCentric and contributors
"""Doc nhan su / to chuc / tep / gui thong bao cho module Khao sat (xem repository.py)."""
import frappe

from ecentric_workspace.surveys import constants as C


# --------------------------------------------------------------- nhan su / to chuc --

def employees():
    return [dict(r) for r in frappe.get_all(
        C.EMPLOYEE, filters={"user_id": ["is", "set"]},
        fields=["user_id", "employee_name", "department", "status"], limit_page_length=20000)]


def departments():
    return [dict(r) for r in frappe.get_all(
        C.DEPARTMENT, filters={"disabled": 0},
        fields=["name", "department_name", "parent_department", "is_group"],
        order_by="lft asc", limit_page_length=5000)]


def user_names(users):
    users = [u for u in set(users or []) if u]
    if not users:
        return {}
    rows = frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"],
                          limit_page_length=len(users))
    return {r.name: (r.full_name or r.name) for r in rows}


def user_exists(user):
    return bool(user) and bool(frappe.db.exists("User", {"name": user, "enabled": 1}))


# ------------------------------------------------------------------------------ tep --

def file_by_url(url):
    rows = frappe.get_all("File", filters={"file_url": url},
                          fields=["name", "owner", "is_private", "file_name",
                                  "attached_to_doctype", "attached_to_name"], limit_page_length=1)
    return dict(rows[0]) if rows else None


def attach_file(file_name, doctype, docname):
    frappe.db.set_value("File", file_name, {"attached_to_doctype": doctype,
                                            "attached_to_name": docname})


def file_content(file_name):
    doc = frappe.get_doc("File", file_name)
    return doc.get_content(), doc.file_name


# --------------------------------------------------------------------- thong bao / job --

def notify(user, title, message, url, survey, dedupe_key, teams=False):
    """teams=True -> event type co ban Teams (DM rieng qua Power Automate, khong rut lai duoc).
    Chi nut "Nhac nguoi chua lam" dung - xem publish_service.run_notify."""
    from ecentric_workspace.notification_center.events import publish_notification_event
    event = C.NOTIFY_EVENT_TEAMS if teams else C.NOTIFY_EVENT
    return publish_notification_event(event, user, title, message, action_url=url,
                                      reference_doctype=C.SURVEY, reference_name=survey,
                                      dedupe_key=dedupe_key)


def enqueue(method, **kwargs):
    frappe.enqueue(method, queue="short", enqueue_after_commit=True, **kwargs)


def log_error(title):
    frappe.log_error(frappe.get_traceback(), title)


def publish_realtime(user, event, payload):
    frappe.publish_realtime(event, payload, user=user, after_commit=True)


def commit():
    frappe.db.commit()      # job moi phut: chot tung khao sat, loi o khao sat sau khong keo lui


def rollback():
    frappe.db.rollback()


def site_flag(key):
    try:
        return bool(int(frappe.conf.get(key) or 0))
    except (TypeError, ValueError):
        return False


def cache_get(key):
    return frappe.cache().get_value(key)


def cache_set(key, value, ttl):
    frappe.cache().set_value(key, value, expires_in_sec=ttl)


def cache_delete(key):
    frappe.cache().delete_value(key)
