# Copyright (c) 2026, eCentric and contributors
"""p060_ky_luat_danh_muc_mau (23/11/2026, Dot 3 HR - Ky luat): seed EC Discipline Settings +
danh muc dieu khoan noi quy MAU TAM. Chi tao khi thieu (hr/ky_luat/infrastructure/setup.py).
Moi buoc mot khoi try, KHONG nem loi (migrate gay = rollback ca ban deploy), khong goi ra ngoai."""
import frappe


def execute():
    from ecentric_workspace.hr.ky_luat.infrastructure import setup
    ket = []
    for label, fn in (("settings", setup.seed_settings), ("rules", setup.seed_rules)):
        try:
            ket.append("%s: %s" % (label, fn()))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("%s LOI\n%s" % (label, frappe.get_traceback()))
    frappe.logger("ky_luat").info("p060: %s" % "; ".join(ket))
    if any("LOI" in k for k in ket):
        frappe.log_error(title="p060_ky_luat_danh_muc_mau", message="\n".join(ket))
