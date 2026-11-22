# Copyright (c) 2026, eCentric and contributors
"""Chan ghi tay vao the vang / ho so ky luat: moi thay doi phai di qua service (co kiem quyen,
kiem thoi hieu va ghi nhat ky). Repository dat co `ec_ky_luat_service` truoc khi luu. Migrate /
patch / System Manager sua du lieu khan cap van ghi duoc (co flag in_migrate / in_patch hoac
frappe.flags.ec_ky_luat_admin_fix)."""
import frappe
from frappe import _


def require_service_write(doc):
    if doc.flags.get("ec_ky_luat_service") or frappe.flags.in_migrate or frappe.flags.in_patch \
            or frappe.flags.in_install or frappe.flags.get("ec_ky_luat_admin_fix"):
        return
    frappe.throw(_("Thẻ vàng / hồ sơ kỷ luật chỉ được cập nhật qua trang /ky-luat."), frappe.PermissionError)
