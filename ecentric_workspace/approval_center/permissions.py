# Copyright (c) 2026, eCentric and contributors
"""Approval Center - service-layer visibility resolver (B2a).

Backend is the ONLY visibility boundary (frontend filters are never trusted).
The catalog DocTypes ship DocPerm = System Manager only, so ordinary users
never touch them directly; all read access flows through
`ecentric_workspace.approval_center.api.catalog` which calls into this module.

No hardcoded users/emails. Fail-closed: anything unresolved => no card.
"""
import frappe

_DEFAULT_ADMIN_ROLES = {"System Manager"}


def _admin_roles():
    cfg = frappe.get_conf().get("approval_center_admin_roles")
    if isinstance(cfg, (list, tuple)) and cfg:
        return set(cfg)
    return set(_DEFAULT_ADMIN_ROLES)


def is_catalog_admin(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(_admin_roles() & set(frappe.get_roles(user)))


def is_internal_system_user(user=None):
    """Enabled, authenticated System User (NOT Guest, NOT Website User)."""
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    row = frappe.db.get_value("User", user, ["user_type", "enabled"], as_dict=True)
    if not row:
        return False
    return row.user_type == "System User" and bool(row.enabled)


def user_roles(user=None):
    return set(frappe.get_roles(user or frappe.session.user))


def user_departments(user=None):
    """Departments the user is validly scoped to, via existing ERP conventions:
      * standard ERPNext Employee.user_id -> Employee.department
      * plus, IF the eCentric `Employee Department Membership` DocType exists,
        its Department links for that user/employee (schema-introspected so we
        never hardcode field names). Any lookup error fails CLOSED (no widen).
    """
    user = user or frappe.session.user
    depts = set()
    employees = frappe.get_all("Employee", filters={"user_id": user},
                               fields=["name", "department"])
    for e in employees:
        if e.department:
            depts.add(e.department)

    dt = "Employee Department Membership"
    if employees and frappe.db.exists("DocType", dt):
        try:
            meta = frappe.get_meta(dt)
            dep_f = next((f.fieldname for f in meta.fields
                          if f.fieldtype == "Link" and f.options == "Department"), None)
            emp_f = next((f.fieldname for f in meta.fields
                          if f.fieldtype == "Link" and f.options == "Employee"), None)
            usr_f = next((f.fieldname for f in meta.fields
                          if f.fieldtype == "Link" and f.options == "User"), None)
            if dep_f and emp_f:
                for e in employees:
                    for r in frappe.get_all(dt, filters={emp_f: e.name}, fields=[dep_f]):
                        if r.get(dep_f):
                            depts.add(r.get(dep_f))
            elif dep_f and usr_f:
                for r in frappe.get_all(dt, filters={usr_f: user}, fields=[dep_f]):
                    if r.get(dep_f):
                        depts.add(r.get(dep_f))
        except Exception:
            pass
    return depts


def build_context(user=None):
    user = user or frappe.session.user
    return {
        "user": user,
        "roles": user_roles(user),
        "departments": user_departments(user),
        "is_admin": is_catalog_admin(user),
    }


def is_type_visible(*, visibility_mode, card_status, allowed_roles, allowed_departments,
                    available_from, category_is_active, ctx, include_disabled=False,
                    today=None):
    """PURE decision function (no DB access) so it is exhaustively unit-testable."""
    is_admin = bool(ctx.get("is_admin"))

    if is_admin:
        if card_status == "Disabled":
            return bool(include_disabled)
        return True

    if card_status == "Disabled":
        return False
    if not category_is_active:
        return False
    if available_from and today is not None and available_from > today:
        return False

    if visibility_mode == "All Internal Users":
        return True
    if visibility_mode == "Admin Only":
        return False
    if visibility_mode == "Restricted Roles":
        roles = set(allowed_roles or [])
        return bool(roles) and bool(roles & set(ctx.get("roles") or []))
    if visibility_mode == "Restricted Departments":
        depts = set(allowed_departments or [])
        return bool(depts) and bool(depts & set(ctx.get("departments") or []))
    return False
