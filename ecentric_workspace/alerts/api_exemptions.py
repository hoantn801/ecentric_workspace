"""RC7-C Gift/Freebie Price Guard exemption API (V1: dedicated gift Seller SKUs).
Brand-scoped, whitelisted CRUD. No hard delete in V1 (operators inactivate instead;
permanent deletion, if ever added, must follow the same safe-delete contract as
EC Price Policy). The DocType controller enforces uniqueness/overlap on save."""
import json

import frappe
from frappe import _
from frappe.utils import nowdate

from ecentric_workspace.alerts import permissions as perms

FIELDS = ["name", "brand", "platform", "seller_sku", "reason", "status",
          "effective_from", "effective_to", "notes", "exempted_by", "modified"]
EDITABLE = ["brand", "platform", "seller_sku", "reason", "status",
            "effective_from", "effective_to", "notes"]

# Final simplification: gift exemptions are permanent until toggled off, so the normal
# UI exposes only status-based tabs.
LIFECYCLE_STATES = ("active", "inactive", "all")
_BIG_DATE = "9999-99-99"


def derive_lifecycle(row, today):
    """RUNTIME date semantics, retained for back-compat with any LEGACY dated records:
    Inactive -> 'inactive'; otherwise Active with effective_from in the future ->
    'upcoming'; Active with effective_to in the past -> 'expired'; else -> 'effective'.
    NOTE: the normal UI no longer surfaces upcoming/expired tabs - an Active exemption
    stays Active in the DB (the system never auto-flips it to Inactive); the matcher in
    services.exemption_guard separately honours any dates at check time. This helper is
    kept so legacy dated records can still be reasoned about, not for the list tabs."""
    if (row.get("status") or "") == "Inactive":
        return "inactive"
    ef = str(row.get("effective_from"))[:10] if row.get("effective_from") else None
    et = str(row.get("effective_to"))[:10] if row.get("effective_to") else None
    if ef and ef > today:
        return "upcoming"
    if et and et < today:
        return "expired"
    return "effective"


def _status_state(row):
    """UI tab bucket = pure DB status (permanent gift model)."""
    return "active" if (row.get("status") or "") == "Active" else "inactive"


@frappe.whitelist()
def list_exemptions(filters=None, start=0, page_length=20):
    """Scoped, paginated Gift Exemption list with status tabs (ONE list endpoint).
    `filters` (JSON) may carry: lifecycle_state (active|inactive|all), brand, platform,
    seller_sku (search), reason. Returns {rows (current page), total (for the selected
    state), counts (active|inactive|all), lifecycle_state}. All rows + counts respect the
    existing Alert Center brand scope; an EMPTY scope returns zero rows and zero counts
    (never unrestricted). Pagination is applied server-side, so the browser only ever
    receives one page. Tabs are status-based: gift exemptions are permanent until an
    operator toggles them Inactive (legacy effective dates are still stored + honoured by
    the runtime matcher, but are not used to bucket the list)."""
    allowed = perms.require_alert_center_access()
    f = json.loads(filters) if isinstance(filters, str) else (filters or {})
    zero = {s: 0 for s in LIFECYCLE_STATES}
    # --- brand scope (same model as the rest of Alert Center) ---
    q = {}
    if allowed == perms.ALL_BRANDS:
        if f.get("brand"):
            q["brand"] = f["brand"]
    else:
        scope = [b for b in allowed if not f.get("brand") or b == f["brand"]]
        if not scope:
            return {"rows": [], "total": 0, "counts": zero, "lifecycle_state": "active"}
        q["brand"] = ["in", scope]
    # --- non-status filters (combine with the tab) ---
    if f.get("platform"):
        q["platform"] = f["platform"]
    if f.get("reason"):
        q["reason"] = f["reason"]
    if f.get("seller_sku"):
        q["seller_sku"] = ["like", "%%%s%%" % f["seller_sku"]]
    # fetch the scoped+filtered set (bounded by brand scope; gift SKUs are few), bucket
    # by status + count in memory, then paginate the SELECTED state server-side.
    rows = frappe.get_all("EC Price Guard Exemption", filters=q, fields=FIELDS,
                          order_by="modified desc", limit_page_length=0)
    counts = {s: 0 for s in LIFECYCLE_STATES}
    for r in rows:
        st = _status_state(r)
        r["lifecycle"] = st
        counts[st] += 1
        counts["all"] += 1
    state = f.get("lifecycle_state") or "active"
    if state not in LIFECYCLE_STATES:
        state = "active"
    sel = rows if state == "all" else [r for r in rows if r["lifecycle"] == state]
    # rows already arrive most-recent-first (order_by modified desc); keep that order.
    total = len(sel)
    start = max(0, int(start or 0))
    page_length = max(1, int(page_length or 20))
    page = sel[start:start + page_length]
    return {"rows": page, "total": total, "counts": counts, "lifecycle_state": state}


