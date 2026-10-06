# Copyright (c) 2026, eCentric and contributors
"""p265_brand_weight_nop_thay: resync trang /ec-hr/phan-bo-cong-viec (06/10).

ec-bw-proxy-v1 (Hoan): tab Duyet - bam nguoi chua nop thi lead (nguoi duyet buoc dau cua
phieu do) dien va nop thay; lead cung la truong phong thi chot luon.

Loi o day khong duoc lam rollback deploy cua ca site: ghi log, chay tay lai duoc."""
import frappe


def execute():
    try:
        from ecentric_workspace.approval_center.features.brand_weight.infrastructure import page_sync
        frappe.logger("approval_center").info("p265 page: %s" % page_sync.sync())
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="p265_brand_weight_nop_thay")
