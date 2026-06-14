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
