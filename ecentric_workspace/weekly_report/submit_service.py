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

from ecentric_workspace.weekly_report import sharepoint, week_calendar


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


def _apply_obligation_fields(doc, employee, week_label):
    """Give a self-created row the same deadline the generator would have set.

    THE BUG THIS FIXES (found 2026-09-17, 211 rows): there are two ways a
    Weekly Team Update comes into existence --

      service.ensure_weekly_obligation  daily 00:00 generator, always sets due_at
      submit_service._get_or_create     this file, when the row does not exist yet

    Anyone submitting BEFORE the generator has run for their week went down the
    second path, and this function did not exist: the row was born with no
    deadline, _apply_fields() set status = Submitted immediately, and from then
    on the generator skipped it forever (`status in TERMINAL_STATES`). So the
    deadline could never be filled in later. Weekly reports now feed SLA, and a
    row with no deadline cannot be measured -- which meant submitting EARLY got
    you left out of the numbers. Exactly backwards.

    Department comes from the EMPLOYEE record, not the payload: compute_due_at()
    needs the Department record name (DRW.name == Department.name), while
    payload["department"] is a browser-supplied display string. The generator
    reads Employee.department too -- same source, same answer.

    obligation_key is set so the canonical lookup in service.py finds this row
    instead of falling through to the legacy branch. generated_obligation stays
    0 on purpose: the generator did NOT create this row, and setting the flag
    would record something untrue.

    A missing or disabled DRW must NOT block the person from submitting. It is a
    configuration gap owned by HR, and turning it into "you cannot file your
    report" would trade a measurement bug for an outage. Leave due_at empty and
    log; sla/weekly_source already surfaces no-deadline rows in its `khong_han`
    bucket (fix ea008665), and due_backfill.py can fill them once the DRW exists.
    """
    doc.obligation_key = str(employee) + "::" + str(week_label)
    department = frappe.db.get_value("Employee", employee, "department")
    try:
        doc.due_at = week_calendar.due_at_for_label(week_label, department)
    except (week_calendar.MissingReportingWindowError, ValueError) as exc:
        frappe.log_error(
            "wr.submit_no_due employee=" + str(employee)
            + " week=" + str(week_label)
            + " dept=" + str(department)
            + " err=" + str(exc)[:200],
            "wr.submit_no_due",
        )


def _get_or_create(payload, employee, week_label):
    # Existence MUST be keyed by (employee, week) because the docname is built
    # from employee -- keying it on submitter caused the 1062 duplicate
    # collisions fixed 2026-08-24.
    name = frappe.db.get_value(
        WTU, {"employee": employee, "week_label": week_label}, "name"
    )
    if name:
        # Deliberately NOT repairing due_at on an existing row here. Re-opening
        # and re-submitting an old report would otherwise hand it a deadline it
        # never had, and could mark someone late for a week that is already
        # closed. Historical rows are the backfill's job, where the decision is
        # explicit and reviewable -- see due_backfill.py.
        return frappe.get_doc(WTU, name)
    doc = frappe.new_doc(WTU)
    doc.week_label = week_label
    doc.employee = employee
    doc.submitter = payload.get("submitter") or frappe.session.user
    emp_code = frappe.db.get_value("Employee", employee, "employee_number")
    if emp_code:
        doc.name = "WTU-{0}-{1}-{2}".format(
            week_label, emp_code, sharepoint.dept_clean(payload.get("department"))
        )
        doc.flags.name_set = True
    _apply_obligation_fields(doc, employee, week_label)
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


def _delete_removed(removed, errors, department):
    # department is required for Office decks: their webUrl is the _layouts
    # viewer form, which carries no folder. Without it the path cannot be
    # rebuilt and the file would silently survive removal.
    try:
        token = sharepoint.get_app_token()
    except Exception as exc:
        errors.append("token: " + str(exc)[:100])
        return
    for url in removed:
        try:
            if not sharepoint.delete_by_web_url(url, token, department):
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
            _delete_removed(removed, errors, payload.get("department"))

    doc.slide_deck = "\n".join(kept + added)
    # Any change to the deck set invalidates the cached Gemini URIs: scoring a
    # file that is no longer attached is worse than not scoring yet.
    #
    # CONTRACT: "[]" means "needs regeneration", and auto_retrigger_missing_ai
    # is the thing that regenerates it. That cron used to EXCLUDE
    # gemini_file_uris = '[]' from its WHERE clause, which meant every report
    # submitted through here between 14/09 and 15/09 was silently unscorable --
    # the comment that used to sit on this line asserted the opposite without
    # anyone having read the cron's SQL. Do not narrow that filter again.
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

    # A report with no document cannot be reviewed or scored. The Server Script
    # this replaces collected upload failures into a list and saved anyway, so
    # two reports (W36, W37) sat marked Submitted with nothing attached and
    # nobody noticed until someone opened one. Refuse rather than persist a
    # hollow record -- and refuse BEFORE save, so nothing is written.
    if not (doc.slide_deck or "").strip():
        raise SubmitError(
            "Báo cáo phải có ít nhất một file slide. Vui lòng đính kèm rồi gửi lại."
        )

    doc.save(ignore_permissions=True)

    return {
        "success": True,
        "name": doc.name,
        "deck_count": deck_count,
        "errors": errors,
    }
