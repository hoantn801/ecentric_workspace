"""Alert Center scheduler jobs (Phase E, decision D2-E).

Both jobs are DRY-RUN-SAFE by construction: process_pending_actions can only
end Pending -> Dry Run / Skipped (no HTTP client exists in alerts/), and pause
expiry only flips Active -> Expired. Kill switch: set
`ec_alerts_scheduler_disabled: 1` in site_config -> both jobs no-op instantly.
Fail-safe: any error reading config disables the run. Idempotent: re-runs
find nothing left to do. Per-row try/except + frappe.log_error - one bad row
never kills the batch.
"""
import frappe
from frappe.utils import now_datetime


def _disabled():
    """Global Alert Center scheduler switch - SAFE parser (the bool("0") trap
    fixed for pulls on 2026-06-09 applies here too)."""
    try:
        from ecentric_workspace.alerts.api_omisell import parse_disabled_flag
        return parse_disabled_flag(frappe.conf.get("ec_alerts_scheduler_disabled"))
    except Exception:
        return True  # fail safe: cannot read config -> do nothing


def _scheduled_brands():
    """PURE-ish allowlist reader: site_config ec_alerts_scheduled_pull_brands.
    Missing / empty / not-a-list -> [] (fail-safe no-op). Strings stripped."""
    try:
        v = frappe.conf.get("ec_alerts_scheduled_pull_brands")
    except Exception:
        return []
    if not isinstance(v, (list, tuple)):
        return []
    return [str(x).strip() for x in v if str(x).strip()]


def expire_automation_pauses():
    """Hourly: Active pauses past pause_until -> Expired (doc.save for the
    track_changes audit trail)."""
    if _disabled():
        return
    try:
        names = frappe.get_all(
            "EC Automation Pause",
            filters={"status": "Active", "pause_until": ("<", now_datetime())},
            pluck="name", limit_page_length=500)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "alerts.tasks.expire_pauses query")
        return
    expired = 0
    for name in names:
        try:
            doc = frappe.get_doc("EC Automation Pause", name)
            doc.status = "Expired"
            doc.save(ignore_permissions=True)
            expired += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "alerts.tasks.expire_pauses %s" % name)
    return {"expired": expired, "candidates": len(names)}


def scheduled_omisell_pull():
    """Narrow scheduler (approved 2026-06-10): every 15 min, enqueue the
    VERIFIED pull_recent_job for each allowlisted brand. NO new pull logic
    lives here - this is a timer + gates in front of proven code.

    Gate chain (all fail-safe):
      1. ec_alerts_scheduler_disabled  -> no-op (global, safe parser)
      2. ec_alerts_pull_disabled       -> no-op (pull-specific, safe parser)
      3. ec_alerts_scheduled_pull_brands missing/empty -> no-op
      4. per brand: BIS enabled=1 + credential_status=Active +
         circuit breaker < limit + no running lock -> else skip that brand
    """
    if _disabled():
        return {"skipped": "scheduler_disabled"}
    from ecentric_workspace.alerts import api_omisell as ao
    if ao._pull_disabled():
        return {"skipped": "pull_disabled"}
    brands = _scheduled_brands()
    if not brands:
        return {"skipped": "no_brands_configured"}
    cache = frappe.cache()
    result = {"queued": [], "skipped": {}}
    for brand in brands:
        try:
            bis = frappe.db.get_value(
                "EC Brand Integration Settings",
                {"brand": brand, "integration_type": "Omisell"},
                ["name", "enabled", "credential_status", "consecutive_failures"],
                as_dict=True)
            if not bis or not int(bis.enabled or 0):
                result["skipped"][brand] = "bis_missing_or_disabled"
                continue
            if bis.credential_status != "Active":
                result["skipped"][brand] = "credential_not_active"
                continue
            if int(bis.consecutive_failures or 0) >= ao.CIRCUIT_BREAKER_LIMIT:
                result["skipped"][brand] = "circuit_breaker_open"
                continue
            if cache.get_value(ao._running_key(brand)):
                result["skipped"][brand] = "already_running"
                continue
            cache.set_value(ao._running_key(brand), now_datetime().isoformat(),
                            expires_in_sec=ao.RUNNING_FLAG_TTL)
            frappe.enqueue(
                "ecentric_workspace.alerts.api_omisell.pull_recent_job",
                queue="long", timeout=ao.JOB_RQ_TIMEOUT,
                job_name="omisell_pull_%s" % brand,
                brand=brand, max_chunks=ao.MAX_CHUNKS_PER_RUN)
            result["queued"].append(brand)
        except Exception:
            result["skipped"][brand] = "error_logged"
            frappe.log_error(frappe.get_traceback(),
                             "alerts.tasks.scheduled_omisell_pull %s" % brand)
    frappe.logger("alerts").info({"scheduled_omisell_pull": result})
    return result


def process_action_queue_job():
    """Every 10 minutes: drain Pending Stock Safety Lock actions through the
    dry-run guard chain (pause -> credential -> Dry Run stamp)."""
    if _disabled():
        return
    try:
        from ecentric_workspace.alerts.services import action_queue
        return action_queue.process_pending_actions()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "alerts.tasks.process_action_queue_job")


