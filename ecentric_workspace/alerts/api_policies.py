"""Phase F - EC Price Policy management (KAM-facing, brand-scoped).
Every endpoint: require_alert_center_access first; writes POST-only;
can_manage_policy per brand; Desk stays SM-only."""
import json

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

from ecentric_workspace.alerts import permissions as perms
from ecentric_workspace.alerts.services import policy_csv
from ecentric_workspace.alerts.services import policy_validation
from ecentric_workspace.alerts.services import policy_scope
from ecentric_workspace.alerts.services import policy_setup
from ecentric_workspace.alerts.services import case_todo
from ecentric_workspace.alerts.services import case_lifecycle as cl
from ecentric_workspace.alerts.services import policy_coverage

FIELDS = ["name", "brand", "platform", "shop", "seller_sku", "item",
          "product_name", "min_price", "reference_price", "target_price",
          "high_alert_percent", "severe_drop_percent",
          "enable_stock_safety_lock", "is_brand_fallback",
          "effective_from", "effective_to", "status", "owner_user",
          "import_batch", "modified"]
EDITABLE = [f for f in FIELDS if f not in ("name", "import_batch", "modified")]
STATUS_FLOW = ("Draft", "Active", "Paused", "Expired", "Inactive")
# Statuses whose change is an activation/deactivation -> needs can_activate_rule
# (manager / leader / supervisor / SM). KAM may create/edit (Draft/Paused) but
# NOT activate or deactivate (binding 2026-06-14, decision F-2).
ACTIVATION_STATUSES = ("Active", "Inactive")
# fields the shared validator inspects (real DocType fieldnames)
_VALUE_FIELDS = ("min_price", "high_alert_percent", "severe_drop_percent",
                 "effective_from", "effective_to")


def _scope(user=None):
    return perms.require_alert_center_access(user)


def _require_manage(brand):
    if not perms.can_manage_policy(frappe.session.user, brand):
        frappe.throw(_("You cannot manage policies of brand {0}.").format(brand),
                     frappe.PermissionError)


def _require_activate(brand):
    if not perms.can_activate_rule(frappe.session.user, brand):
        frappe.throw(
            _("Only a manager, leader or System Manager can activate/deactivate "
              "a price policy of brand {0}.").format(brand), frappe.PermissionError)


def _doc_values(doc):
    return {k: doc.get(k) for k in _VALUE_FIELDS}


def _validate_values(values, require_complete=False):
    """Explicit pre-save validation via the SINGLE shared validator. The
    DocType controller also calls the same validator on save() (defense in
    depth / Desk path); this just surfaces a clean early error. require_complete
    is True only for Active (full completeness), else range-if-present."""
    errs = policy_validation.validate_policy_values(values, require_complete=require_complete)
    if errs:
        frappe.throw(_("Policy validation failed: {0}").format("; ".join(errs)))


def _import_key(norm):
    return {"brand": norm["brand"], "platform": norm.get("platform"),
            "shop": norm.get("shop") or "", "seller_sku": norm.get("seller_sku") or "",
            "item": norm.get("item") or ""}


