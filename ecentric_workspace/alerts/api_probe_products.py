"""G2.2 PROBE-ONLY - Omisell product/catalogue endpoint investigation.

Goal: confirm the real field shape of the product/catalogue READ endpoints
(docs: Get Product List api-6492412, Get Product Detail by SKU api-10762720,
Get Catalogue List api-5741887; exact URL paths NOT published in a fetchable
form) before any SKU-catalog sync is implemented.

STRICT probe-only guarantees:
  * SM-only POST endpoints; GET-only against Omisell - every call goes
    through OmisellClient._request, the frozen ALLOWED_METHODS={GET}
    chokepoint (a write verb is impossible by construction).
  * NO DocType writes: nothing is inserted/updated - NOT EC Marketplace SKU
    Catalog, NOT Order Log, NOT alerts. (Only inherent client token refresh.)
  * NO scheduler / ingest / worker / hooks change. Additive module only.
  * Output is SHAPE-ONLY: key -> {type, sample (sanitized, truncated)} for
    the first item, plus pagination/rate-limit facts. No bulk data dumps.

Intentionally calls the client's private _request: the public client surface
(get_shops/get_orders/get_order_detail) is contract-frozen by
test_phase_d1.test_read_only_surface_unchanged. The real G2.2 implementation
will add public get_product_list/get_catalogue_list methods AND update that
contract test - the probe must not pre-empt that decision.
"""
import json

import frappe
from frappe import _

from ecentric_workspace.alerts.api_omisell import _get_bis
from ecentric_workspace.alerts.services.omisell_client import (
    OmisellClient, OmisellError, sanitize)

# Candidate paths in the style of the 3 confirmed endpoints
# (/api/v2/public/shop/list, /api/v2/public/order/list, /api/v2/public/order/{n}).
CANDIDATE_PATHS = [
    "/api/v2/public/product/list",
    "/api/v2/public/products",
    "/api/v2/public/catalogue/list",
    "/api/v2/public/catalogues",
    "/api/v2/public/product/sku/list",
]
MAX_SAMPLE_CHARS = 120
MAX_KEYS = 60
PROBE_PAGE_SIZE = 2          # shape needs 1-2 items, never bulk
MAX_PAGES = 1                # probe never paginates deep


def _shape(value, depth=0):
    """key -> {type, sample} map; nested dicts/lists summarized one level."""
    if isinstance(value, dict):
        out = {}
        for i, (k, v) in enumerate(value.items()):
            if i >= MAX_KEYS:
                out["..."] = "truncated"
                break
            if isinstance(v, dict):
                out[k] = {"type": "dict",
                          "keys": _shape(v, depth + 1) if depth < 2 else
                          sorted(list(v.keys()))[:MAX_KEYS]}
            elif isinstance(v, list):
                out[k] = {"type": "list", "len": len(v),
                          "item0": _shape(v[0], depth + 1)
                          if v and depth < 2 else None}
            else:
                s = str(v)
                out[k] = {"type": type(v).__name__,
                          "sample": s[:MAX_SAMPLE_CHARS]}
        return out
    return {"type": type(value).__name__,
            "sample": str(value)[:MAX_SAMPLE_CHARS]}


def _probe_one(client, path, params):
    res = {"path": path, "params_sent": params, "ok": False}
    try:
        payload = client._request("GET", path, params=params)
        data = (payload or {}).get("data")
        res["ok"] = True
        res["rate_limit_header"] = client.last_rate_header
        res["envelope_keys"] = sorted((payload or {}).keys())[:MAX_KEYS]
        if isinstance(data, dict):
            res["pagination"] = {k: data.get(k) for k in
                                 ("count", "next", "previous", "page",
                                  "page_size", "total") if k in data}
            results = data.get("results")
            if isinstance(results, list):
                res["results_len"] = len(results)
                res["item_shape"] = _shape(sanitize(results[0])) if results else None
            else:
                res["data_shape"] = _shape(sanitize(data))
        else:
            res["data_shape"] = _shape(sanitize(data))
    except OmisellError as e:
        res["error"] = sanitize(str(e))[:300]
        res["rate_limit_header"] = client.last_rate_header
    except Exception as e:
        res["error"] = sanitize(str(e))[:300]
    return res


@frappe.whitelist(methods=["POST"])
def probe_product_api(brand, path=None, params=None):
    """Probe ONE explicit product/catalogue path for a brand (SM-only).
    params = optional JSON dict merged over {page:1, page_size:2}."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    p = {"page": 1, "page_size": PROBE_PAGE_SIZE}
    if params:
        extra = json.loads(params) if isinstance(params, str) else dict(params)
        p.update({k: v for k, v in extra.items()})
    if not path:
        frappe.throw(_("path is required (e.g. /api/v2/public/product/list)"))
    return {"brand": brand, "probe": _probe_one(client, str(path), p)}


@frappe.whitelist(methods=["POST"])
def probe_product_endpoints(brand, extra_paths=None):
    """Try all candidate product/catalogue paths for a brand (SM-only).
    Returns shape-only results per path; never writes; page_size=2, 1 page."""
    frappe.only_for("System Manager")
    bis = _get_bis(brand)
    client = OmisellClient(bis.name)
    paths = list(CANDIDATE_PATHS)
    if extra_paths:
        more = (json.loads(extra_paths) if isinstance(extra_paths, str)
                else list(extra_paths))
        paths += [str(x) for x in more if str(x) not in paths]
    out = {"brand": brand, "bis": bis.name, "results": [], "live_paths": []}
    for path in paths:
        r = _probe_one(client, path, {"page": 1, "page_size": PROBE_PAGE_SIZE})
        out["results"].append(r)
        if r.get("ok"):
            out["live_paths"].append(path)
    out["note"] = ("SHAPE-ONLY probe: no DocType writes, no SKU Catalog "
                   "writes, GET-only via the frozen client chokepoint.")
    return out
