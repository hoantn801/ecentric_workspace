# Copyright (c) 2026, eCentric and contributors
"""Submit a Weekly Team Update.

A21/A57: deck bytes go straight from the browser to SharePoint via an upload
session, so this service only ever receives {name, web_url} pairs. No base64,
no binary, nothing that depends on frappe.request -- which the python3.14
upgrade removed from the Server Script sandbox.

Public API:
  submit(payload) -> dict
      {"success": True, "name": <docname>, "deck_count": n, "errors": [...]}
      Raises SubmitError when week_label / employee are missing.
"""

import json

import frappe
from frappe.utils import now

from ecentric_workspace.weekly_report import sharepoint


WTU = "Weekly Team Update"
SUBMITTED = "Submitted"

TEXT_FIELDS = (
    "full_name", "department", "designation",
    "what_done", "pending_progress", "plan_next_week", "blockers_help",
    "ai_tools_used", "ai_tools_other", "ai_use_case", "ai_status", "mood",
)
DATE_FIELDS = ("week_start_date", "week_end_date")


class SubmitError(Exception):
    """Payload is unusable -- the API layer maps this to a friendly message."""


def _dept_clean(department):
    dept = department or "Unknown"
    return dept.rsplit(" - ", 1)[0] if " - " in dept else dept


def _get_or_create(payload, employee, week_label):
    # Existence MUST be keyed by (employee, week) because the docname is built
    # from employee -- keying it on submitter caused the 1062 duplicate
    # collisions fixed 2026-08-24.
    name = frappe.db.get_value(
        WTU, {"employee": employee, "week_label": week_label}, "name"
    )
    if name:
        return frappe.get_doc(WTU, name)
    doc = frappe.new_doc(WTU)
    doc.week_label = week_label
    doc.employee = employee
    doc.submitter = payload.get("submitter") or frappe.session.user
    emp_code = frappe.db.get_value("Employee", employee, "employee_number")
    if emp_code:
        doc.name = "WTU-{0}-{1}-{2}".format(
            week_label, emp_code, _dept_clean(payload.get("department"))
        )
        doc.flags.name_set = True
    return doc


def _apply_fields(doc, payload):
    for field in TEXT_FIELDS:
        setattr(doc, field, payload.get(field) or "")
    for field in DATE_FIELDS:
        setattr(doc, field, payload.get(field) or None)
    doc.ai_usage_score = int(payload.get("ai_usage_score") or 0)
    doc.overall_status = payload.get("overall_status") or payload.get("status") or ""
    doc.status = SUBMITTED
    doc.submitted_at = now()


def _current_urls(doc):
    urls = [u.strip() for u in (doc.slide_deck or "").split("\n") if u.strip()]
    if len(urls) == 1 and urls[0].startswith("["):
        try:
            return [u for u in json.loads(urls[0]) if u]
        except ValueError:
            return urls
    return urls


def _delete_removed(removed, errors):
    try:
        token = sharepoint.get_app_token()
    except Exception as exc:
        errors.append("token: " + str(exc)[:100])
        return
    for url in removed:
        try:
            if not sharepoint.delete_by_web_url(url, token):
                errors.append("delete skipped: " + str(url)[:80])
        except Exception as exc:
            errors.append("delete: " + str(exc)[:100])


def _reconcile_decks(doc, payload, errors):
    """Keep what the user kept, append what the browser uploaded, delete the rest."""
    added = [
        d.get("web_url") or d.get("webUrl")
        for d in (payload.get("deck_urls") or [])
        if isinstance(d, dict)
    ]
    added = [u for u in added if u]
    current = _current_urls(doc)

    keep = payload.get("keep_slide_urls")
    if keep is None:
        kept = current
    else:
        keep_set = set(keep)
        kept = [u for u in current if u in keep_set]
        removed = [u for u in current if u not in keep_set]
        if removed:
            _delete_removed(removed, errors)

    doc.slide_deck = "\n".join(kept + added)
    # Any change to the deck set invalidates the cached Gemini URIs; clearing
    # them lets auto_retrigger_missing_ai regenerate cleanly instead of scoring
    # a file that is no longer attached.
    if added or kept != current:
        doc.gemini_file_uris = "[]"
    return len(added)


def submit(payload):
    week_label = (payload.get("week_label") or "").strip()
    employee = (payload.get("employee") or "").strip()
    if not week_label or not employee:
        raise SubmitError("Missing week_label or employee")

    errors = []
    doc = _get_or_create(payload, employee, week_label)
    _apply_fields(doc, payload)
    deck_count = _reconcile_decks(doc, payload, errors)
    doc.save(ignore_permissions=True)

    return {
        "success": True,
        "name": doc.name,
        "deck_count": deck_count,
        "errors": errors,
    }
