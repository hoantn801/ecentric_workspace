"""Phase F - EC Price Policy management (KAM-facing, brand-scoped).
Every endpoint: require_alert_center_access first; writes POST-only;
can_manage_policy per brand; Desk stays SM-only."""
import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from ecentric_workspace.alerts import permissions as perms
from ecentric_workspace.alerts.services import policy_csv

FIELDS = ["name", "brand", "platform", "shop", "seller_sku", "item",
          "product_name", "min_price", "reference_price", "target_price",
          "high_alert_percent", "severe_drop_percent",
          "enable_stock_safety_lock", "is_brand_fallback",
          "effective_from", "effective_to", "status", "owner_user",
          "import_batch", "modified"]
EDITABLE = [f for f in FIELDS if f not in ("name", "import_batch", "modified")]
STATUS_FLOW = ("Draft", "Active", "Paused", "Expired", "Inactive")


def _scope(user=None):
    return perms.require_alert_center_access(user)


def _require_manage(brand):
    if not perms.can_manage_policy(frappe.session.user, brand):
        frappe.throw(_("You cannot manage policies of brand {0}.").format(brand),
                     frappe.PermissionError)


@frappe.whitelist()
def list_policies(filters=None, start=0, page_len=50):
    allowed = _scope()
    f = json.loads(filters) if isinstance(filters, str) else (filters or {})
    flt = []
    for k in ("platform", "status", "owner_user", "shop"):
        if f.get(k):
            flt.append([k, "=", f[k]])
    if f.get("seller_sku"):
        flt.append(["seller_sku", "like", "%%%s%%" % f["seller_sku"]])
    if allowed == perms.ALL_BRANDS:
        if f.get("brand"):
            flt.append(["brand", "=", f["brand"]])
    else:
        scope = [b for b in allowed if not f.get("brand") or b == f["brand"]]
        if not scope:
            return {"rows": [], "total": 0}
        flt.append(["brand", "in", scope])
    rows = frappe.get_all("EC Price Policy", filters=flt, fields=FIELDS,
                          order_by="modified desc", start=cint(start),
                          page_length=min(cint(page_len) or 50, 100))
    return {"rows": rows, "total": frappe.db.count("EC Price Policy", filters=flt)}


@frappe.whitelist(methods=["POST"])
def save_policy(policy=None, name=None):
    """Create (no name) or edit. Brand scope enforced on BOTH the target row
    and any attempted brand change."""
    _scope()
    data = json.loads(policy) if isinstance(policy, str) else (policy or {})
    if not data.get("brand"):
        frappe.throw(_("brand is required"))
    _require_manage(data["brand"])
    if name:
        doc = frappe.get_doc("EC Price Policy", name)
        _require_manage(doc.brand)
    else:
        doc = frappe.new_doc("EC Price Policy")
        doc.status = "Draft"
        doc.owner_user = data.get("owner_user") or frappe.session.user
    for k in EDITABLE:
        if k in data:
            doc.set(k, data[k])
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist(methods=["POST"])
def set_policy_status(name, status):
    _scope()
    if status not in STATUS_FLOW:
        frappe.throw(_("Invalid status {0}").format(status))
    doc = frappe.get_doc("EC Price Policy", name)
    _require_manage(doc.brand)
    doc.status = status
    doc.save(ignore_permissions=True)
    return {"name": doc.name, "status": doc.status}


@frappe.whitelist()
def csv_template():
    """Contract for the Download CSV Template button."""
    _scope()
    return {"filename": "ec_price_policy_template.csv",
            "content": policy_csv.template_csv()}


@frappe.whitelist(methods=["POST"])
def preview_policy_csv(content=None):
    """Parse + validate ONLY - writes nothing. Returns per-row verdicts the
    UI shows before the user confirms import."""
    _scope()
    rows, file_errors = policy_csv.parse_csv(content or "")
    if file_errors:
        return {"ok": False, "file_errors": file_errors}
    report = []
    for i, raw in enumerate(rows, start=2):  # header = line 1
        norm, errs = policy_csv.validate_row_shape(raw, i)
        if not errs:
            errs += _db_validate(norm, i)
        report.append({"line": i, "row": raw, "errors": errs, "ok": not errs})
    return {"ok": all(r["ok"] for r in report), "rows": report,
            "valid": sum(1 for r in report if r["ok"]),
            "invalid": sum(1 for r in report if not r["ok"])}


def _db_validate(norm, idx):
    errs = []
    user = frappe.session.user
    if not perms.can_manage_policy(user, norm["brand"]):
        errs.append("row %d: brand %s is outside your scope" % (idx, norm["brand"]))
    elif not frappe.db.exists("Brand Approver", norm["brand"]):
        errs.append("row %d: brand %s does not exist" % (idx, norm["brand"]))
    if norm.get("shop") and not frappe.db.exists("EC Marketplace Shop", norm["shop"]):
        errs.append("row %d: shop %s does not exist" % (idx, norm["shop"]))
    if norm.get("item") and not frappe.db.exists("Item", norm["item"]):
        errs.append("row %d: item %s does not exist" % (idx, norm["item"]))
    return errs


@frappe.whitelist(methods=["POST"])
def import_policy_csv(content=None):
    """Commit a previously previewed batch. Re-validates everything (the
    preview is advisory); only fully-valid rows are written. Upsert key:
    brand+platform+shop+seller_sku+item. Audit: import_batch on every row."""
    _scope()
    preview = preview_policy_csv(content=content)
    if preview.get("file_errors"):
        frappe.throw(_("File rejected: {0}").format("; ".join(preview["file_errors"])))
    batch = "%s|%s" % (now_datetime().strftime("%Y%m%d%H%M%S"), frappe.session.user)
    created, updated, failed = 0, 0, []
    for r in preview["rows"]:
        if not r["ok"]:
            failed.append({"line": r["line"], "errors": r["errors"]})
            continue
        norm, _errs = policy_csv.validate_row_shape(r["row"], r["line"])
        key = {"brand": norm["brand"], "platform": norm.get("platform"),
               "shop": norm.get("shop") or "", "seller_sku": norm.get("seller_sku") or "",
               "item": norm.get("item") or ""}
        existing = frappe.db.get_value("EC Price Policy", key, "name")
        doc = frappe.get_doc("EC Price Policy", existing) if existing \
            else frappe.new_doc("EC Price Policy")
        for k, v in norm.items():
            doc.set(k, v)
        doc.import_batch = batch
        if not doc.owner_user:
            doc.owner_user = frappe.session.user
        doc.save(ignore_permissions=True)
        created, updated = (created, updated + 1) if existing else (created + 1, updated)
    summary = {"batch": batch, "created": created, "updated": updated, "failed": failed}
    return summary
