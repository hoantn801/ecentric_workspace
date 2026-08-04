# Copyright (c) 2026, eCentric and contributors
"""Shared deadlock-retry helper for PM writes. ERPNext Task nested-set (lft/rgt) updates can
raise MySQL QueryDeadlockError (1213) under concurrency; the DB itself advises 'try restarting
transaction'. This decorator rolls back and retries the wrapped write a few times with a small
backoff, then re-raises. Used by the interactive task create/update paths (and available to the
recurrence scheduler) so a transient deadlock no longer surfaces as a 500."""
import functools
import time

import frappe
from frappe.exceptions import QueryDeadlockError


def retry_on_deadlock(fn=None, attempts=3, base_delay=0.3):
    def deco(f):
        @functools.wraps(f)
        def wrapper(*args, **kwargs):
            for i in range(attempts):
                try:
                    return f(*args, **kwargs)
                except QueryDeadlockError:
                    frappe.db.rollback()
                    if i == attempts - 1:
                        raise
                    time.sleep(base_delay * (i + 1))
        return wrapper
    return deco(fn) if fn else deco
