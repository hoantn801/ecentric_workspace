# Copyright (c) 2026, eCentric and contributors
"""Ho so nhan su (28/09/2026): dua vao code nhung thu chat Phan quyen & Luong da tao TRUC TIEP
trong DB de nhap file Excel cua HR (HO_SO_NHAN_SU_thiet_ke.md, HO_SO_NHAN_SU_import_2026-09-28.md).

Schema (2 DocType, 8 Custom Field, Property Setter) di theo fixtures. Patch nay lo phan con lai,
la DU LIEU / QUYEN chu khong phai schema:
    1. 2 DocType EC Sub Department / EC Employee Contract - CHI tren bench moi. Fixtures import
       custom_field.json TRUOC doctype.json (sap theo ten file), nen field Table `ec_contracts`
       se tro vao mot DocType chua co. Tao truoc tu chinh fixtures/doctype.json (mot nguon).
    2. 6 Employee Grade (D4).
    3. Custom DocPerm Employee: L1 cho HR Manager / EC CnB, L2 cho HR Manager / HR User / EC CnB.
    4. 2 report "Ho so nhan su", "Hop dong nhan su" (chi HR Manager / HR User / EC CnB mo).
    5. Custom Role cua report chuan "Employee Birthday": chi HR Manager / HR User
       (report query thang DB -> role Employee xem duoc ngay sinh cua moi nguoi).

MOI BUOC CHI TAO KHI CON THIEU - khong sua, khong xoa ban ghi co san. Tren production ca 5 deu da
co tu 28/09, nen chay xong KHONG doi gi; HR sua report / grade tren site van giu nguyen.
Khong co gia tri ca nhan hay so luong nao trong file nay.
"""
import json
import os

import frappe

EMPLOYEE = "Employee"
FIXTURE_DOCTYPES = ("EC Employee Contract", "EC Sub Department")
GRADES = ("BOD", "Trưởng phòng", "Trưởng nhóm", "Nhân viên", "TTS", "CTV")
PERMLEVEL_ROWS = (
    ("HR Manager", 1, ("read", "write")),
    ("EC CnB", 1, ("read", "write")),
    ("HR Manager", 2, ("read", "write", "export")),
    ("HR User", 2, ("read", "write", "export")),
    ("EC CnB", 2, ("read", "write", "export")),
)
HR_ROLES = ("HR Manager", "HR User", "EC CnB")
PROFILE_FIELDS = (
    "name", "employee_number", "employee_name", "status", "employment_type", "department",
    "ec_sub_department", "designation", "grade", "reports_to", "gender", "company_email",
    "date_of_joining", "relieving_date", "ec_laptop", "ec_thang_tang_bhxh", "date_of_birth",
    "cell_number", "personal_email", "passport_number", "date_of_issue", "place_of_issue",
    "permanent_address", "current_address", "ec_bien_so_xe", "bank_name", "bank_ac_no",
    "health_insurance_no", "ec_ma_kcb", "ec_noi_kcb", "ec_allow_coffee", "ec_allow_lunch",
    "ec_allow_computer",
)
CONTRACT_FIELDS = ("loai_hop_dong", "so_hop_dong", "tu_ngay", "den_ngay", "khong_thoi_han")
REPORTS = (
    ("Hồ sơ nhân sự", [[f, EMPLOYEE] for f in PROFILE_FIELDS], "`tabEmployee`.`department` asc"),
    ("Hợp đồng nhân sự",
     [[f, EMPLOYEE] for f in ("name", "employee_name", "department", "status")]
     + [[f, "EC Employee Contract"] for f in CONTRACT_FIELDS],
     "`tabEmployee`.`employee_name` asc"),
)
BIRTHDAY_REPORT = "Employee Birthday"


def execute():
    for step in (_doctypes, _grades, _permlevels, _reports, _birthday_role):
        try:
            step()
        except Exception:
            # Mot buoc hong khong duoc lam gay migrate (migrate gay = rollback CA ban deploy).
            frappe.log_error(title="p002_employee_profile_structures: " + step.__name__)
    frappe.clear_cache(doctype=EMPLOYEE)


def _doctypes():
    path = os.path.join(os.path.dirname(__file__), "..", "..", "fixtures", "doctype.json")
    with open(path, encoding="utf-8") as fh:
        defs = {d["name"]: d for d in json.load(fh)}
    for name in FIXTURE_DOCTYPES:
        if not frappe.db.exists("DocType", name):
            frappe.get_doc(dict(defs[name])).insert(ignore_permissions=True)


def _grades():
    for grade in GRADES:
        if not frappe.db.exists("Employee Grade", grade):
            frappe.get_doc({"doctype": "Employee Grade", "__newname": grade}).insert(
                ignore_permissions=True)


def _permlevels():
    from frappe.permissions import setup_custom_perms

    # Bench moi chua co Custom DocPerm nao cho Employee: chep quyen chuan sang truoc, neu
    # khong them mot dong custom se lam Employee mat HET quyen chuan.
    setup_custom_perms(EMPLOYEE)
    for role, level, ptypes in PERMLEVEL_ROWS:
        if frappe.db.exists("Custom DocPerm", {"parent": EMPLOYEE, "role": role,
                                               "permlevel": level, "if_owner": 0}):
            continue
        row = {"doctype": "Custom DocPerm", "parent": EMPLOYEE, "parenttype": "DocType",
               "parentfield": "permissions", "role": role, "permlevel": level}
        row.update({p: 1 for p in ptypes})
        frappe.get_doc(row).insert(ignore_permissions=True)


def _reports():
    for name, fields, order_by in REPORTS:
        if frappe.db.exists("Report", name):
            continue
        spec = {"filters": [[EMPLOYEE, "status", "=", "Active", False]], "fields": fields,
                "order_by": order_by, "add_totals_row": 0, "page_length": 500,
                "column_widths": {}, "group_by": None}
        frappe.get_doc({
            "doctype": "Report", "report_name": name, "ref_doctype": EMPLOYEE,
            "report_type": "Report Builder", "is_standard": "No", "module": "Setup",
            "json": json.dumps(spec, ensure_ascii=False),
            "roles": [{"role": r} for r in HR_ROLES],
        }).insert(ignore_permissions=True)


def _birthday_role():
    if not frappe.db.exists("Report", BIRTHDAY_REPORT):
        return
    if frappe.db.exists("Custom Role", {"report": BIRTHDAY_REPORT}):
        return
    frappe.get_doc({
        "doctype": "Custom Role", "report": BIRTHDAY_REPORT, "ref_doctype": EMPLOYEE,
        "roles": [{"role": "HR Manager"}, {"role": "HR User"}],
    }).insert(ignore_permissions=True)