def _row_action(norm, existing_name):
    """Determine the import action for one validated row using BOTH keys: the
    5-field import key (Create vs Update identity) and the scope key
    (Active-safety -> Conflict). Returns (action, detail)."""
    if (norm.get("status") or "Draft") == "Active":
        conflict = policy_scope.find_active_conflict(
            norm["brand"], norm.get("platform"), norm.get("shop"),
            norm.get("seller_sku"), norm.get("item"), norm.get("is_brand_fallback"),
            norm.get("effective_from"), norm.get("effective_to"),
            exclude_name=existing_name)
        if conflict:
            return "Conflict", conflict
    if not existing_name:
        return "Create", None
    cur = frappe.get_doc("EC Price Policy", existing_name)
    for k, v in norm.items():
        if str(cur.get(k) or "") != str(v or ""):
            return "Update", existing_name
    return "Skip", existing_name        # existing row identical -> no-op


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
    """Create (no name) or edit. Brand scope on BOTH the target row and any
    brand change. Activation (-> Active/Inactive) needs can_activate_rule. The
    shared validator runs on every save; the controller fires the exact-scope
    Active conflict guard. SINGLE-SAVE TRANSACTION: if the post-save lifecycle
    sync (Step 6) raises, the whole request rolls back (errors propagate)."""
    _scope()
    data = json.loads(policy) if isinstance(policy, str) else (policy or {})
    if not data.get("brand"):
        frappe.throw(_("brand is required"))
    _require_manage(data["brand"])
    if name:
        doc = frappe.get_doc("EC Price Policy", name)
        _require_manage(doc.brand)
        prev_status = doc.status
    else:
        doc = frappe.new_doc("EC Price Policy")
        doc.status = "Draft"
        doc.owner_user = data.get("owner_user") or frappe.session.user
        prev_status = None
    for k in EDITABLE:
        if k in data:
            doc.set(k, data[k])
    new_status = doc.status or "Draft"
    if new_status in ACTIVATION_STATUSES and new_status != prev_status:
        _require_activate(doc.brand)         # KAM cannot activate/deactivate
    # JSON path: full completeness ONLY when Active; else range-if-present.
    _validate_values(_doc_values(doc), require_complete=(new_status == "Active"))
    doc.save(ignore_permissions=True)        # controller re-validates + conflict guard
    lifecycle = None
    if doc.status == "Active":               # Step 6 (propagates -> request rollback)
        lifecycle = policy_setup.terminalize_for_policy(doc, actor=frappe.session.user)
    return {"name": doc.name, "status": doc.status, "lifecycle": lifecycle}


@frappe.whitelist(methods=["POST"])
def set_policy_status(name, status):
    """Status change. Active/Inactive require can_activate_rule; activating also
    re-validates the policy fields. SINGLE-SAVE TRANSACTION (Step 6 propagates)."""
    _scope()
    if status not in STATUS_FLOW:
        frappe.throw(_("Invalid status {0}").format(status))
    doc = frappe.get_doc("EC Price Policy", name)
    _require_manage(doc.brand)
    if status in ACTIVATION_STATUSES:
        _require_activate(doc.brand)
    doc.status = status
    # activation (-> Active) re-runs FULL validation before persisting status;
    # other statuses range-check present values only.
    _validate_values(_doc_values(doc), require_complete=(status == "Active"))
    doc.save(ignore_permissions=True)
    lifecycle = None
    if doc.status == "Active":
        lifecycle = policy_setup.terminalize_for_policy(doc, actor=frappe.session.user)
    return {"name": doc.name, "status": doc.status, "lifecycle": lifecycle}


@frappe.whitelist()
def missing_policy_summary():
    """Per-brand DISTINCT missing-coverage SKU count for the Price Setup summary,
    from the CANONICAL order-derived coverage service (services.policy_coverage)
    - the SAME definition as the coverage modal (policy_missing_skus) and the
    aggregated Setup ToDo, so the chip count and the modal list never disagree.
    Brand-scoped. Returns {summary: {brand: count}}; a brand absent from the map
    is a CONFIRMED 0 (the UI shows 0; '-' only before this loads)."""
    allowed = _scope()
    if allowed == perms.ALL_BRANDS:
        return {"summary": policy_coverage.missing_counts(None)}   # supervisor: all brands
    brands = list(allowed.keys()) if isinstance(allowed, dict) else []
    if not brands:
        return {"summary": {}}
    return {"summary": policy_coverage.missing_counts(brands)}


@frappe.whitelist()
def policy_caps(brand=None):
    """Permission caps for the Price Setup UI (BACKEND is the source of truth -
    the frontend shows/enables controls from THESE flags, never from role text).
    With `brand`: {can_manage, can_activate} for that brand. Without: an
    all_brands flag (global supervisor) + a per-allowed-brand caps map."""
    allowed = _scope()
    user = frappe.session.user
    if brand:
        # Pre-E2E hardening 2026-06-14: an explicit out-of-scope brand request
        # is rejected (not answered with false/false) so caps can never be
        # probed for brands the user may not access. Matches the scope-test
        # requirement "explicit brand=LOF-VN by a FES-only user is rejected".
        perms.require_brand_access(user, brand)
        return {"brand": brand,
                "can_manage": bool(perms.can_manage_policy(user, brand)),
                "can_activate": bool(perms.can_activate_rule(user, brand))}
    if allowed == perms.ALL_BRANDS:
        return {"all_brands": True, "caps": {}}
    brands = list(allowed.keys()) if isinstance(allowed, dict) else []
    return {"all_brands": False,
            "caps": {b: {"can_manage": bool(perms.can_manage_policy(user, b)),
                         "can_activate": bool(perms.can_activate_rule(user, b))}
                     for b in brands}}


