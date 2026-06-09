"""Omisell order/list window diagnostic (2026-06-10) - READ-ONLY probe.

Why: the scheduled pull (api_omisell) listed 0 orders for a window that
should contain FES-VN order ODVN260609D6414F3F (order_datetime
2026-06-09 21:37:39), while get_order_detail reads that order fine.
Suspects: list timestamp semantics (updated_* vs created), timezone
(naive datetime .timestamp() uses SERVER tz, not site tz), status/shop
filter, or list<->detail inconsistency.

This module sends order/list requests for explicit windows using the
EXACT SAME epoch conversion as production (int(get_datetime(x).timestamp()))
and reports, per window: raw params sent, reported count, listed order
numbers, whether the target appears, and the target's raw list header.
It also reports server-vs-site timezone evidence (tz_evidence.drift_seconds:
0 = server local time matches site tz; -25200 = server runs UTC while the
site is Asia/Ho_Chi_Minh, i.e. every naive .timestamp() is +7h in the
future -> scheduled windows miss recent orders).

Guarantees: NO DocType writes, NO checkpoint (last_sync_at) movement,
NO Order Log / Alert creation. The only possible side effect is the
client's own token refresh inside OmisellClient (unavoidable, same as
every existing pull). SM-only. GET-only against Omisell.
"""
import json
import time
from datetime import datetime

import frappe
from frappe import _
from frappe.utils import get_datetime, now_datetime

from ecentric_workspace.alerts.api_omisell import _get_bis
from ecentric_workspace.alerts.services.omisell_client import (
    OmisellClient, sanitize)

DEFAULT_TARGET = "ODVN260609D6414F3F"
DEFAULT_TARGET_ORDER_DT = "2026-06-09 21:37:39"  # ERP order_datetime of target
MAX_PAGES_PER_PROBE = 4
PAGE_SIZE = 50
TIME_BUDGET_SECONDS = 100          # stay far below gunicorn worker timeout
MAX_NUMBERS_IN_OUTPUT = 120

# Section-6 probe windows (handover 2026-06-10). Strings are interpreted by
# get_datetime() exactly like pull_orders does - intentionally identical.
DEFAULT_WINDOWS = [
    {"label": "w1_vn_local_around_order",
     "from": "2026-06-09 20:00:00", "to": "2026-06-09 23:00:00"},
    {"label": "w2_utc_shifted_minus_7h",
     "from": "2026-06-09 13:00:00", "to": "2026-06-09 16:00:00"},
    {"label": "w3_vn_same_day_wide",
     "from": "2026-06-09 00:00:00", "to": "2026-06-10 02:00:00"},
    {"label": "w4_utc_shifted_wide",
     "from": "2026-06-08 17:00:00", "to": "2026-06-09 19:00:00"},
    {"label": "w5_scheduler_actual_window",
     "from": "2026-06-09 19:16:00", "to": "2026-06-10 01:18:00"},
]

_NUMBER_KEYS = ("omisell_order_number", "order_number", "order_sn", "number")
_TIMEISH = ("time", "date", "created", "updated", "modified")


def _tz_evidence():
    """Server-vs-site timezone facts. drift_seconds is the smoking gun:
    int(time.time()) - int(now_datetime().timestamp()).
    0          -> server local tz == site tz (naive conversion is correct).
    -25200     -> server is UTC, site is UTC+7: every produced epoch is 7h
                  AHEAD of real time, so [last_sync - overlap, now] actually
                  queries a window mostly in the future -> empty lists."""
    site_tz = None
    try:
        site_tz = frappe.db.get_single_value("System Settings", "time_zone")
    except Exception:
        pass
    epoch_now = int(time.time())
    site_now = now_datetime()
    drift = epoch_now - int(site_now.timestamp())
    demo_ts = int(get_datetime(DEFAULT_TARGET_ORDER_DT).timestamp())
    return {
        "site_time_zone": site_tz,
        "now_datetime_site": str(site_now),
        "datetime_now_server": str(datetime.now()),
        "datetime_utcnow": str(datetime.utcnow()),
        "epoch_now_true": epoch_now,
        "epoch_of_now_datetime_naive": int(site_now.timestamp()),
        "drift_seconds": drift,
        "target_order_dt": DEFAULT_TARGET_ORDER_DT,
        "target_dt_epoch_production_style": demo_ts,
        "target_dt_epoch_read_back_utc": str(datetime.utcfromtimestamp(demo_ts)),
        "target_dt_epoch_read_back_server_local": str(datetime.fromtimestamp(demo_ts)),
    }


def _extract_number(header):
    for k in _NUMBER_KEYS:
        v = (header or {}).get(k)
        if v:
            return str(v).strip()
    return None


