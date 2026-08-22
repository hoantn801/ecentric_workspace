"""Brand consolidation (2026-07-28).

Native `Brand` becomes the single brand master; the custom `Brand Approver`
doctype is retired. The per-brand people/config now live on Brand as
Custom Fields `ec_*`, and the 11 contracted Brand records were renamed so
`Brand.name` is the brand code (VTD-VN, FCV-VN, ...) - the same key every
Link field, GBS document and Server Script already used.

This patch only fixes the leftover the Link fields cannot fix themselves:
the ToDo rows created by alerts.services.case_todo, which stored
reference_type = "Brand Approver".

Deliberately NOT done here: dropping the now-unused Custom Field
"Brand Approver-kam_owner". Deleting it would drop the column, and a
rollback to the previous code (which still selects Brand Approver.kam_owner)
would then fail on a missing column and lose the stored values. The field is
harmless where it is; it disappears with the doctype when Brand Approver is
finally deleted, after GD2/GD4 acceptance.

Idempotent: safe to re-run.
"""

import frappe


def execute():
    # repoint Alert Center setup ToDos onto native Brand
    frappe.db.sql(
        """update `tabToDo` set reference_type = 'Brand'
           where reference_type = 'Brand Approver'"""
    )
    frappe.db.commit()
