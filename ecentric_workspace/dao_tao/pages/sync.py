# Copyright (c) 2026, eCentric and contributors
"""Ghi 7 trang Dao tao + Quiz tu repo len site (Web Page).

Truoc khi ghi, trang nao dang giu route ma KHONG phai cua module nay (khac title) thi duoc DOI
ROUTE sang `<route>-cu` (giu nguyen noi dung + publish) va ghi Error Log - khong xoa gi
(cung cach surveys/pages/sync.py lam voi /khao-sat cu).
"""
import importlib

import frappe

from ecentric_workspace.approval_center import page_sync_util

PAGE_KEYS = ("learn", "lesson", "admin", "quiz", "edit", "play", "host")


def _relocate_foreign(route, title):
    rows = frappe.get_all("Web Page", filters={"route": route}, fields=["name", "title"])
    for r in rows:
        if r.title == title:
            continue
        new_route = route + "-cu"
        frappe.db.set_value("Web Page", r.name, "route", new_route)
        frappe.log_error("Web Page %s (%s) chiem route /%s -> doi sang /%s de nhuong cho module Dao tao"
                         % (r.name, r.title, route, new_route), "dao_tao page relocate")
        return r.name
    return None


def sync_one(route, name, title, html):
    moved = _relocate_foreign(route, title)
    res = page_sync_util.upsert_web_page(route, name, title, html, publish=1)
    if moved:
        res["relocated"] = moved
    return res


def sync_all():
    out = []
    for key in PAGE_KEYS:
        try:
            mod = importlib.import_module("ecentric_workspace.dao_tao.pages.%s.page_sync" % key)
            out.append(mod.sync())
        except Exception as exc:
            frappe.log_error(frappe.get_traceback(), "dao_tao page sync %s" % key)
            out.append({"page": key, "action": "error", "error": str(exc)[:300]})
    return out
