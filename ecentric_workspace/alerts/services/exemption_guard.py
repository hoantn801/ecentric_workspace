"""RC7-C Gift/Freebie Price Guard exemption resolver — the SINGLE source of truth for
"is this (brand, platform, seller_sku) an active dedicated-gift exemption at a given
date". Reused by:
  * services.alert_engine        (skip the line BEFORE policy lookup),
  * services.policy_coverage     (exclude exempt SKUs from the missing-policy count),
  * services.baseline            (exclude gift-window order lines from the 30-day
                                  median so gift prices never contaminate the baseline
                                  after the exemption ends).
The Python `match_exemption`/`is_exempt` and the SQL `exempt_exists_sql` share the SAME
match rules (brand + platform[or All] + seller_sku + Active + date inside the window).

V1 supports DEDICATED gift/freebie Seller SKUs only (whole-SKU). A mixed-use SKU (sold
normally AND given as a gift) must NOT be exempted at the SKU level — that needs a
line-level signal (gift flag / promotion type / campaign marker from the order payload)
and is out of scope here.
"""
import frappe
from frappe.utils import nowdate

# Canonical result / log string for a skipped (exempt) line.
SKIP_RESULT = "Skipped — Gift/Freebie"


def windows_overlap(af, at, bf, bt):
    """Inclusive overlap of [af, at] and [bf, bt]; empty end = open. ISO/lexical."""
    if af and bt and str(af) > str(bt):
        return False
    if bf and at and str(bf) > str(at):
        return False
    return True


def match_exemption(brand, platform, seller_sku, on_date=None):
    """Return the matched ACTIVE EC Price Guard Exemption row {name, reason,
    effective_from, effective_to} when (brand + platform[or All] + seller_sku) has an
    Active exemption whose window contains `on_date` (default today); else None.
    Read-only. This is the ONE place that defines the match rules for Python callers."""
    if not brand or not seller_sku:
        return None
    d = str(on_date or nowdate())[:10]
    rows = frappe.get_all(
        "EC Price Guard Exemption",
        filters={"status": "Active", "brand": brand,
                 "seller_sku": (seller_sku or "").strip(),
                 "platform": ["in", [platform or "All", "All"]]},
        fields=["name", "reason", "effective_from", "effective_to"],
        limit_page_length=0)
    for r in rows:
        ef = str(r.effective_from)[:10] if r.effective_from else None
        et = str(r.effective_to)[:10] if r.effective_to else None
        if (ef is None or ef <= d) and (et is None or et >= d):
            return r
    return None


def is_exempt(brand, platform, seller_sku, on_date=None):
    """Boolean convenience over match_exemption."""
    return match_exemption(brand, platform, seller_sku, on_date) is not None


def exempt_exists_sql(brand_expr, platform_expr, sku_expr, date_expr):
    """Return an SQL EXISTS predicate (string) that is TRUE when an Active exemption
    matches the given column EXPRESSIONS with `date_expr` inside the effective window.
    Reused by coverage + baseline so the matching logic lives in ONE place. The
    arguments are TRUSTED SQL expressions (column references / already-bound params) —
    never raw user input."""
    return (
        "EXISTS (SELECT 1 FROM `tabEC Price Guard Exemption` ge "
        "WHERE ge.status = 'Active' "
        "AND ge.brand = " + brand_expr + " "
        "AND (ge.platform = " + platform_expr + " OR ge.platform = 'All') "
        "AND ge.seller_sku = " + sku_expr + " "
        "AND (ge.effective_from IS NULL OR ge.effective_from <= " + date_expr + ") "
        "AND (ge.effective_to IS NULL OR ge.effective_to >= " + date_expr + "))"
    )
