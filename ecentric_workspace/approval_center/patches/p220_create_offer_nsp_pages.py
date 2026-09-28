# Copyright (c) 2026, eCentric and contributors
"""Tao trang /approvals/offer-request + /approvals/new-staff-preparation va resync trang
/approvals/hiring-request (them tab "Tôi xử lý" + the "HR tuyển dụng" / nut "Tạo Offer") -
28/09/2026. Moi trang mot khoi try rieng, ket qua ghi Error Log. Khong nem loi."""
import frappe

PAGES = (
    "ecentric_workspace.approval_center.features.offer_request.infrastructure.page_sync",
    "ecentric_workspace.approval_center.features.new_staff_preparation.infrastructure.page_sync",
    "ecentric_workspace.approval_center.features.hiring_request.infrastructure.page_sync",
)


def execute():
    ket = []
    for path in PAGES:
        try:
            mod = frappe.get_module(path)
            res = mod.sync() or {}
            ket.append("%s: %s" % (path.split(".")[-3], res.get("action")))
        except Exception:
            ket.append("%s: LOI\n%s" % (path.split(".")[-3], frappe.get_traceback()))
    frappe.log_error(title="p220 offer/nsp/hiring pages", message="\n".join(ket))
