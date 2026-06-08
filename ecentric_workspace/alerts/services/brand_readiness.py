"""Phase G1 - PURE brand-readiness derivation (no frappe, no I/O).

`derive(facts)` takes a plain dict of already-gathered facts about one brand and
returns {status, blockers, action, running} deterministically. Keeping it pure
makes the precedence logic unit-testable without a site (mirrors the
services/rules.py + chunk_windows pattern) and keeps api_brands.py a thin
fact-gatherer.

Status enum (single primary status, precedence first-match-wins):
    Blocked > Running > Manual Pull Required > Warning > Scheduler Enabled > Ready

`blockers` is the FULL ordered list of every issue found (hard blockers first,
then warnings), each {code, label, severity}. `action` is the single
recommended next step (the onboarding workflow's next move).

Thresholds are passed in (defaults below) so they stay site_config-tunable
without code change. NOTHING here reads secrets - the caller never puts
api_key/api_secret/token into the facts dict.
"""

DEFAULT_STALE_MINUTES = 45        # scheduled-brand freshness (approved G1)
DEFAULT_MIN_COVERAGE = 50.0       # policy-coverage warning floor (%, approved G1)
DEFAULT_BREAKER_LIMIT = 3         # == api_omisell.CIRCUIT_BREAKER_LIMIT

# status constants
BLOCKED = "Blocked"
RUNNING = "Running"
MANUAL_PULL = "Manual Pull Required"
WARNING = "Warning"
SCHEDULER_ENABLED = "Scheduler Enabled"
READY = "Ready"

SEV_BLOCK = "blocker"
SEV_WARN = "warning"


def _b(code, label):
    return {"code": code, "label": label, "severity": SEV_BLOCK}


def _w(code, label):
    return {"code": code, "label": label, "severity": SEV_WARN}


def derive(facts):
    """facts (all plain values; missing keys treated as falsy/None):
      ba_exists, ba_status, kam_owner, manager_email, leader_email,
      bis_exists, enabled, credential_status, dry_run_stock_lock,
      consecutive_failures, last_sync_at, sync_age_minutes (float|None),
      running (bool), in_allowlist (bool), last_run_state (str|None),
      coverage_pct (float|None),
      stale_minutes, min_coverage, breaker_limit  (optional overrides)
    Returns {status, blockers:[...], action:{code,label}, running:bool}.
    """
    f = facts or {}
    stale_minutes = _num(f.get("stale_minutes"), DEFAULT_STALE_MINUTES)
    min_coverage = _num(f.get("min_coverage"), DEFAULT_MIN_COVERAGE)
    breaker_limit = int(_num(f.get("breaker_limit"), DEFAULT_BREAKER_LIMIT))
    running = bool(f.get("running"))

    hard = []
    # --- hard blockers, precedence order ---
    if not f.get("ba_exists") or (f.get("ba_status") or "") != "Active":
        hard.append(_b("missing_brand_approver",
                       "Missing or inactive Brand Approver record"))
    elif not f.get("bis_exists"):
        hard.append(_b("missing_bis",
                       "Missing EC Brand Integration Settings"))
    elif not _truthy(f.get("enabled")):
        hard.append(_b("bis_disabled", "Integration disabled (enabled=0)"))
    elif not _truthy(f.get("dry_run_stock_lock")):
        hard.append(_b("ds1_unsafe",
                       "dry_run_stock_lock != 1 (DS1 requires dry-run)"))
    elif (f.get("credential_status") or "") != "Active":
        hard.append(_b("credential_not_active",
                       "credential_status is not Active"))
    elif int(_num(f.get("consecutive_failures"), 0)) >= breaker_limit:
        hard.append(_b("breaker_open",
                       "Circuit breaker open (consecutive_failures >= %d)" % breaker_limit))

    # --- warnings (only meaningful once hard blockers clear) ---
    warns = []
    never_synced = not f.get("last_sync_at")
    age = f.get("sync_age_minutes")
    stale = (age is not None) and (float(age) > stale_minutes)
    in_allow = bool(f.get("in_allowlist"))
    cov = f.get("coverage_pct")

    if not hard:
        if not f.get("kam_owner"):
            warns.append(_w("no_kam_owner",
                            "No KAM owner on Brand Approver (alerts get fallback owner)"))
        if cov is not None and float(cov) < min_coverage:
            warns.append(_w("low_policy_coverage",
                            "Policy coverage %.0f%% < %.0f%%" % (float(cov), min_coverage)))
        if stale and in_allow:
            warns.append(_w("stale_sync_scheduled",
                            "last_sync_at stale > %d min while scheduler-enabled" % stale_minutes))

    # --- resolve single primary status ---
    blockers = hard + warns
    if hard:
        status = BLOCKED
    elif running:
        status = RUNNING
    elif never_synced or (stale and not in_allow):
        status = MANUAL_PULL
    elif warns:
        status = WARNING
    elif in_allow and (f.get("last_run_state") in ("done", None)) and not stale:
        # in allowlist + fresh + last run ok (None = scheduled but no manual
        # last_run cached yet, still fresh) -> scheduler is keeping it healthy
        status = SCHEDULER_ENABLED
    else:
        status = READY

    return {"status": status, "blockers": blockers,
            "action": _action(status, blockers), "running": running}


_ACTIONS = {
    "missing_brand_approver": ("create_brand_approver",
        "Create/activate the Brand Approver record"),
    "missing_bis": ("create_bis",
        "Create EC Brand Integration Settings before preview/pull"),
    "bis_disabled": ("enable_bis", "Enable the integration (set enabled=1)"),
    "ds1_unsafe": ("fix_ds1", "Set dry_run_stock_lock=1 on the BIS"),
    "credential_not_active": ("run_probe",
        "Run the credential probe to validate keys"),
    "breaker_open": ("reset_breaker",
        "Investigate ingestion_api_failed, then reset Consecutive Failures to 0"),
    "no_kam_owner": ("set_kam", "Set kam_owner on the Brand Approver record"),
    "low_policy_coverage": ("add_policies",
        "Add price policies for uncovered SKUs"),
    "stale_sync_scheduled": ("check_pull_status",
        "Scheduler not keeping data fresh - check pull_status / breaker"),
}

_STATUS_ACTIONS = {
    RUNNING: ("view_pull_status", "Catch-up running - watch pull_status"),
    MANUAL_PULL: ("run_preview_then_pull",
        "Run preview, then a manual pull"),
    READY: ("add_to_scheduler",
        "Verified - add to scheduler allowlist (gated, manual)"),
    SCHEDULER_ENABLED: ("monitor", "Healthy - monitoring"),
}


def _action(status, blockers):
    # the most important thing to do next = first (highest-precedence) blocker's
    # remedy; else the status's onboarding step.
    if blockers:
        code = blockers[0]["code"]
        if code in _ACTIONS:
            c, l = _ACTIONS[code]
            return {"code": c, "label": l}
    if status in _STATUS_ACTIONS:
        c, l = _STATUS_ACTIONS[status]
        return {"code": c, "label": l}
    return {"code": "none", "label": "No action needed"}


def _num(v, default):
    if v is None or v == "":
        return default
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _truthy(v):
    # treat 1/"1"/True as true; 0/"0"/None/"" as false (avoids bool("0")==True)
    if isinstance(v, str):
        return v.strip() not in ("", "0", "false", "False", "no", "No")
    return bool(v)
