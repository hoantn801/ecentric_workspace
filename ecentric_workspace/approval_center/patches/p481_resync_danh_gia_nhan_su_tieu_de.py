# Copyright (c) 2026, eCentric and contributors
"""p481_resync_danh_gia_nhan_su_tieu_de (24/11/2026, Hoan chot 23/11): Danh gia nhan su - C&B sua
TIEU DE (truong moi custom_title, migrate tu them cot) o ban nhap truoc ngay tu gui.

Sync lai 2 trang tu nguon repo (A65):
  /approvals/employee-review   o "Tieu de (tuy chinh)" tren the Nhap (co khoa chong troi:
                               BASELINE moi, ban cu nam trong SUPERSEDES)
  /ec-hr/danh-gia-nhan-su      hang cho C&B them cot Tieu de
Moi trang mot khoi try; KHONG nem loi, KHONG xoa du lieu, KHONG goi ra ngoai, khong gui thong bao."""
import frappe

PAGES = (
    "ecentric_workspace.approval_center.features.employee_review.infrastructure.page_sync",
    "ecentric_workspace.hr.pages.danh_gia_nhan_su.page_sync",
)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    for mod in PAGES:
        try:
            res = frappe.get_module(mod).sync() or {}
            frappe.logger("approval_center").info("p481 %s: %s" % (mod.rsplit(".", 2)[-2], res))
            if isinstance(res, dict) and res.get("action") == "refused":
                frappe.log_error("p481: %s refused (live drift): %s" % (mod, res),
                                 "p481_resync_danh_gia_nhan_su_tieu_de")
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "p481_resync_danh_gia_nhan_su_tieu_de failed: %s" % mod)
