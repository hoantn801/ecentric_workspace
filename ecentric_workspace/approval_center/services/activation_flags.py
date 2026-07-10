# Copyright (c) 2026, eCentric and contributors
"""Shared activation-flag parsing for Approval Center activation modules.

Every ``enable_*`` / ``publish_*`` activation method is ``@frappe.whitelist()``d, so its
flags arrive from the browser / HTTP layer as **strings** ("1", "true", "0", "false", "").
Parsing therefore must be string-safe and must never do ``int("true")``.

Contract (safe-by-default): a real, governed execution happens ONLY on an explicit
publish signal. Anything empty, ``None`` or ambiguous stays a dry-run.

    is_dry_run() is True  -> validate only, write nothing
    is_dry_run() is False -> perform the governed mutation

Real execution is triggered when:
  * ``apply`` or ``commit`` is truthy  (1/"1"/True/"true"/yes/"yes"/on/"on"), OR
  * ``dry_run`` is an explicit false token  (0/"0"/False/"false"/no/"no"/off/"off").
"""

_TRUE_TOKENS = ("1", "true", "yes", "on")
_FALSE_TOKENS = ("0", "false", "no", "off")


def is_truthy(value):
    """True for 1/"1"/True/"true"/yes/"yes"/on/"on" (case- and space-insensitive).

    Never raises: non-boolean, non-numeric strings simply return False."""
    if value is True:
        return True
    if value is False or value is None:
        return False
    return str(value).strip().lower() in _TRUE_TOKENS


def is_explicit_false(value):
    """True only for an explicit false token 0/"0"/False/"false"/no/"no"/off/"off".

    Empty string, ``None`` and any ambiguous value return False so the caller stays
    on the safe (dry-run) side. Never raises."""
    if value is None:
        return False
    if value is True:
        return False
    if value is False:
        return True
    return str(value).strip().lower() in _FALSE_TOKENS


def is_dry_run(dry_run=1, apply=0, commit=0):
    """Return True for a safe dry-run, False for a real governed execution.

    See module docstring for the full contract. Safe by default: with no arguments
    (or only ambiguous/empty ones) this returns True."""
    if is_truthy(apply) or is_truthy(commit):
        return False
    if is_explicit_false(dry_run):
        return False
    return True
