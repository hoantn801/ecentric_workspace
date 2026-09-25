# Copyright (c) 2026, eCentric and contributors
"""p214_brand_weight_management_self: phong Management tu chot phieu ty trong (26/09).

- tao process BRAND_WEIGHT-SELF-V1 (idempotent, qua setup_brand_weight_v1)
- trang thai process moi DI THEO process chinh: V1 dang Active thi SELF cung Active.
  Neu de SELF o Draft sau deploy, 8 nguoi phong Management bam nop se gap loi
  "process khong Active" cho toi khi co nguoi bat tay.
- resync trang /ec-hr/phan-bo-cong-viec (nut "Nop va chot" cho nhom Management)

Loi o day khong duoc lam rollback deploy cua ca site: ghi log, chay tay lai duoc."""
import frappe


def execute():
    try:
        _execute()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="p214_brand_weight_management_self")


def _execute():
    if not frappe.db.exists("EC Approval Type", "BRAND_WEIGHT"):
        return
    from ecentric_workspace.approval_center.features.brand_weight.infrastructure import (
        page_sync, setup,
    )
    frappe.set_user("Administrator")
    log = frappe.logger("approval_center")
    log.info("p214 setup: %s" % setup.setup_brand_weight_v1(apply=1))
    main = frappe.db.get_value("EC Approval Process", setup.PROCESS_CODE, "status")
    if main == "Active":
        frappe.db.set_value("EC Approval Process", setup.SELF_PROCESS_CODE, "status", "Active")
    frappe.db.commit()
    log.info("p214 page: %s" % page_sync.sync())
