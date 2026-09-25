# Copyright (c) 2026, eCentric and contributors
"""p211_create_brand_weight_page: tao Web Page /ec-hr/phan-bo-cong-viec tu repo (chay
mot lan luc migrate). Dung chung page_sync.sync() voi endpoint dong bo tay, nen chi co
MOT cach tao/cap nhat trang."""
import frappe

from ecentric_workspace.approval_center.features.brand_weight.infrastructure import page_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    res = page_sync.sync()
    frappe.logger("approval_center").info("p211_create_brand_weight_page: %s" % (res or {}))
