# Copyright (c) 2026, eCentric and contributors
"""p216_create_tong_quan_page: tao trang /tong-quan (Tong quan -> the Nhan su) va dong bo lai
/viec-cua-toi.

Vi sao /viec-cua-toi cung phai sync: muc "Tong quan" tren sidebar portal doi route tu
/coming-soon?tool=tong-quan sang /tong-quan (shell/nav.py). Sidebar du phong duoc duc san
trong HTML cua /viec-cua-toi (shell.fallback) -> file doi -> khong sync thi trang van tro
vao trang "sap ra mat" cu ma khong co gi bao loi.

Chot 28/09/2026 (Hoan): Tong quan > chon the Nhan su > 3 tab (bang dieu khien, danh sach,
so do phong ban). Chi HR Manager / HR User / EC CnB / System Manager thay the Nhan su."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.hr.pages.tong_quan import page_sync as tong_quan
    from ecentric_workspace.action_center.pages.my_work import page_sync as my_work
    for label, mod in (("tong-quan", tong_quan), ("viec-cua-toi", my_work)):
        try:
            frappe.logger("approval_center").info("p216 %s: %s" % (label, mod.sync()))
        except Exception:
            # Mot trang loi khong duoc chan migrate cua ca site - chi ghi lai.
            frappe.log_error(title="p216_create_tong_quan_page " + label)
