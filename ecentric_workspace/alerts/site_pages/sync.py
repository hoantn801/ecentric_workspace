# Copyright (c) 2026, eCentric and contributors
"""Ghi 5 trang Alert Center tu repo len site (xem __init__.py cua goi nay)."""
import frappe
from frappe import _

from ecentric_workspace.alerts.site_pages import PAGE_MODULES
from ecentric_workspace.approval_center import page_sync_util
from ecentric_workspace.legacy_pages import serving


def sync_one(route, name, title, html, accepted, force=0):
    """Ghi MOT trang, co khoa chong troi. Tra ve dict cua upsert_web_page (+ static serving,
    + sha live ghi lai). Live dang giu ban khong nam trong `accepted` -> {"action": "refused"},
    khong ghi gi."""
    res = page_sync_util.upsert_web_page(
        route, name, title, html,
        publish="preserve",
        expect_sha=None if force else tuple(accepted),
    )
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        # HTML thuan, khong token Jinja -> phuc vu tinh (dynamic_template=0) nhu hom nay.
        res.update(serving.ensure_static_serving(res["name"], html))
        # Ghi lai sha SAU khi may chu xu ly, de lan sync sau nhan ra chinh ban ghi cua minh.
        res["recorded_sha"] = page_sync_util.record_live_sha(route, res["name"])
    return res


def _module(key):
    import importlib
    return importlib.import_module("ecentric_workspace.alerts.site_pages.%s.page_sync" % key)


def sync_all(force=0):
    """Dong bo ca 5 trang. Mot trang loi KHONG chan trang khac."""
    out = []
    for key in PAGE_MODULES:
        try:
            out.append(_module(key).sync(force=force))
        except Exception as exc:
            frappe.log_error(frappe.get_traceback(), "alert site_pages sync %s" % key)
            out.append({"page": key, "action": "error", "error": str(exc)[:300]})
    return out


@frappe.whitelist(methods=["POST"])
def sync_alert_center_pages_from_repo():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync Alert Center pages."), frappe.PermissionError)
    return sync_all()
