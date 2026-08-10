# Copyright (c) 2026, eCentric and contributors
"""Reports Center catalog API. The /reports hub calls list_reports_catalog to
render the cards the current user is allowed to SEE (UX visibility). DocPerm on
EC Report is System-Manager-only, so this whitelisted read is the only path a
normal user has to the catalog -- and it hands back a card's `route` only when
the card is Active."""
import frappe

from ecentric_workspace.reporting import permissions as perms


def _child_map(child_doctype, value_field):
    """parent name -> [value, ...] for a child table."""
    out = {}
    for row in frappe.get_all(child_doctype, fields=["parent", value_field]):
        out.setdefault(row["parent"], []).append(row[value_field])
    return out


@frappe.whitelist()
def list_reports_catalog(include_disabled_admin=0):
    user = frappe.session.user
    if not perms.is_internal_system_user(user):
        return {"is_admin": False, "reports": []}

    ctx = perms.build_context(user)
    include_disabled = bool(int(include_disabled_admin or 0)) and ctx["is_admin"]

    rows = frappe.get_all(
        "EC Report",
        fields=["name", "report_title", "category", "card_status", "route",
                "icon", "description", "visibility_mode", "sort_order"],
        order_by="sort_order asc, report_title asc",
    )
    roles_map = _child_map("EC Report Role", "role")
    depts_map = _child_map("EC Report Department", "department")

    cards = []
    for r in rows:
        if not perms.is_report_visible(
            visibility_mode=r.visibility_mode, card_status=r.card_status,
            allowed_roles=roles_map.get(r.name, []),
            allowed_departments=depts_map.get(r.name, []),
            ctx=ctx, include_disabled=include_disabled,
        ):
            continue
        cards.append({
            "code": r.name,
            "title": r.report_title,
            "category": r.category or "Khác",
            "status": r.card_status,
            # a route is only exposed for an Active card (never a dead link)
            "route": (r.route or "") if r.card_status == "Active" else "",
            "icon": r.icon or "chart",
            "description": r.description or "",
        })
    return {"is_admin": ctx["is_admin"], "reports": cards}
