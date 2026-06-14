"""Shared EC Price Policy field validation (Price Setup, 2026-06-14).

ONE validator (single source of truth) used by EVERY write path - the DocType
controller validate(), api_policies.save_policy (JSON), set_policy_status
(activation), and the CSV/paste preview+import - so the rules can never drift.
PURE (frappe-free): takes already-parsed values, returns a list of field-level
error strings. The exact-scope Active conflict guard is NOT here (it stays in
the controller / policy_scope, fired on save).

Mode (binding 2026-06-14):
  require_complete=False  (Draft / Paused / Inactive):
      * the numeric fields MAY be missing;
      * but a PRESENT value is still range-checked:
            min_price > 0
            0 < high_alert_percent <= 100
            0 < severe_drop_percent <= 100
  require_complete=True   (Active / activation):
      * min_price / high_alert_percent / severe_drop_percent must be PRESENT
        and pass the same ranges.
  ALWAYS (both modes): if BOTH effective_from and effective_to are present,
        enforce effective_from <= effective_to.

Real DocType fieldnames: min_price / high_alert_percent / severe_drop_percent /
effective_from / effective_to.
"""

_PERCENT_FIELDS = (("high_alert_percent", "High-alert %"),
                   ("severe_drop_percent", "Severe-drop %"))


def _present(v):
    return not (v is None or (isinstance(v, str) and not v.strip()))


def validate_policy_values(values, require_complete=False, prefix=""):
    """Return field-level error strings for one policy's price/date fields.
    `values` keyed by the REAL fieldnames; numbers may be floats (CSV path,
    pre-parsed by policy_csv.parse_number) or numeric (JSON/Desk path)."""
    errs = []
    p = prefix

    # min_price: required only when complete; range-checked whenever present.
    raw = values.get("min_price")
    if _present(raw):
        try:
            if float(raw) <= 0:
                errs.append("%smin_price must be > 0" % p)
        except (TypeError, ValueError):
            errs.append("%smin_price is not a number" % p)
    elif require_complete:
        errs.append("%smin_price is required" % p)

    # percents: independent of each other; required only when complete.
    for field, label in _PERCENT_FIELDS:
        raw = values.get(field)
        if _present(raw):
            try:
                if not (0 < float(raw) <= 100):
                    errs.append("%s%s (%s) must be > 0 and <= 100" % (p, label, field))
            except (TypeError, ValueError):
                errs.append("%s%s (%s) is not a number" % (p, label, field))
        elif require_complete:
            errs.append("%s%s (%s) is required" % (p, label, field))

    # date order: enforced whenever BOTH are present (either mode).
    ef, et = values.get("effective_from"), values.get("effective_to")
    if ef and et and str(et) < str(ef):
        errs.append("%seffective_to is before effective_from" % p)

    return errs