@frappe.whitelist()
def policy_conflicts(brand):
    """G2.x Policy Conflict Guard - badge data. Returns, per Active policy name,
    flags: 'duplicate' (another Active policy of the EXACT same scope with
    overlapping validity exists) and/or 'overridden' (a more specific Active
    policy supersedes this one per Shop+Platform+SKU > Platform+SKU > All+SKU).
    Read-only, brand-scoped."""
    _scope()
    perms.require_brand_access(frappe.session.user, brand)
    acts = frappe.get_all(
        "EC Price Policy", filters={"brand": brand, "status": "Active"},
        fields=["name", "platform", "shop", "seller_sku", "item",
                "is_brand_fallback", "effective_from", "effective_to"])
    flags = {}

    def tag(name, t):
        flags.setdefault(name, set()).add(t)

    def tgt(p):
        return (p.get("seller_sku") or "").strip() or (p.get("item") or "").strip()

    def scope(p):
        return ((p.get("platform") or "All"), (p.get("shop") or ""),
                tgt(p) or ("__fallback__" if int(p.get("is_brand_fallback") or 0) else ""))

    def overlap(a, b):
        af, at = a.get("effective_from"), a.get("effective_to")
        bf, bt = b.get("effective_from"), b.get("effective_to")
        if af and bt and str(af) > str(bt):
            return False
        if bf and at and str(bf) > str(at):
            return False
        return True

    # exact-scope duplicates (overlapping validity)
    groups = {}
    for p in acts:
        groups.setdefault(scope(p), []).append(p)
    for members in groups.values():
        n = len(members)
        for i in range(n):
            for j in range(i + 1, n):
                if overlap(members[i], members[j]):
                    tag(members[i].name, "duplicate")
                    tag(members[j].name, "duplicate")

    # overridden by a more-specific Active policy (same SKU/item target)
    for p in acts:
        t = tgt(p)
        if not t:
            continue
        p_all = (p.get("platform") or "All") == "All"
        p_noshop = not (p.get("shop") or "")
        for q in acts:
            if q.name == p.name or tgt(q) != t:
                continue
            more_specific = (
                (p_all and (q.get("platform") or "All") != "All")
                or (p_noshop and (q.get("shop") or "")))
            if more_specific and overlap(p, q):
                tag(p.name, "overridden")
                break

    return {"brand": brand,
            "flags": {n: sorted(list(t)) for n, t in flags.items()},
            "duplicate_count": sum(1 for t in flags.values() if "duplicate" in t)}


def _policy_ever_active(doc):
    """RC7-A: True if the change history shows the policy was EVER Active; False if the
    (tracked) history shows it never was; None if it cannot be determined reliably.
    EC Price Policy has track_changes enabled, so the Version log is authoritative; if
    the log is missing/untracked/unparseable we return None and the caller fails
    closed. We do NOT use scope-based alert matching (it could miss/over-match and risk
    deleting audit history)."""
    if (doc.status or "") == "Active":
        return True
    try:
        meta = frappe.get_meta("EC Price Policy")
        if not getattr(meta, "track_changes", 0):
            return None
        versions = frappe.get_all(
            "Version", filters={"ref_doctype": "EC Price Policy", "docname": doc.name},
            fields=["data"], limit_page_length=0)
    except Exception:
        return None
    for v in versions:
        try:
            changed = (json.loads(v.data or "{}")).get("changed", [])
        except Exception:
            return None          # unparseable history -> fail closed
        for ch in changed:
            if ch and ch[0] == "status" and "Active" in (str(ch[1]), str(ch[2])):
                return True
    return False                 # tracked history, never Active


