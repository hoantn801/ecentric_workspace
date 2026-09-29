# Copyright (c) 2026, eCentric and contributors
"""Popup "Hom nay o eCentric" - NOI DUY NHAT doc/ghi DB. Khong co quy tac nghiep vu o day.

Ghi chu quyen: cac ham doc chay phia server, loc theo phien nguoi dung o service. Ngay sinh
(Employee.date_of_birth, permlevel 1 tu 12/08) doc bang frappe.get_all (bo qua quyen) nhung
CHI de tinh ngay/thang - domain.birthdays khong tra nam sinh ra ngoai.
"""
import datetime
import re

import frappe

from ecentric_workspace.home_today import constants as C

_STRIP_RE = re.compile(r"<(style|link|script)\b[^>]*>.*?</\1\s*>|<(style|link|script)\b[^>]*/?>", re.I | re.S)


def active_employees():
    return frappe.get_all(
        "Employee", filters={"status": "Active"},
        fields=["name", "employee_name", "user_id", "department", "designation",
                "date_of_birth", "date_of_joining"],
        limit_page_length=0)


def department_names():
    return {r.name: (r.department_name or r.name)
            for r in frappe.get_all("Department", fields=["name", "department_name"], limit_page_length=0)}


def viewer_employee(user):
    rows = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"},
                          fields=["name", "department", "company", "holiday_list"], limit=1)
    return rows[0] if rows else None


def holiday_list_for(viewer):
    """Employee.holiday_list -> Company.default_holiday_list (cua cong ty nguoi xem, khong co
    thi cong ty mac dinh). Khong doan ten list."""
    if viewer and viewer.get("holiday_list"):
        return viewer.get("holiday_list")
    company = (viewer and viewer.get("company")) or frappe.defaults.get_global_default("company")
    if company and frappe.get_meta("Company").has_field("default_holiday_list"):
        return frappe.db.get_value("Company", company, "default_holiday_list")
    return None


def holidays(holiday_list, today, days_ahead):
    if not holiday_list or not frappe.db.exists("DocType", "Holiday"):
        return []
    fields = ["holiday_date", "description"]
    if frappe.get_meta("Holiday").has_field("weekly_off"):
        fields.append("weekly_off")
    return frappe.get_all(
        "Holiday", fields=fields, order_by="holiday_date asc", limit_page_length=0,
        filters={"parent": holiday_list, "parenttype": "Holiday List",
                 "holiday_date": ["between", [today, today + datetime.timedelta(days=days_ahead)]]})


def news_rows(today):
    """Tin noi bo da tich "Dua len popup". DocType/field chua co tren site -> [] (khong 500)."""
    if not frappe.db.exists("DocType", C.NEWS_DT):
        return []
    meta = frappe.get_meta(C.NEWS_DT)
    if not meta.has_field("ec_show_in_popup"):
        return []
    # DocType cua site: chi doc cot CO THAT (thieu mot cot = ca popup chet, xem service._shared)
    fields = ["name"] + [f for f in ("title", "category", "image", "summary", "published_on",
                                     "content", "ec_popup_until") if meta.has_field(f)]
    if "published_on" not in fields:
        return []
    rows = frappe.get_all(
        C.NEWS_DT, fields=fields, order_by="published_on desc", limit=20,
        filters={"published": 1, "ec_show_in_popup": 1})
    for r in rows:
        r["content_html"] = safe_html(r.get("content"))
    return rows


def safe_html(html, limit=20000):
    """HTML tin noi bo -> an toan de gan innerHTML tren trang chu cua MOI nguoi.
    always_sanitize: sanitize_html mac dinh tra NGUYEN chuoi neu no parse duoc thanh JSON hoac
    khong co the. Cat TRUOC khi lam sach (cat sau co the de lai the mo do). Bo <style>/<link>:
    allowlist cua Frappe giu <style> -> mot tin co the doi mau ca trang chu."""
    from frappe.utils.html_utils import sanitize_html
    raw = (html or "")[:limit]
    clean = sanitize_html(raw, always_sanitize=True) or ""
    return _STRIP_RE.sub("", clean)


def policy_rows(today):
    if not frappe.db.exists("DocType", C.POLICY_DT):
        return []
    meta = frappe.get_meta(C.POLICY_DT)
    if not (meta.has_field("effective_date") and meta.has_field("is_active")):
        return []
    fields = ["name"] + [f for f in ("title", "effective_date", "document", "content") if meta.has_field(f)]
    return frappe.get_all(
        C.POLICY_DT, fields=fields,
        filters={"is_active": 1,
                 "effective_date": ["between", [today - datetime.timedelta(days=C.POLICY_DAYS - 1), today]]},
        order_by="effective_date desc", limit=10)


def onboard_rows():
    """Ban moi onboard hom nay - di qua ham cua chat HR (da chan truoc 08:30, kill switch,
    khong co gi ve luong). Khong doc thang DocType cua ho."""
    from ecentric_workspace.approval_center.features.new_staff_preparation.application import welcome
    return (welcome.welcome_today() or {}).get("rows") or []


# ------------------------------------------------------------------ reaction ----
def reactions(targets):
    if not targets:
        return []
    return frappe.get_all(C.REACTION_DT, filters={"target": ["in", list(targets)]},
                          fields=["target", "kind", "user"], limit_page_length=0)


def full_names(users):
    users = [u for u in set(users) if u]
    if not users:
        return {}
    return {r.name: r.full_name or r.name
            for r in frappe.get_all("User", filters={"name": ["in", users]}, fields=["name", "full_name"])}


def find_reaction(target, kind, user):
    return frappe.db.get_value(C.REACTION_DT, {"target": target, "kind": kind, "user": user}, "name")


def add_reaction(target, kind, user, today):
    """dedupe_key UNIQUE o DB: hai lan bam trung nhau (2 tab) -> lan sau nem DuplicateEntryError,
    service coi nhu da bat."""
    frappe.get_doc({"doctype": C.REACTION_DT, "target": target, "kind": kind, "user": user,
                    "reaction_date": today, "dedupe_key": "%s|%s|%s" % (target, kind, user)}
                   ).insert(ignore_permissions=True)


def is_duplicate(exc):
    """Trung dedupe_key (truong unique): Frappe nem UniqueValidationError(doctype, name, e) -
    args[0] la TEN DOCTYPE, loi MySQL goc nam o __cause__ / args[2]."""
    if isinstance(exc, (frappe.DuplicateEntryError, frappe.UniqueValidationError)):
        return True
    for e in (exc, getattr(exc, "__cause__", None)):
        try:
            if e is not None and frappe.db.is_unique_key_violation(e):
                return True
        except Exception:
            pass
    return False


def remove_reaction(name):
    frappe.delete_doc(C.REACTION_DT, name, ignore_permissions=True, force=True)


# ------------------------------------------------------------------ cache -------
def now():
    return frappe.utils.now_datetime()


def cache_get(key):
    return frappe.cache().get_value(key)


def cache_set(key, value, ttl):
    frappe.cache().set_value(key, value, expires_in_sec=ttl)


def log_error(title):
    frappe.log_error(title=title, message=frappe.get_traceback())
