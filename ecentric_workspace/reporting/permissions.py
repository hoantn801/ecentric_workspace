# Copyright (c) 2026, eCentric and contributors
"""Reports Center visibility resolver.

Decides which report CARDS a user sees on the /reports hub. This is UX only:
the destination report page/API (e.g. the ec_pnl_data Server Script) remains
the sole DATA security boundary. `is_report_visible` is pure (no DB) so it is
unit-testable without a bench."""
import frappe

_DEFAULT_ADMIN_ROLES = {"System Manager"}


def _admin_roles():
    override = (frappe.get_conf().get("reporting_admin_roles")
               if hasattr(frappe, "get_conf") else None)
    if isinstance(override, (list, tuple, set)) and override:
        return set(override)
    return set(_DEFAULT_ADMIN_ROLES)


def user_roles(user=None):
    return set(frappe.get_roles(user or frappe.session.user))


def is_internal_system_user(user=None):
    user = user or frappe.session.user
    if not user or user == "Guest":
        return False
    return frappe.db.get_value("User", user, "user_type") == "System User"


def user_departments(user=None):
    user = user or frappe.session.user
    depts = set()
    emp = frappe.db.get_value("Employee", {"user_id": user}, "department")
    if emp:
        depts.add(emp)
    return depts


def is_catalog_admin(user=None):
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return bool(_admin_roles() & user_roles(user))


def build_context(user=None):
    user = user or frappe.session.user
    return {
        "user": user,
        "roles": user_roles(user),
        "departments": user_departments(user),
        "is_admin": is_catalog_admin(user),
    }


def is_report_visible(*, visibility_mode, card_status, allowed_roles,
                      allowed_departments, ctx, include_disabled=False):
    """PURE gate (no DB). ctx = build_context() dict. Fail-closed."""
    if ctx.get("is_admin"):
        return include_disabled if card_status == "Disabled" else True
    if card_status == "Disabled":
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