def _policy_historical_dependency(doc):
    """RC7-A 3-valued historical dependency. The schema has NO direct EC Alert -> EC
    Price Policy relation, so we can only assert 'reliably none' (False) when the
    policy was provably NEVER operationally used: the engine matches ACTIVE policies
    ONLY, so a never-Active policy cannot have produced any alert. A policy that is or
    was Active may have historical alerts we CANNOT enumerate -> None (fail closed)."""
    ever = _policy_ever_active(doc)
    if ever is True:
        return None              # was operational; cannot enumerate historical alerts
    if ever is False:
        return False             # provably never used -> reliably no dependency
    return None                  # unknown -> fail closed


_DELETE_MSGS = {
    "active_no_delete": "An Active price policy cannot be permanently deleted. Pause or deactivate it first.",
    "dependency_unknown": "Cannot verify this policy has no historical alert dependency (the schema has no reliable Alert->Policy link), so permanent deletion is refused for safety. Deactivate/archive it instead.",
    "has_dependents": "Cannot delete: this policy has historical dependent alert records. Deactivate/archive it instead.",
    "admin_only": "Permanent deletion of a {0} policy is admin-only (System Manager). Ordinary users deactivate/archive it.",
}


def _raise_delete_reason(reason, doc):
    if reason is None:
        return
    msg = _(_DELETE_MSGS.get(reason, "Delete not allowed.")).format(doc.status or "Draft")
    if reason == "admin_only":
        frappe.throw(msg, frappe.PermissionError)
    frappe.throw(msg, title=_("Delete blocked"))


@frappe.whitelist()
def policy_delete_capability(name):
    """RC7-A: BACKEND TRUTH for whether a policy may be permanently deleted, so the UI
    never infers eligibility from status alone. Returns {can_delete, delete_reason}.
    Read-only."""
    _scope()
    doc = frappe.get_doc("EC Price Policy", name)
    _require_manage(doc.brand)
    is_admin = perms.is_global_supervisor(frappe.session.user)
    hist = _policy_historical_dependency(doc)
    reason = policy_validation.delete_decision(doc.status or "Draft", is_admin, hist)
    return {"name": name, "can_delete": reason is None, "delete_reason": reason or "ok"}


@frappe.whitelist(methods=["POST"])
def delete_policy(name):
    """RC7-A hardened safe deletion (SAME guard as the controller on_trash). Audit
    history + alert rows are PRESERVED (never touched). The contract +
    historical-dependency proof are in policy_validation.delete_decision /
    _policy_historical_dependency; unknown dependency fails closed."""
    _scope()
    doc = frappe.get_doc("EC Price Policy", name)
    _require_manage(doc.brand)
    is_admin = perms.is_global_supervisor(frappe.session.user)
    hist = _policy_historical_dependency(doc)
    reason = policy_validation.delete_decision(doc.status or "Draft", is_admin, hist)
    _raise_delete_reason(reason, doc)
    st = doc.status
    frappe.delete_doc("EC Price Policy", name, ignore_permissions=True)
    return {"deleted": name, "status": st}


@frappe.whitelist()
def canonical_duplicates(brand=None):
    """RC6 READ-ONLY diagnostic: groups of LIVE (Draft/Active/Paused) EC Price
    Policies that share a CANONICAL identity (brand + platform + normalized
    seller_sku, Shop IGNORED) - i.e. the pre-existing production duplicates the RC6
    guard now forbids, surfaced for MANUAL cleanup. Never mutates data. Scoped to the
    caller's accessible brands (or `brand` if supplied)."""
    allowed = _scope()
    if brand:
        perms.require_brand_access(frappe.session.user, brand)
        brands = [brand]
    elif allowed == perms.ALL_BRANDS:
        brands = None
    else:
        brands = list(allowed)
    groups = policy_scope.canonical_duplicate_groups(brands)
    return {"groups": groups, "group_count": len(groups),
            "total_rows": sum(g["count"] for g in groups)}


