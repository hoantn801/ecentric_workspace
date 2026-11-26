# Copyright (c) 2026, eCentric and contributors
"""ec_asset_monthly - ghi qua tai_san (service / repository), khong co logic o controller."""
import frappe
from frappe.model.document import Document


class ECAssetMonthly(Document):
    pass


def on_doctype_update():
    # Mot may chi mot dong moi thang: job cron va chay tay cung luc khong chen trung.
    frappe.db.add_unique("EC Asset Monthly", ["month", "asset"], constraint_name="unique_month_asset")
