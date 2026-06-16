"""Phase F CSV import for EC Price Policy - server-side parse + validate.

PURE layer (parse_csv/validate_row shape checks) is site-free and unit-tested;
DB checks (brand scope, Link existence) happen in api_policies. Numbers are
parsed SERVER-SIDE with thousand-separator awareness (the vi-VN parseFloat
footgun lives in JS - never trust client parsing for money).
Template (header row) is the contract for the Download-CSV-Template button.
"""
import csv
import io

# Canonical schema (final simplification): a SINGLE column set shared by BOTH the
# "Download CSV Template" button AND the missing-policy export, so the two downloads can
# never drift. Identity = brand + platform + seller_sku. IS_GIFT routes a row to a Gift
# Exemption instead of a Price Policy. min_price is the only required price; target/
# reference are optional.
TEMPLATE_COLUMNS = [
    "brand", "platform", "seller_sku", "product_name",
    "min_price", "target_price", "reference_price", "status", "is_gift",
]
# Old files may still carry these columns; we ACCEPT the file, IGNORE the values, and
# warn. Shop is never persisted; identity no longer uses shop/item; the alert-rule
# tuning fields and effective dates are no longer part of the simplified Price Setup CSV
# (rule tuning lives on the Rules page; gift exemptions are permanent / un-dated).
DEPRECATED_COLUMNS = (
    "shop", "item", "high_alert_percent", "severe_drop_percent",
    "enable_stock_safety_lock", "effective_from", "effective_to",
)
GIFT_TRUE = ("yes", "true", "1", "y")
# Identity/shape fields required at EVERY status (a Draft may omit the numeric
# fields - those are range/completeness-checked by services.policy_validation
# according to the row's status, NOT here).
REQUIRED = ("brand", "platform")
PLATFORMS = ("All", "Shopee", "Lazada", "TikTok")
STATUSES = ("Draft", "Active", "Paused", "Expired", "Inactive")
MAX_ROWS = 500


def _csv_cell(v):
    s = "" if v is None else str(v)
    if any(ch in s for ch in (",", '"', "\n", "\r")):
        s = '"' + s.replace('"', '""') + '"'
    return s


def template_csv_with_rows(rows):
    """Build a CSV using the canonical TEMPLATE_COLUMNS for BOTH downloads: the template
    is header-only (rows=[]), the missing-policy export is header + pre-filled rows.
    `rows` is a list of dicts keyed by canonical column name; unknown keys are ignored
    and missing keys are blank. This is the SINGLE source of column order, so the two
    download buttons cannot drift apart again."""
    out = [",".join(TEMPLATE_COLUMNS)]
    for r in (rows or []):
        out.append(",".join(_csv_cell((r or {}).get(c, "")) for c in TEMPLATE_COLUMNS))
    return "\n".join(out) + "\n"


def template_csv():
    """Header-only template (contract for the Download-CSV-Template button)."""
    return template_csv_with_rows([])


def is_gift_value(v):
    """True iff the IS_GIFT cell is one of YES/TRUE/1/Y (case-insensitive)."""
    return str(v or "").strip().lower() in GIFT_TRUE


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
    """text -> (rows[dict], errors[str], warnings[str]). Header is matched
    case-insensitively against the template (order-insensitive). Deprecated columns
    (shop/item/percent-tuning/effective dates) are ACCEPTED but their values are dropped
    + a warning is returned (back-compat); any OTHER unknown column is rejected. Old
    files are NEVER rejected just for containing legacy columns."""
    reader = csv.DictReader(io.StringIO(text or ""))
    if not reader.fieldnames:
        return [], ["empty file"], []
    fields = [(c or "").strip().lower() for c in reader.fieldnames]
    known = set(TEMPLATE_COLUMNS) | set(DEPRECATED_COLUMNS)
    unknown = [c for c in fields if c and c not in known]
    if unknown:
        return [], ["unknown columns: %s (download the template)" % ", ".join(unknown)], []
    warnings = []
    legacy = sorted({c for c in fields if c in DEPRECATED_COLUMNS})
    if legacy:
        warnings.append("legacy columns ignored: %s" % ", ".join(legacy))
    rows = []
    for r in reader:
        row = {}
        for k, v in r.items():
            kk = (k or "").strip().lower()
            if kk in DEPRECATED_COLUMNS:
                continue                      # ignore shop value entirely (never persisted)
            row[kk] = (v or "").strip()
        rows.append(row)
    if len(rows) > MAX_ROWS:
        return [], ["too many rows: %d (max %d per batch)" % (len(rows), MAX_ROWS)], []
    return rows, [], warnings


def validate_row_shape(row, idx):
    """Site-free checks. Returns (normalized_dict_or_None, errors[list]). Legacy columns
    (shop/item/percent-tuning/effective dates) are never read or persisted. Every row
    needs Brand + Platform + Seller SKU. A GIFT row (is_gift true) routes to a Gift
    Exemption and IGNORES the price fields. A normal Price Policy row REQUIRES min_price
    (target/reference are optional; range + required-when-Active rules stay in the shared
    validator services.policy_validation, not duplicated here)."""
    errs = []
    out = {}
    gift = is_gift_value(row.get("is_gift"))
    out["is_gift"] = gift
    for k in REQUIRED:
        if not row.get(k):
            errs.append("row %d: %s is required" % (idx, k))
    if row.get("platform") and row["platform"] not in PLATFORMS:
        errs.append("row %d: platform must be one of %s" % (idx, "/".join(PLATFORMS)))
    if not row.get("seller_sku"):
        errs.append("row %d: seller_sku is required" % idx)
    if gift:
        # Gift Exemption row: prices/status/dates ignored.
        for k in ("brand", "platform", "seller_sku", "product_name"):
            if row.get(k):
                out[k] = row[k]
        return (None, errs) if errs else (out, [])
    # --- normal Price Policy row ---
    if row.get("status") and row["status"] not in STATUSES:
        errs.append("row %d: invalid status %r" % (idx, row["status"]))
    if not row.get("min_price"):
        errs.append("row %d: min_price is required" % idx)
    # TYPE/shape only: parse the numbers (locale-aware) so downstream gets floats.
    for k in ("min_price", "target_price", "reference_price"):
        if row.get(k):
            try:
                out[k] = parse_number(row[k])
            except ValueError:
                errs.append("row %d: %s is not a number: %r" % (idx, k, row[k]))
    for k in ("brand", "platform", "seller_sku", "product_name", "status"):
        if row.get(k):
            out[k] = row[k]
    out.setdefault("status", "Draft")
    return (None, errs) if errs else (out, [])