@frappe.whitelist()
def csv_template():
    """Contract for the Download CSV Template button."""
    _scope()
    return {"filename": "ec_price_policy_template.csv",
            "content": policy_csv.template_csv()}


@frappe.whitelist(methods=["POST"])
def preview_policy_csv(content=None, source="csv"):
    """Parse + validate ONLY - writes nothing. Per-row ACTION the UI shows
    before commit: Invalid (shape/range/DB error), Conflict (would be Active and
    collides with another Active scope), Update (5-field import key matches an
    existing row + a field changes), Skip (matches but identical = no-op), or
    Create. `source` is 'csv' or 'paste' (both share this backend)."""
    _scope()
    rows, file_errors, warnings = policy_csv.parse_csv(content or "")
    if file_errors:
        return {"ok": False, "file_errors": file_errors, "warnings": warnings, "source": source}
    report = []
    for i, raw in enumerate(rows, start=2):  # header = line 1
        norm, errs = policy_csv.validate_row_shape(raw, i)
        action, detail, existing = "Invalid", None, None
        gift = bool(norm and norm.get("is_gift"))
        if not errs and gift:
            # RC7 IS_GIFT -> Gift Exemption route (Brand+Platform+Seller SKU). Price
            # fields are ignored; predict the idempotent outcome for the preview.
            errs += _db_validate_gift(norm, i)
            if not errs:
                action = _preview_gift_action(norm)
        elif not errs:
            errs += _db_validate(norm, i)
            # mode by the ROW's own status (Active row missing a numeric field ->
            # field-level Invalid; Draft/Paused/Inactive -> range-if-present).
            errs += policy_validation.validate_policy_values(
                norm, require_complete=((norm.get("status") or "Draft") == "Active"),
                prefix="row %d: " % i)
            if not errs:
                existing = frappe.db.get_value("EC Price Policy", _import_key(norm), "name")
                action, detail = _row_action(norm, existing)
        report.append({"line": i, "row": raw, "norm": norm, "is_gift": gift,
                       "errors": errs,
                       "action": "Invalid" if errs else action,
                       "detail": detail, "existing": existing,
                       "ok": not errs and action != "Conflict"})

    def n(act):
        return sum(1 for r in report if r["action"] == act)
    return {"ok": all(r["ok"] for r in report), "rows": report, "source": source,
            "warnings": warnings,
            "counts": {"create": n("Create"), "update": n("Update"),
                       "skip": n("Skip"), "conflict": n("Conflict"),
                       "invalid": n("Invalid"),
                       "exemption_created": n("exemption_created"),
                       "exemption_reactivated": n("exemption_reactivated"),
                       "already_exists": n("already_exists")},
            "valid": sum(1 for r in report if r["ok"]),
            "invalid": sum(1 for r in report if not r["ok"])}


def _db_validate_gift(norm, idx):
    """Gift row DB checks: brand scope + existence only (Seller SKU presence is a shape
    check; Shop/Item are irrelevant to a Gift Exemption)."""
    errs = []
    user = frappe.session.user
    if not perms.can_manage_policy(user, norm["brand"]):
        errs.append("row %d: brand %s is outside your scope" % (idx, norm["brand"]))
    elif not frappe.db.exists("Brand Approver", norm["brand"]):
        errs.append("row %d: brand %s does not exist" % (idx, norm["brand"]))
    return errs


