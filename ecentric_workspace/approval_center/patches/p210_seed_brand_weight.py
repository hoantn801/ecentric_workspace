# Copyright (c) 2026, eCentric and contributors
"""p210_seed_brand_weight: EC Approval Type BRAND_WEIGHT + process BRAND_WEIGHT-V1 (Draft).

Idempotent, khong pha: type da ton tai thi giu nguyen moi chinh sua cua admin; process da
ton tai thi setup chi bao [OK]. Process tao o trang thai DRAFT - engine chi chay process
Active, nen sau migrate chua ai nop duoc. Bat that su la mot buoc co y:
activation.enable_brand_weight(apply=1), chay tay sau khi xem dry-run."""
import json
import os

import frappe

DOCTYPE = "EC Approval Type"
CODE = "BRAND_WEIGHT"
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Building",
            "visibility_mode": "All Internal Users", "legacy_source": "ERP",
            "route": "ec-hr/phan-bo-cong-viec"}


def _seed_row():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), encoding="utf-8") as fh:
        return next((r for r in json.load(fh) if r.get("approval_code") == CODE), None)


def execute():
    """Loi o day KHONG duoc chan migrate: seed/setup chay tay lai duoc qua
    setup_brand_weight_v1(apply=1), con mot migrate hong thi rollback ca dot deploy."""
    try:
        _execute()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="p210_seed_brand_weight")


def _execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    log = frappe.logger("approval_center")
    if not frappe.db.exists(DOCTYPE, CODE):
        row = _seed_row()
        if not row:
            log.warning("p210: %s khong co trong seed" % CODE)
            return
        if row.get("category") and not frappe.db.exists("EC Approval Category", row["category"]):
            log.warning("p210: thieu category %s, bo qua" % row["category"])
            return
        doc = frappe.new_doc(DOCTYPE)
        doc.update(DEFAULTS)
        doc.update(row)
        doc.insert(ignore_permissions=True)
    from ecentric_workspace.approval_center.features.brand_weight.infrastructure.setup import (
        setup_brand_weight_v1,
    )
    frappe.set_user("Administrator")
    res = setup_brand_weight_v1(apply=1)
    frappe.db.commit()
    log.info("p210_seed_brand_weight: %s" % res)
