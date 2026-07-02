# Copyright (c) 2026, eCentric and contributors
"""Approval Center - controlled read API for the catalog page (B2a).

Exposes ONLY `list_catalog` (whitelisted). Normal users never get raw DocType
access (DocPerm is System Manager only); visibility is enforced here via
`approval_center.permissions`. Returns just what the page needs.
"""
import frappe
from frappe.utils import getdate, nowdate

from ecentric_workspace.approval_center import permissions as perms

CATEGORY_FIELDS = ["name", "category_name", "icon", "sort_order", "is_active"]
TYPE_FIELDS = ["name", "approval_title", "description", "icon", "category",
               "card_status", "process_status", "route", "sort_order",
               "visibility_mode", "available_from"]


def _child_map(child_doctype, value_field):
    """parent -> [values] for a child table of EC Approval Type."""
    out = {}
    rows = frappe.get_all(child_doctype,
                          filters={"parenttype": "EC Approval Type"},
                          fields=["parent", value_field])
    for r in rows:
        out.setdefault(r.parent, []).append(r.get(value_field))
    return out


def _shape(t, cat):
    route = t.route if (t.card_status == "Active" and t.route) else None
    return {
        "approval_code": t.name,
        "approval_title": t.approval_title,
        "description": t.description,
        "icon": t.icon,
        "category_code": t.category,
        "category_name": cat.category_name if cat else None,
        "category_icon": cat.icon if cat else None,
        "card_status": t.card_status,
        "process_status": t.process_status,
        "route": route,
        "sort_order": t.sort_order or 0,
        "category_sort_order": (cat.sort_order or 0) if cat else 0,
    }


@frappe.whitelist()
def list_catalog(include_disabled_admin=0):
    """Return {is_admin, categories, types} visible to the current user."""
    user = frappe.session.user
    if not perms.is_internal_system_user(user):
        return {"is_admin": False, "categories": [], "types": []}

    ctx = perms.build_context(user)
    include_disabled = bool(ctx["is_admin"]) and bool(int(include_disabled_admin or 0))
    today = getdate(nowdate())

    cats = {c.name: c for c in frappe.get_all("EC Approval Category", fields=CATEGORY_FIELDS)}
    types = frappe.get_all("EC Approval Type", fields=TYPE_FIELDS)
    roles_map = _child_map("EC Approval Type Role", "role")
    depts_map = _child_map("EC Approval Type Department", "department")

    cards = []
    for t in types:
        cat = cats.get(t.category)
        visible = perms.is_type_visible(
            visibility_mode=t.visibility_mode,
            card_status=t.card_status,
            allowed_roles=roles_map.get(t.name, []),
            allowed_departments=depts_map.get(t.name, []),
            available_from=getdate(t.available_from) if t.available_from else None,
            category_is_active=bool(cat.is_active) if cat else False,
            ctx=ctx,
            include_disabled=include_disabled,
            today=today,
        )
        if visible:
            cards.append(_shape(t, cat))

    cards.sort(key=lambda c: (c["category_sort_order"], c["sort_order"],
                              (c["approval_title"] or "")))

    seen = {}
    for c in cards:
        code = c["category_code"]
        if code and code not in seen:
            cat = cats.get(code)
            seen[code] = {
                "category_code": code,
                "category_name": c["category_name"],
                "icon": c["category_icon"],
                "sort_order": (cat.sort_order or 0) if cat else 0,
            }
    categories = sorted(seen.values(), key=lambda x: (x["sort_order"], x["category_code"]))

    return {"is_admin": bool(ctx["is_admin"]), "categories": categories, "types": cards}
