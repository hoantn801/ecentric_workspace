# Copyright (c) 2026, eCentric and contributors
"""p217_brand_weight_formkit_copy: resync trang /ec-hr/phan-bo-cong-viec (28/09).

- o "+ Them brand..." dung combobox co o tim chung cua ERP (ec_formkit, bat bang
  data-ec-formkit tren #ec-bw-root) thay cho <select> goc cua trinh duyet
- khung "Chep tu thang truoc" luon hien; thang truoc chua co so thi noi ro va khoa nut
- tab Duyet: thanh buoc duyet, ghi chu khi chua ai nop, nut "Chep thang truoc" cho moi
  phieu dang cho minh

Loi o day khong duoc lam rollback deploy cua ca site: ghi log, chay tay lai duoc."""
import frappe


def execute():
    try:
        from ecentric_workspace.approval_center.features.brand_weight.infrastructure import page_sync
        frappe.logger("approval_center").info("p217 page: %s" % page_sync.sync())
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="p217_brand_weight_formkit_copy")
