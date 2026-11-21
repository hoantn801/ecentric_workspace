# Copyright (c) 2026, eCentric and contributors
"""Trang thai ben vung (Default Value toan cuc) + nguoi nhan. Noi duy nhat cham frappe.db/defaults."""

import frappe

from ecentric_workspace.gbs_monitor import constants as C


def load():
    g = frappe.defaults.get_global_default
    return {"ip": g(C.KEY_IP) or C.KNOWN_IP, "status": g(C.KEY_STATUS) or "", "checked": g(C.KEY_CHECKED) or ""}


def save(ip, status, now):
    s = frappe.defaults.set_global_default
    if ip:
        s(C.KEY_IP, ip)
    s(C.KEY_STATUS, status)
    s(C.KEY_CHECKED, now)


def recipients():
    conf = frappe.conf.get(C.CONF_RECIPIENTS) or []
    if isinstance(conf, str):
        conf = [x.strip() for x in conf.split(",")]
    users = [u for u in conf if u]
    if users:
        return users
    rows = frappe.db.sql(
        """SELECT DISTINCT u.name FROM `tabUser` u JOIN `tabHas Role` r ON r.parent = u.name
           WHERE r.role = %s AND u.enabled = 1 AND u.user_type = 'System User'
             AND u.name NOT IN ('Administrator', 'Guest')""", (C.FALLBACK_ROLE,))
    return [r[0] for r in rows]


def disabled():
    return bool(frappe.conf.get(C.CONF_DISABLED))
