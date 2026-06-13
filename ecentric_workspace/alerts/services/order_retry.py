"""Durable per-order retry queue (Hotfix B, 2026-06-13).

A transient order detail/ingest failure during a pull is recorded here so the
chunk can complete and the checkpoint can advance; a scheduled worker later
re-pulls each item via the existing `pull_one_order` path (Order Log
`order_key` dedupe keeps replay safe). DB status is the source of truth.

Guarantees:
  * upsert is IDEMPOTENT by `retry_key = source|brand|order_number`; a
    duplicate queue-upsert in the same pull cycle does NOT bump attempt_count
    (the worker owns attempts) and never duplicates the row.
  * `last_error` is sanitized + truncated - NEVER tokens/credentials/headers/
    full payloads.
  * claim is ATOMIC (conditional UPDATE + per-claim token) so two workers can
    never process the same item; stale `Processing` recovers after a TTL.
  * bounded attempts -> `Dead` + diagnostic; never retries forever.
  * touches ONLY EC Order Retry (+ calls pull_one_order). No catalogue/case/
    ToDo/PM/stock/remote write.
"""
import re

import frappe
from frappe.utils import add_to_date, get_datetime, now_datetime

DEFAULT_MAX_ATTEMPTS = 5
DEFAULT_STALE_MINUTES = 30
DEFAULT_BATCH_SIZE = 20
BACKOFF_BASE_MIN = 5            # first retry ~5 min out
BACKOFF_CAP_MIN = 360          # capped at 6 h
ERROR_MAX_LEN = 500

_SECRET_RE = re.compile(
    r"(?i)(authorization|bearer|token|api[_-]?key|api[_-]?secret|password|secret)"
    r"\s*[:=]?\s*\S+")


def retry_key(brand, order_number, source="Omisell"):
    return "%s|%s|%s" % (source, brand or "", str(order_number or "").strip())


def _save_internal(doc):
    """Save through the controller WITH the sanctioned-transition flag so the
    state-machine guard allows worker/service transitions (a generic Desk/API
    edit, which lacks the flag, is still blocked)."""
    frappe.flags.in_order_retry_transition = True
    try:
        doc.save(ignore_permissions=True)
    finally:
        frappe.flags.in_order_retry_transition = False


# ----- per-brand worker lock (atomic Redis SET NX EX; max 1 worker/brand) ---
_BRAND_LOCK_TTL = 600          # s; > a brand worker's time budget
_RELEASE_LUA = ("if redis.call('get', KEYS[1]) == ARGV[1] "
                "then return redis.call('del', KEYS[1]) else return 0 end")


def _brand_lock_key(brand):
    return "ec_order_retry_brand_%s" % brand


def acquire_brand_lock(brand, token, ttl=_BRAND_LOCK_TTL):
    cache = frappe.cache()
    return bool(cache.set(cache.make_key(_brand_lock_key(brand)), token,
                          nx=True, ex=int(ttl)))


def release_brand_lock(brand, token):
    cache = frappe.cache()
    key = cache.make_key(_brand_lock_key(brand))
    try:
        cache.eval(_RELEASE_LUA, 1, key, token)
    except Exception:
        try:
            if cache.get(key) == (token.encode() if isinstance(token, str) else token):
                cache.delete(key)
        except Exception:
            pass


def _sanitize_error(err):
    """Truncate + strip any secret-looking token. The pull errors are already
    secret-free (HTTP/TIMEOUT messages), this is defense-in-depth."""
    s = str(err or "")
    s = _SECRET_RE.sub(r"\1=***", s)
    return s[:ERROR_MAX_LEN]


def _max_attempts():
    try:
        v = frappe.conf.get("ec_alerts_order_retry_max_attempts")
        return max(1, int(float(v))) if v not in (None, "") else DEFAULT_MAX_ATTEMPTS
    except Exception:
        return DEFAULT_MAX_ATTEMPTS


