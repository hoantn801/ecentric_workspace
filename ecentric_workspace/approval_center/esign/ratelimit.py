# Copyright (c) 2026, eCentric and contributors
"""Lightweight per-actor rate limiting for governed esign commands (fail-OPEN on cache
error is NOT used here - a cache failure fails CLOSED for write commands and open only for
pure reads, decided by the caller passing fail_closed).

Backed by frappe.cache incr with a TTL window. Deterministic given a clock; the window key
buckets by fixed interval so no background sweeper is needed."""
import frappe
from frappe import _


def _bucket(now_ts, window_s):
    return int(now_ts // window_s)


def hit(action, user=None, limit=30, window_s=60, fail_closed=True):
    """Register one hit for (action,user) in the current window. Returns True if allowed.
    Raises frappe.ValidationError when the limit is exceeded. On cache failure: raise when
    fail_closed (write commands), else allow (pure reads)."""
    user = user or frappe.session.user
    import time
    key = "ec_esign_rl:%s:%s:%s" % (action, user, _bucket(time.time(), window_s))
    try:
        cache = frappe.cache()
        n = cache.incr(key)
        if n == 1:
            cache.expire(key, window_s * 2)
    except Exception:
        if fail_closed:
            frappe.throw(_("Hệ thống giới hạn tần suất tạm thời không khả dụng."),
                         frappe.ValidationError)
        return True
    if n > int(limit):
        frappe.throw(_("Bạn thao tác quá nhanh, vui lòng thử lại sau ít giây."),
                     frappe.ValidationError)
    return True