def _preview_gift_action(norm):
    """Predict the idempotent Gift Exemption outcome for the preview (no write)."""
    rows = frappe.get_all(
        "EC Price Guard Exemption",
        filters={"brand": norm["brand"], "platform": norm.get("platform") or "All",
                 "seller_sku": (norm.get("seller_sku") or "").strip()},
        fields=["name", "status"])
    if any(r.status == "Active" for r in rows):
        return "already_exists"
    return "exemption_reactivated" if rows else "exemption_created"


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
def import_policy_csv(content=None, source="csv", lines=None):
    """Commit a previewed CSV/paste batch. Re-derives the per-row action (the
    preview is advisory; re-derivation == confirmation). PARTIAL mode with
    CONTROL: each Create/Update row runs inside its OWN savepoint - a row that
    fails (validation, conflict guard, or its Step-6 lifecycle close) is rolled
    back to the savepoint, marked failed, and the batch CONTINUES. Conflict /
    Invalid rows are NOT written (no silent overwrite). Skip rows are no-ops.
    Active rows trigger Step 6 inside the same savepoint (atomic per row); the
    aggregated Setup ToDo is recomputed ONCE per affected brand at the end.
    Returns created/updated/skipped/failed + per-row errors + lifecycle."""
    _scope()
    preview = preview_policy_csv(content=content, source=source)
    if preview.get("file_errors"):
        frappe.throw(_("File rejected: {0}").format("; ".join(preview["file_errors"])))
    from ecentric_workspace.alerts import api_exemptions
    batch = "%s|%s" % (now_datetime().strftime("%Y%m%d%H%M%S"), frappe.session.user)
    res = {"batch": batch, "source": source,
           "counts": {"policy_created": 0, "policy_updated": 0, "exemption_created": 0,
                      "exemption_reactivated": 0, "already_exists": 0, "skipped": 0,
                      "invalid": 0, "failed": 0},
           "errors": [], "closed_alerts": 0}
    affected_brands = set()
    actor = frappe.session.user
    # optional selective commit: only commit the line numbers the user ticked in
    # the preview (Invalid/Conflict can never be ticked). None = all eligible.
    if lines is not None and isinstance(lines, str):
        lines = json.loads(lines or "[]")
    selected = set(int(x) for x in lines) if lines is not None else None

    for r in preview["rows"]:
        action, line = r["action"], r["line"]
        if action == "Invalid":
            res["counts"]["invalid"] += 1
            res["errors"].append({"line": line, "action": "Invalid", "errors": r["errors"]})
            continue
        if action == "Conflict":
            res["counts"]["invalid"] += 1
            res["errors"].append({"line": line, "action": "Conflict",
                                  "errors": ["row %d: would conflict with active policy %s"
                                             % (line, r.get("detail"))]})
            continue
        if action == "Skip":
            res["counts"]["skipped"] += 1
            continue
        if selected is not None and line not in selected:
            res["counts"]["skipped"] += 1    # eligible but not ticked for commit
            continue
        norm = r["norm"]
        sp = "polrow_%d" % line              # own savepoint (partial-failure isolation)
        frappe.db.savepoint(sp)
        try:
            if norm.get("is_gift"):
                # RC7 IS_GIFT -> idempotent Gift Exemption upsert (NO Price Policy).
                if not perms.can_manage_policy(actor, norm["brand"]):
                    raise Exception("brand %s is outside your scope" % norm["brand"])
                outcome, _nm = api_exemptions.upsert_gift_exemption(
                    norm["brand"], norm.get("platform"), norm.get("seller_sku"))
                res["counts"][outcome] += 1
            else:
                existing = r["existing"]
                doc = frappe.get_doc("EC Price Policy", existing) if existing \
                    else frappe.new_doc("EC Price Policy")
                for k, v in norm.items():
                    if k == "is_gift":       # not a policy field
                        continue
                    doc.set(k, v)
                doc.import_batch = batch
                if not doc.owner_user:
                    doc.owner_user = actor
                doc.save(ignore_permissions=True)   # controller re-checks Active conflict
                if doc.status == "Active":           # Step 6 atomic with this row
                    lc = policy_setup.terminalize_for_policy(doc, actor=actor, recompute=False)
                    res["closed_alerts"] += len(lc.get("closed", []))
                    if lc.get("closed"):
                        affected_brands.add(doc.brand)
                res["counts"]["policy_updated" if existing else "policy_created"] += 1
        except Exception as e:
            frappe.db.rollback(save_point=sp)
            res["counts"]["failed"] += 1
            res["errors"].append({"line": line, "action": action,
                                  "errors": [str(e)[:200]]})
            continue

    # recompute the aggregated Setup ToDo ONCE per affected brand (fail-open)
    for b in sorted(affected_brands):
        try:
            case_todo.sync_brand_setup(b)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "alerts.api_policies.import recompute %s" % b)
    res["affected_brands"] = sorted(affected_brands)
    return res
