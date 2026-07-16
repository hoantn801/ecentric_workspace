# Copyright (c) 2026, eCentric and contributors
"""ERP Shell v1 -- boot endpoint (read-only, UX only).

Returns the navigation registry + minimal session-user display info for pages
that opted in via the `data-ec-shell="1"` marker.

Kill switch (site_config): `ec_shell_disabled: 1` -> {"enabled": false}.
Default (key absent/falsy) = enabled. The check FAILS CLOSED for the shell
only: any error here (or any non-2xx/network failure client-side) leaves the
underlying page fully usable with its static fallback nav; Notification
Center, Approval logic and all backend permissions are unaffected.

Security posture:
- GET, whitelisted, session-authenticated; Guest rejected.
- Read-only; no ignore_permissions anywhere; no business records returned.
- Nav visibility is UX assistance ONLY -- direct URL access continues to be
  protected by existing backend/page authorization (unchanged in Phase 1B).
"""
import frappe

from ecentric_workspace.shell import nav as shell_nav


def _is_internal_user(user):
    if not user or user == "Guest":
        return False
    return frappe.db.get_value("User", user, "user_type") == "System User"


@frappe.whitelist(methods=["GET"])
def get_shell_boot():
    user = frappe.session.user
    if not user or user == "Guest":
        frappe.throw(frappe._("Not permitted"), frappe.PermissionError)

    if frappe.conf.get("ec_shell_disabled"):
        return {"enabled": False, "reason": "kill_switch"}

    if not _is_internal_user(user):
        # Website Users keep their current experience untouched (fail closed).
        return {"enabled": False, "reason": "not_internal"}

    items = shell_nav.compose()
    # v1: every validated item is visible_when == "internal"; the compose()
    # validator guarantees it, so no per-item capability evaluation yet.
    nav = [
        {
            "key": it["key"],
            "label": it["label"],
            "route": it["route"],
            "icon": it["icon"],
            "group": it["group"],
            "active_patterns": it["active_patterns"],
            "keywords": it.get("keywords", []),
            "children": [
                {
                    "key": ch["key"], "label": ch["label"], "route": ch["route"],
                    "icon": ch["icon"], "active_patterns": ch["active_patterns"],
                    "keywords": ch.get("keywords", []),
                }
                for ch in it.get("children", [])
            ],
        }
        for it in items
    ]

    info = frappe.db.get_value(
        "User", user, ["full_name", "user_image"], as_dict=True
    ) or {}
    return {
        "enabled": True,
        "nav": nav,
        "user": {
            "name": user,
            "full_name": info.get("full_name") or user,
            "image": info.get("user_image") or "",
        },
    }
