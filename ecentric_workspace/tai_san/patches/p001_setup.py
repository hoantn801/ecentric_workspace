# Copyright (c) 2026, eCentric and contributors
"""p001: dung nen Quan ly tai san tren Asset goc cua ERPNext (dot 0, plan 26/11/2026).

KHONG sua DocType goc, KHONG submit Asset nao, KHONG doi gia / nguoi giu cua may nao.
    1. Custom Field ec_* tren Asset + Asset Category - lay tu CHINH fixtures/custom_field.json
       (mot nguon), chi tao field con thieu (fixtures dong bo lai sau patch).
    2. O trang thai van hanh `custom_asset_` (field tao tay tren site 08/2026, khong thuoc app):
       noi them "Pending Check" + "Broken", giu nguyen moi gia tri cu (domain.merge_status_options).
       Site chua co field nay (bench moi) -> bo qua, khong tu tao.
    3. Role "EC Asset Manager" (chua gan ai - PO gan tren /app/user).
    4. Mac dinh theo loai: chi dien vao Asset Category CON TRONG o thoi gian khau hao / mau cau
       hinh; o da co gia tri thi giu (nguoi dung da sua).

Chay lai bao nhieu lan cung duoc. FAIL-SAFE: loi mot buoc -> Error Log, khong chan migrate.
"""
import json
import os

import frappe

from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import domain as D

TITLE = "tai_san p001 setup"


def execute():
    if not frappe.db.exists("DocType", C.ASSET):
        return
    for step in (_custom_fields, _status_options, _roles, _category_defaults):
        try:
            step()
        except Exception:
            frappe.log_error(title="%s: %s" % (TITLE, step.__name__))
    frappe.clear_cache(doctype=C.ASSET)
    frappe.clear_cache(doctype=C.CATEGORY)


def fixture_fields():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "custom_field.json")
    with open(path, encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r.get("module") == C.MODULE]


def _custom_fields():
    for row in fixture_fields():
        if frappe.db.exists("Custom Field", row["name"]):
            continue
        frappe.get_doc(dict(row)).insert(ignore_permissions=True)


def _status_options():
    name = C.OPS_STATUS_CUSTOM_FIELD
    if not frappe.db.exists("Custom Field", name):
        return
    current = frappe.db.get_value("Custom Field", name, "options")
    wanted = D.merge_status_options(current)
    if wanted != current:
        doc = frappe.get_doc("Custom Field", name)
        doc.options = wanted
        doc.save(ignore_permissions=True)


def _roles():
    if not frappe.db.exists("Role", C.ROLE_MANAGER):
        frappe.get_doc({"doctype": "Role", "role_name": C.ROLE_MANAGER,
                        "desk_access": 1}).insert(ignore_permissions=True)


def _category_defaults():
    for row in frappe.get_all(C.CATEGORY, fields=["name", "ec_default_life_months",
                                                  "ec_is_component", "ec_spec_template"]):
        defaults = D.category_defaults(row.name)
        if not defaults:
            continue
        life, component, spec = defaults
        values = {}
        if not row.ec_default_life_months:
            values["ec_default_life_months"] = life
        if not row.ec_spec_template:
            values["ec_spec_template"] = spec
            # Chi bat co linh kien lan dau dien mac dinh: sau do nguoi dung tat thi giu.
            if component and not row.ec_is_component:
                values["ec_is_component"] = 1
        if values:
            frappe.db.set_value(C.CATEGORY, row.name, values)