def _stale_minutes():
    try:
        v = frappe.conf.get("ec_alerts_order_retry_stale_minutes")
        return max(1, int(float(v))) if v not in (None, "") else DEFAULT_STALE_MINUTES
    except Exception:
        return DEFAULT_STALE_MINUTES


def _batch_size():
    try:
        v = frappe.conf.get("ec_alerts_order_retry_batch_size")
        return max(1, min(int(float(v)), 200)) if v not in (None, "") else DEFAULT_BATCH_SIZE
    except Exception:
        return DEFAULT_BATCH_SIZE


def _next_retry_at(attempt):
    """Capped exponential backoff from now."""
    minutes = min(BACKOFF_BASE_MIN * (2 ** max(0, int(attempt))), BACKOFF_CAP_MIN)
    return add_to_date(now_datetime(), minutes=minutes)


# --------------------------- queue write (from pull) ------------------------
def upsert(brand, order_number, error, source="Omisell",
           error_type=None, error_code=None):
    """Idempotently record one failed order. Returns True iff durably
    persisted (the pull uses this to decide queued-vs-unqueued failure).
    Does NOT increment attempt_count (worker owns attempts)."""
    try:
        key = retry_key(brand, order_number, source)
        now = now_datetime()
        err = _sanitize_error(error)
        existing = frappe.db.get_value("EC Order Retry", {"retry_key": key},
                                       ["name", "status"], as_dict=True)
        if not existing:
            frappe.get_doc({
                "doctype": "EC Order Retry", "retry_key": key, "brand": brand or None,
                "source": source, "order_number": str(order_number).strip(),
                "status": "Pending", "attempt_count": 0,
                "max_attempts": _max_attempts(), "last_error": err,
                "error_type": (error_type or None), "error_code": (error_code or None),
                "trigger_source": "Pull Failure",
                "next_retry_at": _next_retry_at(0), "first_failed_at": now,
                "last_attempt_at": now,
            }).insert(ignore_permissions=True)
            return True
        doc = frappe.get_doc("EC Order Retry", existing.name)
        if doc.status in ("Completed", "Dead"):
            # a NEW failure occurrence after a terminal state -> restart cycle
            doc.status = "Pending"
            doc.attempt_count = 0
            doc.first_failed_at = now
            doc.completed_at = None
            doc.next_retry_at = _next_retry_at(0)
            doc.processing_token = None
        # Pending/Processing: refresh diagnostics only; DO NOT bump attempts
        # (avoid double-counting same-cycle upserts).
        doc.last_error = err
        if error_type:
            doc.error_type = error_type
        if error_code:
            doc.error_code = error_code
        doc.last_attempt_at = now
        _save_internal(doc)        # terminal->Pending restart needs the flag
        return True
    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         "alerts.order_retry.upsert %s/%s" % (brand, order_number))
        return False


# --------------------------- worker claim / transitions ---------------------
def recover_stale(threshold_minutes=None):
    """Processing items whose CLAIM is older than the threshold revert to
    Pending (a worker died mid-claim). Uses processing_started_at so a
    genuinely-running item (recent claim) is never stolen. Atomic UPDATE."""
    cutoff = add_to_date(now_datetime(), minutes=-int(threshold_minutes or _stale_minutes()))
    frappe.db.sql(
        """UPDATE `tabEC Order Retry`
           SET status='Pending', processing_token=NULL
           WHERE status='Processing'
             AND (processing_started_at IS NULL OR processing_started_at < %s)""",
        (cutoff,))


def _affected_rows():
    """Rows changed by the LAST statement, if the DB cursor exposes a rowcount;
    else None (caller falls back to the token re-read). Defensive: private
    cursor access is wrapped so an API change can never crash a claim."""
    try:
        cur = getattr(frappe.db, "_cursor", None)
        rc = getattr(cur, "rowcount", None)
        return int(rc) if rc is not None and int(rc) >= 0 else None
    except Exception:
        return None


