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


# --- G1.1: COMPONENT-BASED configurable price basis -------------------------
# Each brand (EC Brand Alert Config) ticks which discount components are
# subtracted from RSP. effective_check_price =
#   RSP - [seller_discount] - [seller_voucher] - [platform_discount] - [platform_voucher]
# (each term only if its include_* flag is on); optionally overridden by a
# reliable customer-paid unit price. PURE.
COMPONENT_FLAGS = (
    "include_seller_discount",
    "include_seller_voucher",
    "include_platform_discount",
    "include_platform_voucher",
    "use_customer_paid_if_available",
)

DEFAULT_FLAGS = {
    "include_seller_discount": 1,
    "include_seller_voucher": 1,
    "include_platform_discount": 0,
    "include_platform_voucher": 0,
    "use_customer_paid_if_available": 0,
}

_COMPONENT_FIELDS = (
    ("seller_discount", "seller_discount_amount", "include_seller_discount"),
    ("seller_voucher", "seller_voucher_amount", "include_seller_voucher"),
    ("platform_discount", "platform_discount_amount", "include_platform_discount"),
    ("platform_voucher", "platform_voucher_amount", "include_platform_voucher"),
)


def _flag(flags, key):
    v = (flags or {}).get(key, DEFAULT_FLAGS.get(key, 0))
    if isinstance(v, str):
        return v.strip() not in ("", "0", "false", "False", "no", "No")
    return bool(v)


def evaluate_components(line, flags=None):
    """Component-based per-unit effective check price. PURE.
    line provides RSP (list_price) + per-LINE component amounts
    (seller_discount_amount / seller_voucher_amount / platform_discount_amount
    / platform_voucher_amount) and optional customer_paid_price. flags = the
    brand's include_* booleans (default = seller-funded).
    Returns: effective_check_price, price_components_used, rsp_price, and the
    PER-UNIT component amounts actually available (for audit)."""
    flags = flags or DEFAULT_FLAGS
    qty = _f(line.get("quantity"))
    has_qty = bool(qty and qty > 0)

    # Omisell original_price / discount_* / voucher_* are PER-UNIT (golden:
    # original - all four components = discounted_price per unit). So RSP and
    # the component amounts are used as-is. customer_paid_price (if ever
    # populated) is a LINE total -> divide by qty.
    rsp = _f(line.get("list_price"))
    amts = {tag: (_f(line.get(field)) or 0.0) for tag, field, _flagk in _COMPONENT_FIELDS}
    cpp = _f(line.get("customer_paid_price"))
    cpp_u = (cpp / qty) if (cpp is not None and cpp > 0 and has_qty) else (
        cpp if (cpp is not None and cpp > 0) else None)

    # customer-paid override (when reliable + enabled)
    if _flag(flags, "use_customer_paid_if_available") and cpp_u is not None:
        return _result(cpp_u, "customer_paid", rsp, amts, cpp_u)

    if rsp is None or rsp <= 0:
        # no RSP -> fall back to the pre-normalized payload unit price
        payload = _f(line.get("unit_check_price"))
        eff = payload if (payload is not None and payload > 0) else None
        return _result(eff, "payload_unit" if eff is not None else "unresolved",
                       rsp, amts, cpp_u)

    eff = rsp
    used = []
    for tag, _field, flagk in _COMPONENT_FIELDS:
        if _flag(flags, flagk):
            eff -= amts[tag]
            used.append(tag)
    eff = max(eff, 0.0)
    return _result(eff, "+".join(used) or "rsp_only", rsp, amts, cpp_u)


def _result(eff, used, rsp, amts, cpp_u):
    return {
        "effective_check_price": eff,
        "price_components_used": used,
        "rsp_price": rsp,
        "seller_discount_amount": amts["seller_discount"],
        "seller_voucher_amount": amts["seller_voucher"],
        "platform_discount_amount": amts["platform_discount"],
        "platform_voucher_amount": amts["platform_voucher"],
        "customer_paid_price": cpp_u,
    }


def _f(v):
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None
