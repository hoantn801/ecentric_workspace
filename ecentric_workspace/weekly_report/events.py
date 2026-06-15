# Copyright (c) 2026, eCentric and contributors
"""WR1A doc_events handlers.

Registered in hooks.py:
  doc_events = {
      "Weekly Team Update": {"on_update":
          "ecentric_workspace.weekly_report.events.on_weekly_update"},
      "ToDo": {"validate":
          "ecentric_workspace.weekly_report.events.validate_weekly_report_todo"},
  }

on_weekly_update: when WTU.status transitions to Submitted, close all bound
                  obligation ToDos via service.close_weekly_obligation.

validate_weekly_report_todo: scoped guard. Block manual Closed/Cancelled
                  transition for ToDos referencing a generated WR obligation
                  while the WTU is still Draft. Approval ToDos, legacy/manual
                  WR ToDos, and other reference_types are NOT touched.
"""

import frappe


WTU = "Weekly Team Update"


def on_weekly_update(doc, method=None):
    """Close obligation ToDos when WTU.status flips to Submitted.

    The service raises on error; we let it bubble so the surrounding save
    transaction rolls back. We never end up with WTU=Submitted + ToDo=Open.
    """
    if doc.doctype != WTU:
        return
    if doc.status != "Submitted":
        return
    before = doc.get_doc_before_save()
    if before is not None and getattr(before, "status", None) == "Submitted":
        return  # already submitted previously; idempotent no-op
    # Lazy import to avoid circular reference during Frappe app boot.
    from ecentric_workspace.weekly_report import service
    service.close_weekly_obligation(doc.name)


def validate_weekly_report_todo(doc, method=None):
    """Guard: block manual Close/Cancel of generated WR obligation ToDo
    while the WTU is still Draft.

    Scope:
      * reference_type must be Weekly Team Update.
      * referenced WTU.generated_obligation must be 1 (skip legacy / manual).
      * transition must be Open -> Closed/Cancelled (skip create/no-change/other).
      * WTU.status must not yet be Submitted -> throw.

    Service close (close_weekly_obligation) runs AFTER on_weekly_update has
    confirmed WTU.status=="Submitted"; by the time the ToDo.save inside the
    service hits this guard, WTU.status is already Submitted in DB and we let
    the close through.
    """
    if doc.doctype != "ToDo":
        return
    if doc.reference_type != WTU:
        return
    new_status = doc.status
    if new_status not in ("Closed", "Cancelled"):
        return
    before = doc.get_doc_before_save()
    if before is None:
        # Brand new ToDo being inserted with Closed/Cancelled - not our case.
        return
    old_status = getattr(before, "status", None)
    if old_status == new_status:
        return
    if old_status != "Open":
        return  # only block Open -> Closed/Cancelled transitions

    wtu = frappe.db.get_value(
        WTU, doc.reference_name,
        ["status", "generated_obligation"], as_dict=True,
    )
    if not wtu:
        # Dangling reference; not our concern.
        return
    if not wtu.get("generated_obligation"):
        # Legacy / manual WR ToDo not produced by our scheduler.
        return
    if wtu.get("status") == "Submitted":
        return  # allowed (this is exactly the service close path)

    frappe.throw(
        "Khong the dong/huy ToDo bao cao tuan khi bao cao chua Submitted. "
        "Mo /weekly-update?week=... va nop bao cao truoc.",
        frappe.PermissionError,
    )
