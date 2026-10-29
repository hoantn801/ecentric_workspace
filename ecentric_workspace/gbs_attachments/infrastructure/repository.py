# Copyright (c) 2026, eCentric and contributors
"""Doc / ghi phieu GBS phia EC. Noi duy nhat cua module goi frappe.db."""

import json

import frappe

FIELDS = ["name", "status", "gbs_doc_name", "attachment_url", "resubmit_count",
          "attachments_pushed_count"]
#: order_type chi co o GBS Sales Order (quyet dinh co tu "Submit for Approval" hay khong).
EXTRA = {"GBS Sales Order": ["order_type"]}


def load(doctype, name):
    row = frappe.db.get_value(doctype, name, FIELDS + EXTRA.get(doctype, []), as_dict=True)
    return dict(row) if row else None


def local_copy_names(doctype, name):
    """Ten cac file da gan vao phieu tren site EC (ban sao doi chieu)."""
    rows = frappe.get_all("File", filters={"attached_to_doctype": doctype, "attached_to_name": name},
                          fields=["file_name"], limit_page_length=500)
    return {r.file_name for r in rows if r.file_name}


def save_local_copy(doctype, name, filename, data):
    """Ban sao PRIVATE tren team.ecentric.vn - doi chieu doc lap voi SharePoint."""
    frappe.get_doc({
        "doctype": "File", "file_name": filename, "content": data, "is_private": 1,
        "attached_to_doctype": doctype, "attached_to_name": name, "folder": "Home/Attachments",
    }).insert(ignore_permissions=True)


def local_file_bytes(file_url):
    fname = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not fname:
        raise ValueError("khong thay File " + file_url)
    doc = frappe.get_doc("File", fname)
    return doc.file_name or file_url.rsplit("/", 1)[-1], doc.get_content()


def save_result(doctype, name, fields, event):
    """Ghi ket qua + 1 dong approval_history (audit). Khong doi `modified`
    de khong kich lai hook After Save."""
    raw = frappe.db.get_value(doctype, name, "approval_history") or "[]"
    try:
        hist = json.loads(raw)
    except Exception:
        hist = []
    if not isinstance(hist, list):
        hist = []
    hist.append(event)
    values = dict(fields)
    values["approval_history"] = json.dumps(hist, ensure_ascii=False)
    frappe.db.set_value(doctype, name, values, update_modified=False)
