# Copyright (c) 2026, eCentric and contributors
"""Ghi 4 trang Khao sat tu repo len site (Web Page).

ROUTE /khao-sat DA CO CHU tu 28/07/2026: trang "Khao sat noi bo & Vong quay may man" (MS Form
nhung + vong quay 3 ly tra sua, Server Script spin_wheel / lucky_winners). page_sync_util tim
trang theo route, nen upsert thang se GHI DE trang cu. Truoc khi ghi, trang nao dang giu
route ma KHONG phai cua module nay (khac title) thi duoc DOI ROUTE sang `<route>-cu`, giu
nguyen noi dung + trang thai publish, va ghi Error Log de con dau vet. Khong xoa gi.
"""
import frappe

from ecentric_workspace.approval_center import page_sync_util

PAGE_KEYS = ("hub", "fill", "manage", "builder")


def _relocate_foreign(route, title):
    """Doi route cua trang KHAC dang chiem `route`. Tra ve ten trang da doi (hoac None)."""
    rows = frappe.get_all("Web Page", filters={"route": route}, fields=["name", "title"])
    for r in rows:
        if r.title == title:
            continue
        new_route = route + "-cu"
        frappe.db.set_value("Web Page", r.name, "route", new_route)
        frappe.log_error("Web Page %s (%s) chiem route /%s -> doi sang /%s de nhuong cho module Khao sat"
                         % (r.name, r.title, route, new_route), "surveys page relocate")
        return r.name
    return None


def sync_one(route, name, title, html):
    moved = _relocate_foreign(route, title)
    res = page_sync_util.upsert_web_page(route, name, title, html, publish=1)
    if moved:
        res["relocated"] = moved
    return res


def sync_all():
    import importlib
    out = []
    for key in PAGE_KEYS:
        try:
            mod = importlib.import_module("ecentric_workspace.surveys.pages.%s.page_sync" % key)
            out.append(mod.sync())
        except Exception as exc:
            frappe.log_error(frappe.get_traceback(), "surveys page sync %s" % key)
            out.append({"page": key, "action": "error", "error": str(exc)[:300]})
    return out
