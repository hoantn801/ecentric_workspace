"""Phase F CSV import for EC Price Policy - server-side parse + validate.

PURE layer (parse_csv/validate_row shape checks) is site-free and unit-tested;
DB checks (brand scope, Link existence) happen in api_policies. Numbers are
parsed SERVER-SIDE with thousand-separator awareness (the vi-VN parseFloat
footgun lives in JS - never trust client parsing for money).
Template (header row) is the contract for the Download-CSV-Template button.
"""
import csv
import io

TEMPLATE_COLUMNS = [
    "brand", "platform", "shop", "seller_sku", "item", "product_name",
    "min_price", "reference_price", "target_price", "high_alert_percent",
    "severe_drop_percent", "enable_stock_safety_lock",
    "effective_from", "effective_to", "status",
]
# Identity/shape fields required at EVERY status (a Draft may omit the numeric
# fields - those are range/completeness-checked by services.policy_validation
# according to the row's status, NOT here).
REQUIRED = ("brand", "platform")
PLATFORMS = ("All", "Shopee", "Lazada", "TikTok")
STATUSES = ("Draft", "Active", "Paused", "Expired", "Inactive")
MAX_ROWS = 500


def template_csv():
    return ",".join(TEMPLATE_COLUMNS) + "\n"


def parse_number(value):
    """Locale-tolerant money/percent parser. Accepts '5000000', '5,000,000',
    '5.000.000' (vi-VN thousands), '5000000.50', '5.000.000,50' (vi decimal
    comma). Returns float or raises ValueError."""
    s = str(value).strip().replace(" ", "")
    if not s:
        raise ValueError("empty")
    if "." in s and "," in s:
        # whichever separator comes LAST is the decimal mark
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        parts = s.split(",")
        s = s.replace(",", "") if len(parts[-1]) == 3 and len(parts) > 1 else s.replace(",", ".")
    elif "." in s:
        parts = s.split(".")
        if len(parts[-1]) == 3 and len(parts) > 1:
            s = s.replace(".", "")   # 5.000.000 -> 5000000 (NEVER 5)
    return float(s)


def parse_csv(text):
    """text -> (rows[dict], errors[str]). Header must equal the template
    (order-insensitive, unknown columns rejected)."""
    reader = csv.DictReader(io.StringIO(text or ""))
    if not reader.fieldnames:
        return [], ["empty file"]
    unknown = [c for c in reader.fieldnames if c.strip() not in TEMPLATE_COLUMNS]
    if unknown:
        return [], ["unknown columns: %s (download the template)" % ", ".join(unknown)]
    rows = [{(k or "").strip(): (v or "").strip() for k, v in r.items()} for r in reader]
    if len(rows) > MAX_ROWS:
        return [], ["too many rows: %d (max %d per batch)" % (len(rows), MAX_ROWS)]
    return rows, []


def validate_row_shape(row, idx):
    """Site-free checks. Returns (normalized_dict_or_None, errors[list])."""
    errs = []
    out = {}
    for k in REQUIRED:
        if not row.get(k):
            errs.append("row %d: %s is required" % (idx, k))
    if row.get("platform") and row["platform"] not in PLATFORMS:
        errs.append("row %d: platform must be one of %s" % (idx, "/".join(PLATFORMS)))
    if row.get("status") and row["status"] not in STATUSES:
        errs.append("row %d: invalid status %r" % (idx, row["status"]))
    if not (row.get("seller_sku") or row.get("item")):
        errs.append("row %d: seller_sku or item is required" % idx)
    # TYPE/shape only: parse the numbers (locale-aware) so downstream gets
    # floats; the >0 / 0<pct<=100 RANGE + required-when-Active rules live in the
    # single shared validator (services.policy_validation), NOT duplicated here.
    for k in ("min_price", "reference_price", "target_price",
              "high_alert_percent", "severe_drop_percent"):
        if row.get(k):
            try:
                out[k] = parse_number(row[k])
            except ValueError:
                errs.append("row %d: %s is not a number: %r" % (idx, k, row[k]))
    if row.get("enable_stock_safety_lock"):
        out["enable_stock_safety_lock"] = 1 if row["enable_stock_safety_lock"].strip().lower() in ("1", "true", "yes") else 0
    # NOTE: effective date ORDER is enforced by the shared validator (both
    # dates present) - not duplicated here.
    for k in ("brand", "platform", "shop", "seller_sku", "item", "product_name",
              "effective_from", "effective_to", "status"):
        if row.get(k):
            out[k] = row[k]
    out.setdefault("status", "Draft")
    return (None, errs) if errs else (out, [])