def _claim(name, token):
    """ATOMIC claim: only a row still in Pending flips to Processing with our
    token + processing_started_at. Two ownership proofs, never process without
    one: (1) affected-row count from the conditional UPDATE when the DB API
    exposes it - 0 rows means we lost the race, fail immediately; (2) re-read
    and compare processing_token as the second confirmation (and the sole
    signal when rowcount is unavailable). The brand worker (not the dispatcher)
    calls this."""
    now = now_datetime()
    frappe.db.sql(
        """UPDATE `tabEC Order Retry`
           SET status='Processing', processing_token=%s,
               processing_started_at=%s, last_attempt_at=%s
           WHERE name=%s AND status='Pending'""",
        (token, now, now, name))
    affected = _affected_rows()
    if affected is not None and affected == 0:
        return False                                # lost the race - no row matched
    # Second ownership confirmation (authoritative when rowcount is unavailable).
    return frappe.db.get_value("EC Order Retry", name, "processing_token") == token


def brands_with_due_items():
    """Distinct brands that have at least one due Pending item (for the
    dispatcher to decide which per-brand workers to enqueue). Read-only,
    NO claim."""
    rows = frappe.db.sql(
        """SELECT DISTINCT brand FROM `tabEC Order Retry`
           WHERE status='Pending' AND next_retry_at <= %s AND brand IS NOT NULL""",
        (now_datetime(),), as_dict=True)
    return [r["brand"] for r in rows]


def claim_due(limit=None, brand=None):
    """Claim up to `limit` due Pending items for ONE brand. Returns the claimed
    docs' dicts. Recovers stale Processing first. Called by the BRAND WORKER
    (never the dispatcher)."""
    recover_stale()
    flt = {"status": "Pending", "next_retry_at": ["<=", now_datetime()]}
    if brand:
        flt["brand"] = brand
    rows = frappe.get_all("EC Order Retry", filters=flt,
                          fields=["name", "brand", "order_number", "source",
                                  "attempt_count", "max_attempts"],
                          order_by="next_retry_at asc",
                          limit_page_length=int(limit or _batch_size()))
    claimed = []
    for r in rows:
        token = frappe.generate_hash(length=20)
        if _claim(r["name"], token):
            r["processing_token"] = token
            claimed.append(r)
    return claimed


def release(name):
    """Return a claimed item to Pending WITHOUT bumping attempt_count (used
    when the worker defers to an active order pull - not a retry attempt)."""
    frappe.db.set_value("EC Order Retry", name,
                        {"status": "Pending", "processing_token": None},
                        update_modified=False)


def mark_completed(name):
    frappe.db.set_value("EC Order Retry", name,
                        {"status": "Completed", "completed_at": now_datetime(),
                         "processing_token": None}, update_modified=True)


def mark_retry(name, error):
    """Transient retry failure: bump attempt; Dead at max, else reschedule."""
    doc = frappe.get_doc("EC Order Retry", name)
    doc.attempt_count = int(doc.attempt_count or 0) + 1
    doc.last_error = _sanitize_error(error)
    doc.last_attempt_at = now_datetime()
    doc.processing_token = None
    if doc.attempt_count >= int(doc.max_attempts or _max_attempts()):
        doc.status = "Dead"
        _save_internal(doc)
        _on_dead(doc)
    else:
        doc.status = "Pending"
        doc.next_retry_at = _next_retry_at(doc.attempt_count)
        _save_internal(doc)
    return doc.status


def _dead_owner(brand):
    """KAM owner of the brand, else Manager/Leader, else None (-> System
    Manager fallback handled by the caller)."""
    try:
        from ecentric_workspace.alerts.services import brand_resolver
        return brand_resolver.resolve_owner(None, brand)
    except Exception:
        return None


