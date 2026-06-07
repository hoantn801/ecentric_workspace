"""Phase D.1 capacity hardening - composite indexes (idempotent).

  tabEC Marketplace Order Log (brand, order_datetime)  - baseline median scan
  tabEC Alert (brand, status, detected_at)             - /alerts list + cards

Safe to re-run: existing indexes are detected and skipped. Read-only data
operation (DDL only, no rows touched). Rollback = drop_index (data untouched).
"""
import frappe

INDEXES = (
    ("tabEC Marketplace Order Log", ("brand", "order_datetime")),
    ("tabEC Alert", ("brand", "status", "detected_at")),
)


def execute():
    for table, fields in INDEXES:
        index_name = "_".join(fields) + "_index"
        try:
            exists = frappe.db.sql(
                """SHOW INDEX FROM `%s` WHERE Key_name = %%s""" % table, index_name)
            if exists:
                print("p001_capacity_indexes: %s.%s already present - skip" % (table, index_name))
                continue
            frappe.db.add_index(table.replace("tab", "", 1), list(fields), index_name)
            print("p001_capacity_indexes: created %s on %s" % (index_name, table))
        except Exception:
            # Never block migrate over an index - log and continue.
            frappe.log_error(frappe.get_traceback(), "p001_capacity_indexes %s" % table)
