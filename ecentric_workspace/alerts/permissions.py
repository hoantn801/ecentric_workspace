"""Alert Center - brand-scoped SERVICE-LAYER permission (Phase B, decision D2).

Modeled on ecentric_workspace.pm.permissions (PM1-T03 pattern):

  * NO new System Roles. NO changes to existing DocTypes' DocPerm. The eight
    Alert Center DocTypes ship with DocPerm = System Manager only, so Desk
    cannot leak data. ALL business access (KAM / brand manager / brand leader)
    goes through whitelisted services that call into this module.
  * Brand scope source of truth = `Brand Approver` (status = Active):
        kam_owner      -> role "kam"      (daily marketplace alert owner, D1)
        manager_email  -> role "manager"
        leader_email   -> role "leader"
    System Manager / Administrator -> global override ("*").
  * No hardcoded users or emails. Fail-safe: unresolved -> no access (never
    silently widen scope).

Capability matrix (MVP, per approved spec):
    handle alert (In Review / Resolve / Ignore) : kam, manager, leader
    create automation pause                     : kam, manager
    cancel automation pause                     : manager, leader
    manage integration credentials              : System Manager only
    execute / retry / cancel alert action       : System Manager only (MVP;
                                                  dry-run era - revisit when
                                                  real execution is enabled)
"""

import frappe
from frappe import _

ALL_BRANDS = "*"

# Brand Approver field -> scope role granted to that user. Order matters:
# first match wins, "kam" strongest for default-view purposes.
_BRAND_ROLE_FIELDS = (
    ("kam_owner", "kam"),
    ("manager_email", "manager"),
    ("leader_email", "leader"),
)

_ROLE_RANK = {"kam": 3, "manager": 2, "leader": 1}


def is_global_supervisor(user=None):
    """System Manager / Administrator -> sees and manages all brands."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return "System Manager" in frappe.get_roles(user)


def get_allowed_brands(user=None):
    """Return ALL_BRANDS ("*") for global supervisors, else a dict
    {brand_code: strongest_scope_role} from active Brand Approver records.

    Empty dict means NO Alert Center access.
    """
    user = user or frappe.session.user
    if is_global_supervisor(user):
        return ALL_BRANDS

    allowed = {}
    try:
        rows = frappe.get_all(
            "Brand Approver",
            filters={"status": "Active"},
            fields=["name", "kam_owner", "manager_email", "leader_email"],
        )
    except Exception:
        # Fail-safe: a broken Brand Approver lookup must never widen access.
        frappe.log_error(frappe.get_traceback(), "alerts.get_allowed_brands")
        return {}

    for row in rows:
        for field, role in _BRAND_ROLE_FIELDS:
            if row.get(field) and row.get(field) == user:
                cur = allowed.get(row["name"])
                if not cur or _ROLE_RANK[role] > _ROLE_RANK[cur]:
                    allowed[row["name"]] = role
    return allowed


def get_brand_role(user, brand):
    """Scope role of `user` on `brand`: 'kam' | 'manager' | 'leader' |
    'supervisor' | None."""
    allowed = get_allowed_brands(user)
    if allowed == ALL_BRANDS:
        return "supervisor"
    return allowed.get(brand)


def require_alert_center_access(user=None):
    """Capability gate for every whitelisted Alert Center service."""
    user = user or frappe.session.user
    allowed = get_allowed_brands(user)
    if allowed == ALL_BRANDS or allowed:
        return allowed
    frappe.throw(_("You do not have access to the Alert Center."), frappe.PermissionError)


def require_brand_access(user, brand):
    """Data-scope gate: throw unless `user` may see `brand`."""
    if not brand:
        frappe.throw(_("Brand is required."), frappe.ValidationError)
    if not get_brand_role(user or frappe.session.user, brand):
        frappe.throw(
            _("You do not have access to brand {0}.").format(brand),
            frappe.PermissionError,
        )


def filter_brands(user, brands):
    """Intersect a brand list with the user's allowed scope (for list APIs)."""
    allowed = get_allowed_brands(user)
    if allowed == ALL_BRANDS:
        return list(brands)
    return [b for b in brands if b in allowed]


# --- capability checks (used by Phase C/E services) -------------------------

def can_handle_alert(user, brand):
    """Mark In Review / Resolve / Ignore alerts of this brand."""
    return get_brand_role(user, brand) in ("kam", "manager", "leader", "supervisor")


def can_create_pause(user, brand):
    """KAM pauses automation only for brands they own; manager too."""
    return get_brand_role(user, brand) in ("kam", "manager", "supervisor")


def can_cancel_pause(user, brand):
    """Lead/Manager can view/cancel team pauses."""
    return get_brand_role(user, brand) in ("manager", "leader", "supervisor")


def can_manage_policy(user, brand):
    """Phase F: EC Price Policy create/edit/status within own brand (master
    data input is the KAM's job; manager included; leader is read-only)."""
    return get_brand_role(user, brand) in ("kam", "manager", "supervisor")


def can_activate_rule(user, brand):
    """Phase F decision F-2: KAM edits Draft rules; ACTIVATION (and pausing)
    is the approval step - manager/leader/System Manager only."""
    return get_brand_role(user, brand) in ("manager", "leader", "supervisor")


def can_review_lock(user, brand):
    """Phase F: approve/reject DRY-RUN lock actions (real execution remains
    System Manager + DS1 gate, untouched here)."""
    return get_brand_role(user, brand) in ("kam", "manager", "leader", "supervisor")


def can_manage_credentials(user=None):
    """EC Brand Integration Settings: System Manager only (MVP). API keys are
    never readable by KAM or any frontend code path."""
    return is_global_supervisor(user)


def can_execute_action(user=None):
    """Execute / retry / cancel EC Alert Action: System Manager only in MVP."""
    return is_global_supervisor(user)
