# Copyright (c) 2026, eCentric and contributors
"""Doc tu meta cua Frappe: nguoi xem hien tai doc duoc NHUNG FIELD NAO cua mot DocType.

Cung mot luat voi `Document.apply_fieldlevel_read_permissions` (frappe v16): permlevel doc
duoc = cac dong quyen (DocPerm / Custom DocPerm - meta da gop san) co role cua nguoi xem va
co `read`; cot cua bang con xet theo permlevel cua CHA. Them: field bi mask voi nguoi xem
cung coi nhu khong doc duoc - diff trong Version la gia tri THAT, khong qua mask.
"""
import frappe
from frappe.model import table_fields


def needs_filter(doctype):
    """False khi DocType khong co field nao permlevel > 0 va khong field nao bi mask:
    luc do moi nguoi doc duoc form thi doc duoc het, khong can loc."""
    meta = frappe.get_meta(doctype)
    if any(df.permlevel for df in _all_fields(meta)):
        return True
    return bool(meta.get_masked_fields())


def readable_fields(doctype):
    """(set field cha doc duoc, {field_bang: set cot doc duoc})."""
    meta = frappe.get_meta(doctype)
    roles = set(frappe.get_roles())
    levels = {p.permlevel for p in meta.permissions if p.role in roles and p.get("read")}
    masked = {df.fieldname for df in meta.get_masked_fields() or []}
    readable = {df.fieldname for df in meta.fields
                if df.permlevel in levels and df.fieldname not in masked}
    children = {}
    for df in meta.fields:
        if df.fieldtype in table_fields and df.fieldname in readable and df.options:
            child = frappe.get_meta(df.options)
            children[df.fieldname] = {c.fieldname for c in child.fields if c.permlevel in levels}
    return readable, children


def _all_fields(meta):
    fields = list(meta.fields)
    for df in meta.fields:
        if df.fieldtype in table_fields and df.options:
            fields += frappe.get_meta(df.options).fields or []
    return fields
