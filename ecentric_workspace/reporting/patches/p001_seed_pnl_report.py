# Copyright (c) 2026, eCentric and contributors
"""Seed the first Reports Center card: PnL dashboard, visible only to the
Management - EC department (mirrors the ec_pnl_data Server Script gate).
Idempotent get-or-create -- never overwrites an existing / admin-edited row."""
import frappe

DOCTYPE = "EC Report"
CODE = "PNL_DASHBOARD"


def execute():
    if not frappe.db.exists("DocType", DOCTYPE):
        return
    if frappe.db.exists(DOCTYPE, CODE):
        return
    doc = frappe.new_doc(DOCTYPE)
    doc.update({
        "report_code": CODE,
        "report_title": "Doanh thu eCentric (PnL)",
        "category": "Doanh thu",
        "sort_order": 10,
        "card_status": "Active",
        "route": "/pnl-dashboard",
        "icon": "wallet",
        "description": "Doanh thu & lợi nhuận eCentric. Chỉ Ban Giám đốc (Management - EC).",
        "visibility_mode": "Restricted Departments",
        "allowed_departments": [{"department": "Management - EC"}],
    })
    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    print("[reports-center] seeded EC Report %s -> /pnl-dashboard (Management - EC)" % CODE)