@frappe.whitelist(methods=["POST"])
def save_exemption(exemption=None, name=None):
    perms.require_alert_center_access()
    data = json.loads(exemption) if isinstance(exemption, str) else (exemption or {})
    if not data.get("brand"):
        frappe.throw(_("brand is required"))
    perms.require_brand_access(frappe.session.user, data["brand"])
    if name:
        doc = frappe.get_doc("EC Price Guard Exemption", name)
        perms.require_brand_access(frappe.session.user, doc.brand)
    else:
        doc = frappe.new_doc("EC Price Guard Exemption")
    for k in EDITABLE:
        if k in data:
            doc.set(k, data[k])
    doc.save(ignore_permissions=True)        # controller validates overlap/window
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def set_exemption_status(name, status):
    perms.require_alert_center_access()
    if status not in ("Active", "Inactive"):
        frappe.throw(_("Invalid status {0}").format(status))
    doc = frappe.get_doc("EC Price Guard Exemption", name)
    perms.require_brand_access(frappe.session.user, doc.brand)
    doc.status = status
    doc.save(ignore_permissions=True)        # re-validates overlap when -> Active
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def bulk_save_exemptions(exemptions=None, defaults=None):
    """Create MANY gift exemptions in ONE request (e.g. several SKUs selected in the
    missing-policy list). `defaults` are shared fields (brand, platform, reason, dates,
    status); `exemptions` is a list whose items override the defaults (typically just
    seller_sku). Each row is validated INDEPENDENTLY in its own savepoint, so one bad
    row (e.g. an overlapping exemption) does NOT abort the others. Returns per-item
    results so the UI can clear the successful rows and keep the failed ones selected.
    Brand scope is enforced per row."""
    perms.require_alert_center_access()
    items = json.loads(exemptions) if isinstance(exemptions, str) else (exemptions or [])
    dflt = json.loads(defaults) if isinstance(defaults, str) else (defaults or {})
    results = []
    created = 0
    for idx, it in enumerate(items):
        row = dict(dflt)
        row.update(it or {})
        sku = (row.get("seller_sku") or "").strip()
        res = {"seller_sku": sku, "brand": row.get("brand"), "ok": False}
        sp = "ge_%d" % idx
        try:
            frappe.db.savepoint(sp)
            if not row.get("brand"):
                raise Exception(_("brand is required"))
            if not sku:
                raise Exception(_("seller_sku is required"))
            perms.require_brand_access(frappe.session.user, row["brand"])
            doc = frappe.new_doc("EC Price Guard Exemption")
            for k in EDITABLE:
                if k in row:
                    doc.set(k, row[k])
            doc.save(ignore_permissions=True)   # controller validates overlap/window
            res["ok"] = True
            res["name"] = doc.name
            created += 1
        except Exception as e:
            frappe.db.rollback(save_point=sp)   # undo only THIS row's partial work
            res["error"] = str(e)
        results.append(res)
    return {"results": results, "created": created, "failed": len(results) - created}


def upsert_gift_exemption(brand, platform, seller_sku):
    """RC7 CSV IS_GIFT routing (reused by the CSV import). Canonical key =
    brand + platform + seller_sku (Shop is NOT part of the identity). Idempotent:
      * an Active exemption already exists -> ('already_exists', name)
      * an Inactive exemption exists       -> reactivate it -> ('exemption_reactivated')
      * none                               -> create Active -> ('exemption_created')
    Never creates a duplicate. reason=Gift / Freebie, status=Active, no dates. The
    caller is responsible for brand-scope enforcement."""
    sku = (seller_sku or "").strip()
    rows = frappe.get_all(
        "EC Price Guard Exemption",
        filters={"brand": brand, "platform": platform or "All", "seller_sku": sku},
        fields=["name", "status"])
    active = next((r for r in rows if r.status == "Active"), None)
    if active:
        return ("already_exists", active["name"])
    other = rows[0] if rows else None
    if other:                                   # reactivate an Inactive one (no dup)
        doc = frappe.get_doc("EC Price Guard Exemption", other["name"])
        doc.status = "Active"
        doc.reason = "Gift / Freebie"
        doc.save(ignore_permissions=True)
        return ("exemption_reactivated", doc.name)
    doc = frappe.new_doc("EC Price Guard Exemption")
    doc.brand = brand
    doc.platform = platform or "All"
    doc.seller_sku = sku
    doc.reason = "Gift / Freebie"
    doc.status = "Active"
    doc.save(ignore_permissions=True)
    return ("exemption_created", doc.name)
