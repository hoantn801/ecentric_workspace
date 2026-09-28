"""Stable compatibility API cho New Staff Preparation (28/09/2026)."""
import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.features.new_staff_preparation.application import (
    service, welcome)

globals().update(bind("NEW_STAFF_PREPARATION"))


@frappe.whitelist(methods=["POST"])
def update_welcome(name, welcome_intro=None, onboard_date=None):
    service.update_welcome(name, welcome_intro=welcome_intro, onboard_date=onboard_date)
    return {"ok": True, "detail": get_detail(name)}   # noqa: F821 - tu bind()


@frappe.whitelist()
def welcome_today():
    """Popup chao mung tren trang chu (tu 08:30 ngay onboard). Moi nguoi da dang nhap."""
    return welcome.welcome_today()
