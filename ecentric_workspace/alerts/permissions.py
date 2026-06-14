"""Alert Center - brand-scoped SERVICE-LAYER permission (Phase B, decision D2).

Modeled on ecentric_workspace.pm.permissions (PM1-T03 pattern):

  * NO new System Roles. NO changes to existing DocTypes' DocPerm. The eight
    Alert Center DocTypes ship with DocPerm = System Manager only, so Desk
    cannot leak data. ALL business access (KAM / brand manager / brand leader)
    goes through whitelisted services that call into this module.
  * Brand scope source of truth = `Brand Approver` (status = Active):
        kam_owner      -> role "kam"      (daily marketplace alert owner, D1)
        manager_email  -> role "manager"  (brand-scoped: this brand only)
        leader_email   -> role "leader"
    A user appearing in several rows gets the UNION of those brands.
    GLOBAL SCOPE ("*") -> System Manager / Administrator, OR an active Employee
    in the Management Department ("Management - EC"; owner decision 2026-06-15).
    Management-Department scope is data-visibility only - it does NOT grant
    System-Manager-only capabilities. Brand Approver.manager_email stays
    brand-scoped and is never conflated with the Management Department.
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

# Owner decision 2026-06-15: a user linked to an ACTIVE Employee in this
# Department also sees ALL brands (global SCOPE), exactly like a supervisor.
# This is a DATA-SCOPE grant only - it does NOT confer System-Manager-only
# capabilities (credential management / action execution / case cancellation),
# which stay gated on is_global_supervisor (Administrator / System Manager).
# The Department docname is company-suffixed in ERPNext ("Management - EC");
# overridable via site_config for non-prod company abbreviations.
_MANAGEMENT_DEPARTMENT_DEFAULT = "Management - EC"


def _management_department():
    return frappe.conf.get("ec_alerts_management_department") or \
        _MANAGEMENT_DEPARTMENT_DEFAULT


def _is_management_employee(user=None):
    """True iff `user` is linked to at least one ACTIVE Employee in the global
    Management Department. Considers ALL matching rows (a user may map to more
    than one Employee), filters on status='Active' (an Inactive/Left/Suspended
    employee does NOT grant scope), and is fail-safe: any lookup error returns
    False so a broken Employee table can never widen access."""
    user = user or frappe.session.user
    if not user or user in ("Guest", "Administrator"):
        return False
    try:
        return bool(frappe.get_all(
            "Employee",
            filters={"user_id": user, "status": "Active",
                     "department": _management_department()},
            limit=1, pluck="name"))
    except Exception:
        # Fail-safe: never widen scope on a broken Employee lookup.
        frappe.log_error(frappe.get_traceback(), "alerts._is_management_employee")
        return False


def is_global_supervisor(user=None):
    """System Manager / Administrator. This is the SYSTEM-MANAGER capability
    predicate (credential management, action execution, case cancellation,
    forced cooldown bypass). It is intentionally NARROWER than global DATA SCOPE
    - Management-Department employees get all-brand visibility via
    get_allowed_brands but are NOT System Managers here."""
    user = user or frappe.session.user
    if user == "Administrator":
        return True
    return "System Manager" in frappe.get_roles(user)


def get_allowed_brands(user=None):
    """Return ALL_BRANDS ("*") for users with GLOBAL SCOPE, else a dict
    {brand_code: strongest_scope_role} = the UNION of brands from active Brand
    Approver records (kam_owner / manager_email / leader_email).

    Global scope (owner model 2026-06-15):
        * Administrator / System Manager  (is_global_supervisor), OR
        * an active Employee in the Management Department.

    Empty dict means NO Alert Center access (deny-by-default - this never falls
    back to all brands).
    """
    user = user or frappe.session.user
    if is_global_supervisor(user) or _is_management_employee(user):
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
    """Mark In Review / Closed / Ignored alerts of this brand (KAM flow)."""
    return get_brand_role(user, brand) in ("kam", "manager", "leader", "supervisor")


def can_run_catalogue_sync(user, brand):
    """Trigger a background catalogue sync for a brand (Phase 4, 2026-06-13):
    KAM/Manager/Leader/Supervisor of the brand. KAM is limited to its assigned
    brand by get_brand_role (brand-scoped). `force=1` (cooldown bypass) is a
    SEPARATE check = is_global_supervisor only (see api_catalogue_sync)."""
    return get_brand_role(user, brand) in ("kam", "manager", "leader", "supervisor")


def can_cancel_case(user=None):
    """Cancel a case (decision D6, 2026-06-13): System Manager / Admin ONLY.
    KAM and Manager never cancel - Cancelled is for wrong/duplicate/invalid
    cases and is excluded from handling KPIs. Brand-agnostic (global)."""
    return is_global_supervisor(user)


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


def can_manage_order_retry(user=None, brand=None):
    """Hotfix B (2026-06-13): manual EC Order Retry actions (retry_now /
    requeue). System Manager / Admin globally, else the brand's manager or
    leader for that specific item's brand. KAM is read-only here (a stuck
    sync is an ops/escalation action, not daily alert handling). Fail-safe:
    unresolved brand role -> no access."""
    if is_global_supervisor(user):
        return True
    if not brand:
        return False
    return get_brand_role(user, brand) in ("manager", "leader", "supervisor")


def can_mark_order_retry_dead(user=None):
    """Force an item to Dead (stop retrying): System Manager / Admin only -
    it suppresses automated recovery, so it is the strongest manual action."""
    return is_global_supervisor(user)
