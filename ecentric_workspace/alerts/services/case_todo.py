"""Step 2 (rev 2026-06-13): two-flow Frappe-native ToDo lifecycle.

FLOW A - Incident ToDo (per Alert Case): one open ToDo per ACTIVE incident
  case (below_min / above_high / severe_price_drop / possible_missing_zero /
  missing_brand_mapping), reference_type="EC Alert". Terminal closes it; a new
  violation after terminal is a new case = a new ToDo (old never reopened).

FLOW B - Setup ToDo (aggregated per Brand): missing_policy is NOT one ToDo per
  case. ONE open setup ToDo per (brand, owner), reference_type="Brand Approver",
  reference_name=brand, description prefixed with the marker
  "[price_setup_missing]". Description shows the distinct missing-COVERAGE SKU
  count (order-derived, from services.policy_coverage - NOT a count of active
  missing_policy EC Alert rows, which are retired as of 2026-06-14); a
  missing_policy case event just triggers a recompute of the same per-brand ToDo;
  when the count reaches 0 the ToDo is closed; a later recurrence creates a NEW
  ToDo (the closed one is never reopened). Reference model approved Q-S2-B.

Assignment API contract = the PROVEN pattern from pm/api/tasks.py:
    from frappe.desk.form.assign_to import add as _assign_add
    _assign_add({"doctype": <DT>, "name": <name>, "assign_to": [<user>]})
  (+ the standard `description` key, which Frappe stores on the ToDo).
Closing does NOT use close_all_assignments (signature unproven here): we query
the active ToDo rows and call the stable public `assign_to.remove(doctype,
name, user)` once per allocated user. We never force-update ToDo.status
directly, so `_assign` on the target stays consistent.

Invariants: recursion guard (frappe.flags), FAIL-OPEN (a ToDo error never
breaks Alert Case insert/update; diagnostic carries brand/case/owner/error),
idempotent (<=1 open ToDo per case / per brand-setup). Touches ONLY Frappe
ToDo + the target doc's _assign (via the API). No PM, order pull, scheduler,
catalogue, Omisell/stock. Zero migration.
"""
import contextlib

import frappe

from ecentric_workspace.alerts.services import case_lifecycle as cl

_GUARD = "_ec_alert_todo_syncing"


@contextlib.contextmanager
def autosync_suspended():
    """Suppress the EC Alert controller's per-row ToDo recompute (the recursion
    guard) so a batch caller (e.g. policy_setup closing many missing_policy
    alerts) can recompute the brand setup ToDo exactly ONCE afterwards via
    sync_brand_setup(), instead of N times via per-alert on_update."""
    prev = getattr(frappe.flags, _GUARD, False)
    setattr(frappe.flags, _GUARD, True)
    try:
        yield
    finally:
        setattr(frappe.flags, _GUARD, prev)

# Classification uses the EXACT rule_code strings emitted by the engine /
# defined in the EC Alert.rule_code Select (verified by grep 2026-06-13; the
# canonical enum is the single source of truth - test_rule_code_inventory
# asserts every enum value is classified here, so a future code can't slip
# through unclassified).
#
# Real emitted codes (NOT the shorthand 'severe_drop'/'missing_zero'):
#   rules._hit -> below_min, above_high, severe_price_drop, possible_missing_zero
#   alert_engine._create_alert -> missing_policy, missing_brand_mapping
#   api_omisell / action_queue -> missing_integration_credential,
#       ingestion_api_failed; (stock_lock_api_failed defined in the enum)

# Flow A - real incidents needing per-case KAM action.
INCIDENT_RULES = frozenset({
    "below_min", "above_high", "severe_price_drop", "possible_missing_zero",
    "missing_brand_mapping",
})
# Flow B - aggregated brand-level price-setup work.
SETUP_RULES = frozenset({"missing_policy"})
# System / integration failures -> System Manager concern, NO KAM ToDo (known
# and intentional - distinct from an UNKNOWN future code, which is logged).
SYSTEM_RULES = frozenset({
    "missing_integration_credential", "ingestion_api_failed",
    "stock_lock_api_failed",
})

