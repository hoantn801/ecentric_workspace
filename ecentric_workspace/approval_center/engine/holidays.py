# Copyright (c) 2026, eCentric and contributors
"""Schema-safe Holiday List resolution (does NOT guess field names; uses meta
checks + fail-closed). Precedence: explicit override -> Employee.holiday_list ->
Company.default_holiday_list."""
import frappe
from frappe import _


def resolve_holiday_list(employee=None, company=None, override=None):
    if override:
        if not frappe.db.exists("Holiday List", override):
            frappe.throw(_("Holiday List override '{0}' does not exist.").format(override))
        return override
    if employee and frappe.get_meta("Employee").has_field("holiday_list"):
        hl = frappe.db.get_value("Employee", employee, "holiday_list")
        if hl:
            return hl
    if company and frappe.get_meta("Company").has_field("default_holiday_list"):
        hl = frappe.db.get_value("Company", company, "default_holiday_list")
        if hl:
            return hl
    return None


def holiday_dates(holiday_list):
    if not holiday_list:
        return set()
    # 'Holiday' child with 'holiday_date' is the standard ERPNext schema; guard anyway.
    if not (frappe.db.exists("DocType", "Holiday")
            and frappe.get_meta("Holiday").has_field("holiday_date")):
        frappe.throw(_("Holiday schema not found; cannot compute business-hours SLA."))
    rows = frappe.get_all("Holiday", filters={"parent": holiday_list, "parenttype": "Holiday List"},
                          fields=["holiday_date"])
    return set(r.holiday_date for r in rows if r.holiday_date)
