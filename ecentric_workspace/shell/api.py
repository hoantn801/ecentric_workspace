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

    # v2 (nav contexts): serialize EVERY context; the client resolves its
    # context from location.pathname with the same canonical logic as the
    # server-side fallback (shell_nav.resolve_context port). The legacy `nav`
    # key stays = DEFAULT context so pre-context cached JS keeps working.
    contexts = {
        name: {
            "items": [_ser(it) for it in shell_nav.compose(name)],
            "entry": (shell_nav.CONTEXTS[name].get("entry") or None),
        }
        for name in shell_nav.CONTEXTS
    }

    info = frappe.db.get_value(
        "User", user, ["full_name", "user_image"], as_dict=True
    ) or {}
    return {
        "enabled": True,
        "nav": contexts[shell_nav.DEFAULT_CONTEXT]["items"],
        "contexts": contexts,
        "context_order": list(shell_nav.CONTEXT_ORDER),
        "default_context": shell_nav.DEFAULT_CONTEXT,
        "all_items": [_ser(it) for it in shell_nav.compose_all()],
        "user": {
            "name": user,
            "full_name": info.get("full_name") or user,
            "image": info.get("user_image") or "",
        },
    }


def _ser(it):
    """Serialize one nav item. SECURITY: `no_prerender` is derived from the
    item flag OR the central route policy -- moving/removing a provider can
    never un-protect a no-warm route (route_policy is nav-independent)."""
    from ecentric_workspace.shell import route_policy
    return {
        "key": it["key"],
        "label": it["label"],
        "route": it["route"],
        "icon": it["icon"],
        "group": it["group"],
        "active_patterns": it["active_patterns"],
        "keywords": it.get("keywords", []),
        "no_prerender": bool(it.get("no_prerender")) or route_policy.no_warm(it["route"]),
        "soon": bool(it.get("soon")),
        "alias": bool(it.get("alias")),
        "badge_source": it.get("badge_source") or "",
        "children": [
            {
                "key": ch["key"], "label": ch["label"], "route": ch["route"],
                "icon": ch["icon"], "active_patterns": ch["active_patterns"],
                "keywords": ch.get("keywords", []),
                "no_prerender": bool(ch.get("no_prerender")) or route_policy.no_warm(ch["route"]),
            }
            for ch in it.get("children", [])
        ],
    }
