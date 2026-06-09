"""PURE site-tz -> UTC epoch conversion (TZ-FIX 2026-06-10).

Root cause (46_OMISELL_LIST_DIAGNOSTIC, drift_seconds = -25200):
`int(naive_dt.timestamp())` interprets a naive datetime in the SERVER's
local timezone. Frappe Cloud servers run UTC while `now_datetime()` and
DB datetimes are SITE-timezone (Asia/Ho_Chi_Minh) wall time, so every
epoch sent to Omisell order/list was ~7h in the future and the scheduled
pull listed nothing.

This module is intentionally frappe-free (pure: datetime + pytz only) so
the conversion is unit-testable anywhere. api_omisell wraps it with the
site timezone read from System Settings.
"""
from datetime import datetime

import pytz

DEFAULT_SITE_TZ = "Asia/Ho_Chi_Minh"


def epoch_in_tz(dt, tz_name=None):
    """True UTC epoch (int seconds) of `dt`.

    Naive `dt` is interpreted as wall time in `tz_name` (default
    Asia/Ho_Chi_Minh) - NEVER in the server's local timezone. Aware `dt`
    passes through unchanged. Raises TypeError on non-datetime input so a
    stringly-typed call site fails loudly instead of mis-converting.
    """
    if not isinstance(dt, datetime):
        raise TypeError("epoch_in_tz expects a datetime, got %s" % type(dt))
    if dt.tzinfo is None:
        dt = pytz.timezone(tz_name or DEFAULT_SITE_TZ).localize(dt)
    return int(dt.timestamp())


def utc_str(epoch):
    """Human-readable UTC wall time of an epoch - for run summaries/logs."""
    return str(datetime.utcfromtimestamp(int(epoch)))
