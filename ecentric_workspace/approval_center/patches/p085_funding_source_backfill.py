# Copyright (c) 2026, eCentric and contributors
"""Backfill the generic funding pair on existing Payment Requests.

`EC Payment Request` gains `funding_source_doctype` + `funding_source_name` (Dynamic Link),
which supersede the hardcoded `purchase_request` link. Historical rows only have the old
field, so the new UI and the remaining-balance maths would treat them as "no source" and
under-count what an ĐNMH has already spent.

This copies every non-empty `purchase_request` into the pair. The legacy field is deliberately
KEPT and dual-written by the service layer, so anything still reading it keeps working and a
rollback needs no data repair.

Idempotent: rows that already carry the pair are skipped. Uses db_set-free direct SQL update
so no doc hooks fire on historical records (no notifications, no modified bump storm).
"""
import frappe


def execute():
    if not frappe.db.has_column("EC Payment Request", "funding_source_doctype"):
        # Schema not synced yet (patch ordered before model sync on a partial migrate).
        return
    rows = frappe.get_all(
        "EC Payment Request",
        filters={"purchase_request": ["is", "set"], "funding_source_name": ["in", ["", None]]},
        fields=["name", "purchase_request"], limit_page_length=0)
    if not rows:
        frappe.logger().info("p085: nothing to backfill")
        return
    for row in rows:
        frappe.db.sql(
            """UPDATE `tabEC Payment Request`
               SET funding_source_doctype = %s, funding_source_name = %s
               WHERE name = %s""",
            ("EC Purchase Request", row.purchase_request, row.name))
    frappe.logger().info("p085: backfilled %d Payment Request(s)" % len(rows))