SETUP_REF_DOCTYPE = "Brand Approver"
SETUP_MARKER = "[price_setup_missing]"

_INCIDENT_LABEL = {
    "below_min": "Gia duoi muc toi thieu",
    "above_high": "Gia vuot nguong cao",
    "severe_price_drop": "Rot gia manh",
    "possible_missing_zero": "Nghi thieu so 0 (gia bat thuong)",
    "missing_brand_mapping": "Thieu mapping shop/brand",
}


# ----- assignment API (proven add contract + stable remove) -----------------
def _assign_add(args):
    from frappe.desk.form.assign_to import add as _add
    _add(args)


def _assign_remove(doctype, name, user):
    from frappe.desk.form.assign_to import remove as _remove
    _remove(doctype, name, user)


def _open_todos(reference_type, reference_name, extra=None):
    filters = {"reference_type": reference_type,
               "reference_name": reference_name, "status": "Open"}
    if extra:
        filters.update(extra)
    return frappe.get_all("ToDo", filters=filters,
                          fields=["name", "allocated_to", "description"])


def _remove_all(reference_type, reference_name, rows):
    for t in rows:
        if t.allocated_to:
            try:
                _assign_remove(reference_type, reference_name, t.allocated_to)
            except Exception:
                frappe.log_error(frappe.get_traceback(),
                                 "alerts.case_todo.remove %s/%s" % (
                                     reference_type, reference_name))


# ----- FLOW A: incident per-case -------------------------------------------
def _incident_description(case):
    label = _INCIDENT_LABEL.get(case.rule_code, "Canh bao gia")
    sku = case.get("seller_sku") or case.get("item") or "-"
    return "[%s] %s | SKU %s | %s" % (case.name, label, sku, case.get("brand") or "-")


def _ensure_incident_todo(case):
    owner = case.get("owner_user")
    if not owner:
        frappe.logger("alerts").warning({
            "todo_skipped_no_owner": case.name, "brand": case.get("brand"),
            "rule_code": case.get("rule_code")})
        return
    opens = _open_todos("EC Alert", case.name)
    correct = [t for t in opens if t.allocated_to == owner]
    stale = [t for t in opens if t.allocated_to != owner]
    _remove_all("EC Alert", case.name, stale)          # reassign / dedupe wrong owner
    if not correct:
        _assign_add({"doctype": "EC Alert", "name": case.name,
                     "assign_to": [owner],
                     "description": _incident_description(case)})
    elif len(correct) > 1:
        _remove_all("EC Alert", case.name, correct[1:])  # dedupe extras


def _close_incident_todo(case):
    _remove_all("EC Alert", case.name, _open_todos("EC Alert", case.name))


# ----- FLOW B: setup aggregated per brand ----------------------------------
def _remaining_missing_skus(brand):
    """Distinct missing-coverage seller_sku for `brand`, from the CANONICAL
    order-derived coverage source (services.policy_coverage) - NOT from
    missing_policy EC Alert records (2026-06-14: missing_policy is retired as an
    operational alert). Retiring/closing missing_policy alerts therefore does
    NOT change this count; it reflects live order coverage vs active policies, so
    the Setup ToDo only closes when coverage is actually complete."""
    if not brand:
        return 0
    from ecentric_workspace.alerts.services import policy_coverage
    return policy_coverage.missing_count(brand)


def remaining_missing_skus(brand):
    """PUBLIC: distinct ACTIVE missing_policy seller_sku count for `brand` (the
    aggregated Setup ToDo metric). Used by policy_setup (lifecycle summary) and
    the Price Setup per-brand missing summary - one definition, no duplicate."""
    return _remaining_missing_skus(brand)


