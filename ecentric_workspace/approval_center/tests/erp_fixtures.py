# Copyright (c) 2026, eCentric and contributors
"""Shared, ERPNext/HRMS-compatible test fixtures (R1 correction, 2026-07-12).

Valid on BOTH bare-frappe test sites and real ERPNext/HRMS benches:
  * real ERPNext `Employee` requires `first_name` (not just employee_name);
  * real ERPNext `Company` requires `country`; the HRMS Company override reads
    payroll-account custom fields (optional) - `flags.ignore_mandatory` covers
    optional accounts only, never identity fields;
  * `User.name` is lowercased by frappe - emails are normalized here so
    frappe.set_user(session) always matches stored owner fields;
  * Roles are created when absent (bare sites ship no 'Employee' role).

No dependence on pre-existing site data: every helper creates what it needs and
is idempotent (exists-check first). NOT a test module (no test_ prefix)."""
import frappe


def ensure_role(role):
    if not frappe.db.exists("Role", role):
        frappe.get_doc({"doctype": "Role", "role_name": role}).insert(ignore_permissions=True)
    return role


def make_user(email, roles=("Employee",)):
    email = email.lower()  # frappe lowercases User.name on insert
    for r in roles:
        ensure_role(r)
    if not frappe.db.exists("User", email):
        u = frappe.get_doc({"doctype": "User", "email": email,
                            "first_name": email.split("@")[0], "user_type": "System User",
                            "enabled": 1, "send_welcome_email": 0})
        u.flags.no_welcome_mail = True
        u.insert(ignore_permissions=True)
        u.add_roles(*roles)
    return email


def make_company(company_name, abbr, currency="VND", country="Vietnam"):
    if not frappe.db.exists("Company", company_name):
        d = frappe.get_doc({"doctype": "Company", "company_name": company_name,
                            "abbr": abbr, "default_currency": currency, "country": country})
        d.flags.ignore_mandatory = True  # optional ERPNext/HRMS account fields only
        d.insert(ignore_permissions=True)
    return company_name


def make_department(department_name, company):
    """Returns the ACTUAL Department name (ERPNext autonames 'X - ABBR')."""
    existing = frappe.db.get_value("Department", {"department_name": department_name}, "name")
    if existing:
        return existing
    d = frappe.get_doc({"doctype": "Department", "department_name": department_name,
                        "company": company})
    d.flags.ignore_mandatory = True
    return d.insert(ignore_permissions=True).name


def make_employee(user_id, company, reports_to=None, department=None):
    """ERPNext-valid Employee for a User; first_name is mandatory on real ERPNext."""
    n = frappe.db.get_value("Employee", {"user_id": user_id}, "name")
    if not n:
        d = frappe.get_doc({"doctype": "Employee",
                            "first_name": user_id.split("@")[0],
                            "employee_name": user_id.split("@")[0],
                            "user_id": user_id, "company": company,
                            "department": department, "status": "Active",
                            "gender": "Other", "date_of_joining": "2020-01-01",
                            "date_of_birth": "1990-01-01"})
        d.flags.ignore_mandatory = True
        n = d.insert(ignore_permissions=True).name
    if reports_to:
        frappe.db.set_value("Employee", n, "reports_to", reports_to)
    return n


def ensure_category(code, name):
    if not frappe.db.exists("EC Approval Category", code):
        frappe.get_doc({"doctype": "EC Approval Category", "category_code": code,
                        "category_name": name}).insert(ignore_permissions=True)
    return code
