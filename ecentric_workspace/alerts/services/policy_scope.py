"""Shared EC Price Policy scope-key + Active conflict detection (Price Setup
2026-06-14). SINGLE SOURCE OF TRUTH for "what makes two policies the same
scope" - imported by the controller's exact-scope conflict guard AND by the
bulk-import preview's Conflict detection, so the two can never diverge.

Scope identity (decision G2.x): brand + platform + shop +
(seller_sku ?? item ?? __fallback__). Two ACTIVE policies of the same scope
with overlapping validity windows are ambiguous and forbidden. platform='All'
is a DISTINCT scope from a specific platform (the fallback a specific policy
overrides). This module is intentionally separate from the 5-field CSV import
key (brand+platform+shop+seller_sku+item) which decides record IDENTITY
(Create vs Update); the scope key decides ACTIVE-safety (Conflict)."""
import frappe


def scope_key(platform, shop, seller_sku, item, is_brand_fallback):
    pf = (platform or "All")
    sh = (shop or "")
    tgt = ((seller_sku or "").strip() or (item or "").strip()
           or ("__fallback__" if int(is_brand_fallback or 0) else ""))
    return (pf, sh, tgt)


def windows_overlap(af, at, bf, bt):
    """Inclusive overlap of [af,at] and [bf,bt]; empty end = open. ISO/lexical."""
    if af and bt and str(af) > str(bt):
        return False
    if bf and at and str(bf) > str(at):
        return False
    return True


# === RC6 (2026-06-16): CANONICAL Price Setup identity =======================
# The standard Price Setup model no longer has a Shop input, so Shop must NOT make
# two policies distinct. The canonical identity is brand + platform + normalized
# target, where target = normalized(seller_sku) (falling back to the legacy ERP
# `item` for old rows). Empty target = the brand/platform FALLBACK identity, which is
# DISTINCT from any SKU-specific identity. Normalization is strip()+upper() to mirror
# the DB's case-insensitive matching of seller_sku.
#
# "Non-cancelled" = a policy still live in the workflow. There is no literal
# "Cancelled" status on EC Price Policy; the status set is Draft/Active/Paused/
# Expired/Inactive. Per the lifecycle contract, Expired + Inactive are the
# retired/"cancelled" equivalents and do NOT participate in the canonical conflict;
# the live set below does. So: at most ONE Draft/Active/Paused policy per canonical
# identity; Expired/Inactive rows are ignored (they free up the identity).
LIVE_STATUSES = ("Draft", "Active", "Paused")


def _norm_sku(v):
    return (v or "").strip().upper()


def canonical_key(brand, platform, seller_sku):
    """RC6 canonical identity (brand, platform, normalized seller_sku). Shop AND the
    legacy ERP `item` are intentionally NOT part of the identity: the normal KAM
    workflow no longer exposes ERP Item, so using it would silently allow multiple
    Brand/Platform fallback policies that look identical to the user. target='' => the
    SINGLE brand/platform fallback identity (two empty-SKU rows are the SAME identity
    even if their stored Item differs). seller_sku is normalized strip()+upper()."""
    return ((brand or ""), (platform or "All"), _norm_sku(seller_sku))


def find_canonical_conflict(brand, platform, seller_sku, exclude_name=None):
    """Return {'name','status','shop'} of an existing LIVE (Draft/Active/Paused) EC
    Price Policy that shares this canonical identity (Shop + ERP Item ignored),
    excluding `exclude_name` (self). None if no conflict. Read-only. Platform is
    normalized in Python so legacy NULL/empty platforms still compare correctly."""
    me = canonical_key(brand, platform, seller_sku)
    rows = frappe.get_all(
        "EC Price Policy",
        filters={"brand": brand, "status": ["in", LIVE_STATUSES]},
        fields=["name", "status", "platform", "seller_sku", "shop"])
    for r in rows:
        if r.name == (exclude_name or ""):
            continue
        if canonical_key(brand, r.platform, r.seller_sku) == me:
            return {"name": r.name, "status": r.status, "shop": r.shop or ""}
    return None


def canonical_guard_conflict(status, brand, platform, seller_sku, exclude_name=None):
    """The EXACT decision the controller guard makes: enforce canonical uniqueness
    ONLY when the document's target `status` is LIVE (Draft/Active/Paused). For a
    retired/terminal status (Inactive/Expired/anything not live) it returns None so
    operators can retire one of two existing duplicates. Self is excluded by
    `exclude_name`. Read-only."""
    if (status or "") not in LIVE_STATUSES:
        return None
    return find_canonical_conflict(brand, platform, seller_sku, exclude_name)


def canonical_duplicate_groups(brands=None):
    """READ-ONLY diagnostic: groups of LIVE EC Price Policies that share a canonical
    identity (i.e. existing duplicates that the RC6 guard would now forbid), for
    MANUAL cleanup. Never mutates data. `brands` optionally limits the scan; an EMPTY
    list means "no accessible brands" and returns [] (never a full-table scan), so a
    caller can safely pass a brand-scoped list. Returns a list of
    {'brand','platform','seller_sku','members':[{name,status,shop,...}]} for every
    canonical key with 2+ live members."""
    if brands is not None and not brands:
        return []
    flt = {"status": ["in", LIVE_STATUSES]}
    if brands:
        flt["brand"] = ["in", list(brands)]
    rows = frappe.get_all(
        "EC Price Policy", filters=flt,
        fields=["name", "status", "brand", "platform", "shop", "seller_sku",
                "modified"],
        order_by="brand asc, platform asc, seller_sku asc, modified desc")
    groups = {}
    for r in rows:
        k = canonical_key(r.brand, r.platform, r.seller_sku)
        groups.setdefault(k, []).append(r)
    out = []
    for k, members in groups.items():
        if len(members) > 1:
            out.append({"brand": k[0], "platform": k[1],
                        "seller_sku": k[2] or "(fallback)",
                        "count": len(members), "members": members})
    out.sort(key=lambda g: (-g["count"], g["brand"], g["platform"]))
    return out


def find_active_conflict(brand, platform, shop, seller_sku, item,
                         is_brand_fallback, effective_from, effective_to,
                         exclude_name=None):
    """Name of an EXISTING Active EC Price Policy with the EXACT same scope_key
    as the candidate AND an overlapping validity window (i.e. the controller's
    _guard_exact_scope_conflict would throw), EXCLUDING `exclude_name` (the
    row's own import-key match). None if no conflict. Read-only."""
    my = scope_key(platform, shop, seller_sku, item, is_brand_fallback)
    narrow = {"brand": brand, "status": "Active"}
    if seller_sku:
        narrow["seller_sku"] = seller_sku
    elif item:
        narrow["item"] = item
    else:
        narrow["is_brand_fallback"] = 1
    rows = frappe.get_all(
        "EC Price Policy", filters=narrow,
        fields=["name", "platform", "shop", "seller_sku", "item",
                "is_brand_fallback", "effective_from", "effective_to"])
    for r in rows:
        if r.name == (exclude_name or ""):
            continue
        if scope_key(r.platform, r.shop, r.seller_sku, r.item,
                     r.is_brand_fallback) != my:
            continue
        if windows_overlap(effective_from, effective_to,
                           r.effective_from, r.effective_to):
            return r.name
    return None