def _time_fields(header):
    out = {}
    for k, v in (header or {}).items():
        lk = str(k).lower()
        if any(t in lk for t in _TIMEISH) or lk in ("status", "order_status",
                                                    "shop_id", "shop_name",
                                                    "platform"):
            out[k] = v
    return out


def _parse_windows(windows):
    if not windows:
        return DEFAULT_WINDOWS
    if isinstance(windows, str):
        windows = json.loads(windows)
    specs = []
    for i, w in enumerate(windows):
        if isinstance(w, dict):
            specs.append({"label": w.get("label") or ("custom_%s" % (i + 1)),
                          "from": w["from"], "to": w["to"]})
        else:
            specs.append({"label": w[0], "from": w[1], "to": w[2]})
    return specs


def _probe_window(client, spec, target, page_size, max_pages, deadline):
    f, t = get_datetime(spec["from"]), get_datetime(spec["to"])
    if not f or not t or t <= f:
        return {"label": spec["label"], "error": "invalid window"}
    # IDENTICAL conversion to api_omisell.pull_orders (the code under test):
    f_ts, t_ts = int(f.timestamp()), int(t.timestamp())
    res = {
        "label": spec["label"],
        "requested_from": str(f), "requested_to": str(t),
        "raw_params_first_page": {"page": 1, "page_size": page_size,
                                  "updated_from": f_ts, "updated_to": t_ts,
                                  "status_group": "all"},
        "epoch_window_read_back_utc": [str(datetime.utcfromtimestamp(f_ts)),
                                       str(datetime.utcfromtimestamp(t_ts))],
        "listed_count_reported": None, "pages_fetched": 0,
        "fetched_headers": 0, "listed_order_numbers": [],
        "target_found": False, "target_header": None,
        "first_header_time_fields": None, "rate_limit_header": None,
    }
    numbers = []
    try:
        page = 1
        while page <= max_pages:
            if time.monotonic() > deadline:
                res["timeboxed"] = True
                break
            payload = client.get_orders(f_ts, t_ts, page=page,
                                        page_size=page_size)
            data = (payload or {}).get("data") or {}
            results = data.get("results") or []
            if res["listed_count_reported"] is None:
                res["listed_count_reported"] = data.get("count")
            res["pages_fetched"] = page
            res["fetched_headers"] += len(results)
            for h in results:
                num = _extract_number(h)
                if num:
                    numbers.append(num)
                if res["first_header_time_fields"] is None:
                    res["first_header_time_fields"] = sanitize(_time_fields(h))
                if num and num == target:
                    res["target_found"] = True
                    res["target_header"] = sanitize(h)
            if res["target_found"] or not data.get("next") or not results:
                break
            page += 1
        res["rate_limit_header"] = client.last_rate_header
    except Exception as e:
        res["error"] = sanitize(str(e))[:300]
    res["listed_order_numbers"] = numbers[:MAX_NUMBERS_IN_OUTPUT]
    res["listed_order_numbers_total"] = len(numbers)
    return res


@frappe.whitelist(methods=["POST"])
def diagnose_order_list(brand, target_order=None, windows=None,
                        page_size=None, max_pages=None):
    """Run the read-only order/list window probes for one brand.

    Args: brand (e.g. FES-VN); target_order (default ODVN260609D6414F3F);
    windows = optional JSON list of {label,from,to} (default: the 5
    section-6 windows); page_size / max_pages optional tuning.
    Returns tz_evidence + one result block per window. Writes nothing.
    """
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    target = str(target_order or DEFAULT_TARGET).strip()
    specs = _parse_windows(windows)
    psize = int(page_size or PAGE_SIZE)
    mpages = int(max_pages or MAX_PAGES_PER_PROBE)
    deadline = time.monotonic() + TIME_BUDGET_SECONDS

    out = {
        "brand": brand, "bis": bis.name, "target_order": target,
        "page_size": psize, "max_pages_per_probe": mpages,
        "tz_evidence": _tz_evidence(),
        "checkpoint_last_sync_at_untouched": str(bis.last_sync_at),
        "probes": [],
    }
    for spec in specs:
        out["probes"].append(_probe_window(client, spec, target, psize,
                                           mpages, deadline))
        if time.monotonic() > deadline:
            out["timeboxed"] = True
            break
    found = [p["label"] for p in out["probes"] if p.get("target_found")]
    out["summary"] = {
        "target_found_in": found,
        "drift_seconds": out["tz_evidence"]["drift_seconds"],
        "interpretation": (
            "drift_seconds 0 = naive epoch conversion correct on this server; "
            "negative ~ -25200 = server UTC vs site UTC+7, scheduled windows "
            "shifted ~7h into the future. If target appears ONLY in the "
            "utc_shifted windows, the fix is tz-aware epoch conversion in "
            "api_omisell (make_aware via site tz before .timestamp())."),
    }
    return out
