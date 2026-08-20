# Copyright (c) 2026, eCentric and contributors
"""Remove duplicate File rows on Approval Center requests (same doc + same file_url).

Cause (fixed at source in command_service.claim_uploaded_files): the forms upload through
/api/method/upload_file without a `fieldname`, so the File row is stored with
attached_to_field empty; Frappe's attach_files_to_document hook then fails to recognise it
and inserts a SECOND row for the Attach field. Every existing request therefore carries two
File rows per upload, both pointing at the SAME physical file.

This patch cleans the historical rows. Per (doctype, name, file_url) group it keeps ONE row,
preferring the one that carries attached_to_field (that is the row Frappe's hook maintains),
otherwise the earliest.

Safety: rows are removed with frappe.db.delete, which does NOT run File.on_trash, so the
physical file on disk is never touched -- and a surviving row keeps referencing it anyway.
Scoped to EC* business doctypes of the Approval Center. Idempotent.
"""
import frappe


def execute():
    rows = frappe.get_all(
        "File",
        filters={"attached_to_doctype": ["like", "EC %"], "file_url": ["!=", ""]},
        fields=["name", "attached_to_doctype", "attached_to_name", "attached_to_field",
                "file_url", "creation"],
        order_by="creation asc")
    groups = {}
    for r in rows:
        key = (r["attached_to_doctype"], r["attached_to_name"], r["file_url"])
        groups.setdefault(key, []).append(r)

    removed = 0
    for key, items in groups.items():
        if len(items) < 2:
            continue
        keep = next((i for i in items if (i.get("attached_to_field") or "").strip()), items[0])
        for i in items:
            if i["name"] == keep["name"]:
                continue
            frappe.db.delete("File", {"name": i["name"]})
            removed += 1

    if removed:
        frappe.db.commit()
    frappe.logger("approval_center").info(
        "p055 removed %d duplicate File row(s) across %d group(s)" % (removed, len(groups)))