def _on_dead(doc):
    """Dead -> ONE actionable Frappe ToDo (not a Notification Log too).
    reference_type=EC Order Retry, reference_name=this item; assigned to the
    brand KAM owner (fallback Manager/Leader, else System Manager). DEDUPE:
    at most one OPEN ToDo per retry item. Content: brand/order/attempts/
    sanitized last_error - NO token/credential. Also keeps an Error Log."""
    try:
        existing = frappe.get_all(
            "ToDo", filters={"reference_type": "EC Order Retry",
                             "reference_name": doc.name, "status": "Open"},
            limit_page_length=1)
        if existing:
            return                                  # dedupe: one open ToDo/item
        owner = _dead_owner(doc.brand)
        if not owner:
            sm = frappe.get_all("Has Role", filters={"role": "System Manager"},
                                fields=["parent"], limit_page_length=1)
            owner = sm[0]["parent"] if sm else "Administrator"
        desc = ("Don %s (brand %s) khong dong bo duoc sau %s lan thu -> Dead. "
                "Loi: %s" % (doc.order_number, doc.brand, doc.attempt_count,
                             _sanitize_error(doc.last_error)))[:1000]
        from frappe.desk.form.assign_to import add as _assign_add
        _assign_add({"doctype": "EC Order Retry", "name": doc.name,
                     "assign_to": [owner], "description": desc})
    except Exception:
        # FAIL-OPEN: the item stays Dead, is NOT reverted to Pending, and the
        # worker transaction is NOT failed just because assignment failed. Log
        # with retry name / brand / order so ops can assign manually.
        frappe.log_error(
            "Dead ToDo assignment failed for retry=%s brand=%s order=%s\n%s"
            % (doc.name, doc.brand, doc.order_number, frappe.get_traceback()),
            "alerts.order_retry._on_dead")
    try:
        frappe.log_error(
            "Order %s (brand %s) reached %s attempts -> Dead. Last error: %s"
            % (doc.order_number, doc.brand, doc.attempt_count, _sanitize_error(doc.last_error)),
            "alerts.order_retry.dead")
    except Exception:
        pass


# --------------------------- manual service transitions ---------------------
# These are the ONLY sanctioned paths the manual API (api_order_retry) calls.
# Each goes through _save_internal so the controller guard allows it; a raw
# Desk/API status edit (no flag) is still rejected. trigger_source="Manual"
# + track_changes give the audit trail.
def manual_retry_now(name):
    """Bring a PENDING item's next attempt forward to now (no state change,
    no attempt bump). Returns the new next_retry_at. Rejects non-Pending."""
    doc = frappe.get_doc("EC Order Retry", name)
    if doc.status != "Pending":
        frappe.throw(frappe._("retry_now only applies to a Pending item (this is %s).") % doc.status)
    doc.next_retry_at = now_datetime()
    doc.trigger_source = "Manual"
    _save_internal(doc)
    return doc.next_retry_at


def manual_requeue(name):
    """Reactivate a TERMINAL (Completed/Dead) item: -> Pending, fresh cycle
    (attempt_count=0). The ONLY sanctioned exit from a terminal state."""
    doc = frappe.get_doc("EC Order Retry", name)
    if doc.status not in ("Completed", "Dead"):
        frappe.throw(frappe._("requeue only applies to a Completed/Dead item (this is %s).") % doc.status)
    doc.status = "Pending"
    doc.attempt_count = 0
    doc.processing_token = None
    doc.completed_at = None
    doc.next_retry_at = now_datetime()
    doc.first_failed_at = now_datetime()
    doc.trigger_source = "Manual"
    _save_internal(doc)
    return doc.status


def manual_mark_dead(name, reason=None):
    """Force a Pending/Processing item to Dead (stop retrying). No ToDo is
    raised (a human chose this and is already aware). Records the reason."""
    doc = frappe.get_doc("EC Order Retry", name)
    if doc.status in ("Completed", "Dead"):
        frappe.throw(frappe._("mark_dead only applies to an active item (this is %s).") % doc.status)
    doc.status = "Dead"
    doc.processing_token = None
    doc.trigger_source = "Manual"
    if reason:
        doc.last_error = _sanitize_error("[manual] %s" % reason)
    _save_internal(doc)
    return doc.status