def _setup_description(brand, count):
    return "%s Thieu thiet lap gia: %d SKU - mo Price Setup (/alerts/policies) cho brand %s" % (
        SETUP_MARKER, count, brand)


def _open_setup_todos(brand, owner=None):
    extra = {"description": ["like", SETUP_MARKER + "%"]}
    if owner:
        extra["allocated_to"] = owner
    return _open_todos(SETUP_REF_DOCTYPE, brand, extra)


def _sync_brand_setup(case):
    # delegate to the public brand-level recompute (used by policy_setup too)
    sync_brand_setup(case.get("brand"), case.get("owner_user"))


def sync_brand_setup(brand, owner=None):
    """PUBLIC entry: recompute the aggregated Setup ToDo for `brand` from the
    current ACTIVE missing_policy case count. Called by the EC Alert controller
    (via _sync_brand_setup) AND by services.policy_setup after auto-closing
    missing_policy alerts. `owner` defaults to the brand's resolved KAM owner so
    a policy-save-driven recompute (no case in hand) still assigns correctly.
    Idempotent; <=1 open setup ToDo per (brand, owner)."""
    if not brand:
        return
    if owner is None:
        try:
            from ecentric_workspace.alerts.services import brand_resolver
            owner = brand_resolver.resolve_owner(None, brand)
        except Exception:
            owner = None
    count = _remaining_missing_skus(brand)
    existing = _open_setup_todos(brand)  # any owner (handles owner change too)
    if count <= 0:
        _remove_all(SETUP_REF_DOCTYPE, brand, existing)  # all done -> close
        return
    if not owner:
        frappe.logger("alerts").warning({
            "setup_todo_skipped_no_owner": brand, "remaining": count})
        return
    correct = [t for t in existing if t.allocated_to == owner]
    stale = [t for t in existing if t.allocated_to != owner]
    _remove_all(SETUP_REF_DOCTYPE, brand, stale)         # owner changed -> reassign
    desc = _setup_description(brand, count)
    if not correct:
        _assign_add({"doctype": SETUP_REF_DOCTYPE, "name": brand,
                     "assign_to": [owner], "description": desc})
    else:
        # REUSE the same open ToDo: update only its description (count). NOT a
        # status/_assign change, so consistency is preserved.
        frappe.db.set_value("ToDo", correct[0].name, "description", desc,
                            update_modified=False)
        if len(correct) > 1:
            _remove_all(SETUP_REF_DOCTYPE, brand, correct[1:])  # dedupe extras


# ----- single entry point ---------------------------------------------------
def sync_todo(case):
    """Called by the EC Alert controller (after_insert + on_update). Dispatch
    by rule; recursion-guarded + FAIL-OPEN."""
    if getattr(frappe.flags, _GUARD, False):
        return
    setattr(frappe.flags, _GUARD, True)
    try:
        rule = case.get("rule_code")
        if rule in SETUP_RULES:
            _sync_brand_setup(case)            # Flow B (recompute brand count)
        elif rule in INCIDENT_RULES:
            if cl.is_terminal(case.status):
                _close_incident_todo(case)
            elif cl.is_active(case.status):
                _ensure_incident_todo(case)
        elif rule in SYSTEM_RULES:
            pass                               # known system alert -> no KAM ToDo
        else:
            # FAIL-SAFE for an unknown/future rule_code: never create an
            # accidental KAM ToDo; log a diagnostic with case/brand/rule.
            frappe.logger("alerts").warning({
                "todo_unknown_rule_code": rule, "case": case.get("name"),
                "brand": case.get("brand")})
    except Exception:
        frappe.log_error(
            frappe.get_traceback(),
            "alerts.case_todo.sync_todo case=%s brand=%s owner=%s status=%s rule=%s" % (
                case.get("name"), case.get("brand"), case.get("owner_user"),
                case.get("status"), case.get("rule_code")))
    finally:
        setattr(frappe.flags, _GUARD, False)
