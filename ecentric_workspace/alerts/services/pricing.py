"""Rule A - unit check price extraction. PURE module (no frappe import) so the
logic is unit-testable anywhere and swappable later (per 04_PHASE_C_DESIGN s2).
"""


def compute_unit_check_price(line):
    """line: dict with quantity / customer_paid_price / unit_check_price /
    list_price / seller_discount. Returns (unit_price_float_or_None, source_tag).

    Priority (approved rule A):
      1. customer_paid_price / quantity   (customer_paid_price is the LINE total)
      2. pre-normalized unit price provided by the payload (unit_check_price)
      3. list_price minus per-unit seller_discount (platform_discount is
         intentionally NOT subtracted - platform-funded subsidy is not a
         seller pricing decision)
    Unresolvable -> (None, "unresolved"); caller skips the line and counts it.
    """
    qty = _f(line.get("quantity"))
    cpp = _f(line.get("customer_paid_price"))
    if cpp is not None and cpp > 0 and qty and qty > 0:
        return cpp / qty, "customer_paid_price/quantity"

    ucp = _f(line.get("unit_check_price"))
    if ucp is not None and ucp > 0:
        return ucp, "payload_unit_price"

    lp = _f(line.get("list_price"))
    if lp is not None and lp > 0:
        sd = _f(line.get("seller_discount")) or 0.0
        per_unit_discount = (sd / qty) if (qty and qty > 0) else sd
        return max(lp - per_unit_discount, 0.0), "list_price_minus_seller_discount"

    return None, "unresolved"


def _f(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