RETRY_DISPATCH_BUDGET = 360       # s; dispatcher total time budget (5-8 min)
DISPATCH_MARKER_TTL = 120         # s; short-lived per-brand dispatch de-dupe


def _dispatch_marker_key(brand):
    return "ec_order_retry_dispatch_%s" % brand


def _dispatch_budget():
    try:
        v = frappe.conf.get("ec_alerts_order_retry_dispatch_budget_seconds")
        return max(30, int(float(v))) if v not in (None, "") else RETRY_DISPATCH_BUDGET
    except Exception:
        return RETRY_DISPATCH_BUDGET


def dispatch_order_retries():
    """SCHEDULER hook (every 10 min) - LIGHTWEIGHT: only enqueue the dispatcher
    job and return. No claim, no processing here."""
    if _disabled():
        return {"skipped": "scheduler_disabled"}
    job = frappe.enqueue(
        "ecentric_workspace.alerts.tasks.retry_dispatcher_job",
        queue="long", job_name="ec_order_retry_dispatch")
    return {"queued": True, "job_id": getattr(job, "id", None)}


def retry_dispatcher_job():
    """DISPATCHER (background): find brands with due items and enqueue AT MOST
    ONE brand worker per brand. Does NOT claim items (a claimed item must never
    sit Processing while its job is only queued) - the brand worker claims.
    Bounded by a total time budget; leftover brands wait for the next cycle."""
    import time as _t
    if _disabled():
        return {"skipped": "scheduler_disabled"}
    from ecentric_workspace.alerts import api_omisell as ao
    from ecentric_workspace.alerts.services import order_retry
    if ao._pull_disabled():
        return {"skipped": "pull_disabled"}
    res = {"brands": 0, "enqueued": 0, "skipped_locked": 0,
           "skipped_dispatch_marker": 0, "deadline": 0}
    deadline = _t.monotonic() + _dispatch_budget()
    cache = frappe.cache()
    try:
        brands = order_retry.brands_with_due_items()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "alerts.tasks.retry_dispatcher_job")
        return res
    res["brands"] = len(brands)
    for brand in brands:
        if _t.monotonic() > deadline:
            res["deadline"] = 1
            break                                   # leftover -> next cycle
        # A worker is actively running this brand -> nothing to enqueue.
        if cache.get_value(cache.make_key(order_retry._brand_lock_key(brand))):
            res["skipped_locked"] += 1
            continue
        # De-dupe overlapping dispatchers: only the dispatcher that wins this
        # short-lived NX marker enqueues a worker this window. This is pure
        # queue-noise reduction - the worker's own Redis brand lock is the real
        # safety, so any duplicate queued worker that slips through (marker
        # expiry, Redis hiccup) safely no-ops on acquire_brand_lock().
        if not cache.set(cache.make_key(_dispatch_marker_key(brand)),
                         "1", nx=True, ex=DISPATCH_MARKER_TTL):
            res["skipped_dispatch_marker"] += 1
            continue
        frappe.enqueue(
            "ecentric_workspace.alerts.tasks.retry_brand_worker_job",
            queue="long", job_name="ec_order_retry_%s" % brand, brand=brand)
        res["enqueued"] += 1
    frappe.logger("alerts").info({"retry_dispatcher": res})
    return res


def retry_brand_worker_job(brand, limit=None):
    """BRAND WORKER (background): max one active per brand (Redis brand lock).
    Atomically claims a small batch of due items for THIS brand, re-pulls each
    via the existing pull_one_order (Order Log order_key dedupe -> replay safe),
    and transitions the item. Releases the brand lock in finally."""
    if _disabled():
        return {"skipped": "scheduler_disabled"}
    from ecentric_workspace.alerts import api_omisell as ao
    from ecentric_workspace.alerts.services import order_retry
    if ao._pull_disabled():
        return {"skipped": "pull_disabled"}
    token = frappe.generate_hash(length=20)
    if not order_retry.acquire_brand_lock(brand, token):
        return {"skipped": "brand_worker_active", "brand": brand}
    res = {"brand": brand, "claimed": 0, "completed": 0, "retried": 0,
           "dead": 0, "deferred_pull_running": 0, "errors": 0}
    try:
        # order pull PRIORITY: if the brand's order pull is actively running,
        # leave the queue for the next cycle (don't compete for token/API).
        if frappe.cache().get_value(ao._running_key(brand)):
            res["deferred_pull_running"] = 1
            return res
        claimed = order_retry.claim_due(limit, brand)
        res["claimed"] = len(claimed)
        for item in claimed:
            num = item["order_number"]
            try:
                ao.pull_one_order(brand, num)        # dedupe-safe
                order_retry.mark_completed(item["name"])
                res["completed"] += 1
            except Exception as e:
                try:
                    st = order_retry.mark_retry(item["name"], e)
                    res["dead" if st == "Dead" else "retried"] += 1
                except Exception:
                    res["errors"] += 1
                    frappe.log_error(frappe.get_traceback(),
                                     "alerts.tasks.retry_brand_worker_job %s/%s" % (brand, num))
    finally:
        order_retry.release_brand_lock(brand, token)
    frappe.logger("alerts").info({"retry_brand_worker": res})
    return res
