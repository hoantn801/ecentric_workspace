# Copyright (c) 2026, eCentric and contributors
"""Don mot lan cac dong duyet kieu Role con Pending tren phieu dang mo (25/09/2026).

Tu ban nay tro di, luat moi chay tu dong (xem shared/workflow/role_pool.py):
  * dung luong: nguoi co ghe dich danh o cap sau khong vao nhom Role o cap truoc;
  * go role: hook User.on_update don dong cua nguoi do.
Nhung phieu DA NOP truoc ban nay van mang dong cu. Doc live 25/09 thay 4 dong:
    EC-CTR-2026-00004 L2  phuong.nguyen1  co ghe HOF o cap 3
    EC-CTR-2026-00011 L2  phuong.nguyen1  co ghe HOF o cap 3
    EC-CTR-2026-00017 L2  phuong.nguyen1  co ghe HOF o cap 3
    EC-CTR-2026-00017 L2  fabric.bot      da mat role EC Finance
Patch goi dung ham ma hook dung - khong co luat rieng. Khong dung dong Approved/Rejected;
EC-CTR-2026-00023 va 00026 Hoan chot DE NGUYEN (cap Finance da dong).
Khong bao gio nem loi (chay trong migrate).
"""
import frappe


def execute():
    try:
        from ecentric_workspace.approval_center.shared.workflow import role_pool
        kq = role_pool.tidy_open_rows(actor="hoan.tran@ecentric.vn")
        frappe.db.commit()
        msg = "\n".join("%s L%s %s: %s -> %s" % r for r in kq) or "khong co dong nao can don"
    except Exception:
        frappe.db.rollback()
        msg = "LOI:\n" + frappe.get_traceback()
    frappe.log_error(title="p209 don dong duyet theo role", message=msg)
