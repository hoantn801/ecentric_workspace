"""Shared EC Price Policy field validation (Price Setup, 2026-06-14).

ONE validator (single source of truth) used by EVERY write path - the DocType
controller validate(), api_policies.save_policy (JSON), set_policy_status
(activation), and the CSV/paste preview+import - so the rules can never drift.
PURE (frappe-free): takes already-parsed values, returns a list of field-level
error strings. The exact-scope Active conflict guard is NOT here (it stays in
the controller / policy_scope, fired on save).

Mode (binding 2026-06-14; alert-threshold rule revised 2026-06-16 / RC5):
  require_complete=False  (Draft / Paused / Inactive):
      * the numeric fields MAY be missing;
      * a PRESENT min_price is range-checked (> 0).
  require_complete=True   (Active / activation):
      * min_price must be PRESENT and > 0.

  Alert thresholds (high_alert_percent / severe_drop_percent) are owned by EC Alert
  Rule (the Rules overlay) now; on EC Price Policy they are LEGACY fallbacks only and
  are NEVER required - not for Draft, not for Active. A POSITIVE legacy value is still
  range-checked (0 < v <= 100) so genuinely-bad data (e.g. 150) is rejected, but a
  0 / blank legacy value is treated as UNSET and ignored. This is why the RC4 Price
  Setup form (which no longer submits these fields) can SAVE and ACTIVATE without
  them, and why a legacy policy storing high_alert_percent=0 stays editable. The
  alert engine (services.rules / rule_overlay) already has safe fallbacks
  (severe -> DEFAULT_SEVERE_DROP_PERCENT, high optional), so no completeness check
  or silent default is introduced here.

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

    # Alert thresholds: Rules-owned now -> LEGACY fallbacks on the policy. Never
    # required (not even on Active). A 0 / blank legacy value is treated as UNSET and
    # ignored (so a stored 0 never blocks save/activate); a POSITIVE value is still
    # range-checked so bad data (e.g. 150) is rejected. (require_complete no longer
    # gates these - the engine has its own safe fallbacks.)
    for field, label in _PERCENT_FIELDS:
        raw = values.get(field)
        if not _present(raw):
            continue
        try:
            f = float(raw)
        except (TypeError, ValueError):
            errs.append("%s%s (%s) is not a number" % (p, label, field))
            continue
        if f == 0:
            continue  # legacy / unset sentinel - ignored, not an error
        if not (0 < f <= 100):
            errs.append("%s%s (%s) must be > 0 and <= 100" % (p, label, field))

    # date order: enforced whenever BOTH are present (either mode).
    ef, et = values.get("effective_from"), values.get("effective_to")
    if ef and et and str(et) < str(ef):
        errs.append("%seffective_to is before effective_from" % p)

    return errs
