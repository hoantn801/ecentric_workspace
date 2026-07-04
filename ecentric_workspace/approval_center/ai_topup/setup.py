# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for AI_TOPUP-V1 (Draft) + shared
business calendar + SLA policies. User identities are INPUT arguments, never
hardcoded in engine logic. dry_run by default; explicit apply required.
Leaves the process Draft and the catalog card inactive."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

CALENDAR_CODE = "EC_STANDARD_9_18"
PROCESS_CODE = "AI_TOPUP-V1"
APPROVAL_TYPE = "AI_TOPUP"
POLICIES = {  # policy_code -> label
    "AI_TOPUP_MANAGER_3H": "AI Topup Manager 3h",
    "AI_TOPUP_OPERATION_REVIEW_3H": "AI Topup Operation Review 3h",
    "AI_TOPUP_FINANCE_REVIEW_3H": "AI Topup Finance Review 3h",
    "AI_TOPUP_FULFILLMENT_3H": "AI Topup Fulfillment 3h",
}
_WEEK = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run AI Topup setup."), frappe.PermissionError)


def _parse(v):
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))  # de-dup, keep order


def _validate_users(label, users, rep):
    if not users:
        rep["errors"].append("No %s users supplied." % label)
    for u in users:
        try:
            require_active_system_user(u, label)
        except Exception as e:
            rep["errors"].append("%s: %s" % (label, str(e)))


def _calendar_rows():
    rows = []
    for d in _WEEK:
        rows.append({"weekday": d, "start_time": "09:00:00", "end_time": "12:00:00"})
        rows.append({"weekday": d, "start_time": "13:00:00", "end_time": "18:00:00"})
    return rows


# --------------------------------------------------------------------------- #
@frappe.whitelist()
def setup_ai_topup_v1(operation_approvers=None, operation_fulfillers=None, finance_approvers=None,
                      holiday_list=None, dry_run=1, apply=0):
    _require_sm()
    dry = bool(int(dry_run)) and not bool(int(apply))
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [], "result": None}
    op, ff, fin = _parse(operation_approvers), _parse(operation_fulfillers), _parse(finance_approvers)
    _validate_users("Operation Approver", op, rep)
    _validate_users("Operation Fulfiller", ff, rep)
    _validate_users("Finance Approver", fin, rep)
    if holiday_list and not frappe.db.exists("Holiday List", holiday_list):
        rep["errors"].append("Holiday List override '%s' not found." % holiday_list)

    active = frappe.get_all("EC Approval Process",
                            filters={"approval_type": APPROVAL_TYPE, "status": "Active"}, pluck="name")
    if active:
        rep["warnings"].append("An Active process already exists for %s: %s (will NOT be overwritten)."
                               % (APPROVAL_TYPE, active))
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["errors"].append("%s is Active; setup refuses to overwrite an Active process." % PROCESS_CODE)

    rep["planned"] = [
        "calendar %s (Mon-Fri 09-12,13-18)" % CALENDAR_CODE,
        "SLA policies: %s (3h, business hours)" % ", ".join(POLICIES),
        "process %s (Draft) fulfillment=%s" % (PROCESS_CODE, "AI_TOPUP_FULFILLMENT_3H"),
        "L1 Direct Manager (Requester Manager, Any One)",
        "L2 Operation Review (Any One) approvers=%s" % op,
        "L3 Finance Review (Any One) approvers=%s" % fin,
        "process Fulfillers=%s" % ff,
    ]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep

    _upsert_calendar()
    _upsert_policies(holiday_list)
    _upsert_process(op, ff, fin)
    frappe.db.commit()
    rep["result"] = "APPLIED (process left Draft; card inactive)"
    return rep


def _upsert_calendar():
    if frappe.db.exists("EC Approval Business Calendar", CALENDAR_CODE):
        cal = frappe.get_doc("EC Approval Business Calendar", CALENDAR_CODE)
    else:
        cal = frappe.new_doc("EC Approval Business Calendar")
        cal.calendar_code = CALENDAR_CODE
    cal.calendar_name = "eCentric Standard Working Calendar"
    cal.active = 1
    cal.set("working_periods", [])
    for r in _calendar_rows():
        cal.append("working_periods", r)
    cal.save(ignore_permissions=True)


def _upsert_policies(holiday_list):
    for code, label in POLICIES.items():
        pol = frappe.get_doc("EC Approval SLA Policy", code) if frappe.db.exists(
            "EC Approval SLA Policy", code) else frappe.new_doc("EC Approval SLA Policy")
        if not pol.policy_code:
            pol.policy_code = code
        pol.policy_name = label
        pol.duration_hours = 3
        pol.use_business_hours = 1
        pol.business_calendar = CALENDAR_CODE
        pol.holiday_list = holiday_list or None
        pol.active = 1
        pol.save(ignore_permissions=True)


def _set_participants(doc, purpose, source_type, users=None):
    """Idempotent: replace this purpose's rows with exactly the configured set."""
    keep = [p for p in doc.participants if p.participant_purpose != purpose]
    doc.set("participants", keep)
    if source_type == "Requester Manager":
        doc.append("participants", {"participant_purpose": purpose, "source_type": "Requester Manager"})
    else:
        for i, u in enumerate(users or []):
            doc.append("participants", {"participant_purpose": purpose, "source_type": "User",
                                        "user": u, "sort_order": i})


def _upsert_process(op, ff, fin):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "AI Topup V1"
    proc.approval_type = APPROVAL_TYPE
    proc.status = "Draft"                       # never Active in B2
    proc.fulfillment_sla_policy = "AI_TOPUP_FULFILLMENT_3H"
    _set_participants(proc, "Fulfiller", "User", ff)
    proc.save(ignore_permissions=True)

    levels = [(1, "Direct Manager", "AI_TOPUP_MANAGER_3H", "Requester Manager", None, 0),
              (2, "Operation Review", "AI_TOPUP_OPERATION_REVIEW_3H", "User", op, 0),
              (3, "Finance Review", "AI_TOPUP_FINANCE_REVIEW_3H", "User", fin, 1)]  # Finance may adjust amount
    for no, name, sla, src, users, adj in levels:
        existing = frappe.get_all("EC Approval Level",
                                  filters={"approval_process": PROCESS_CODE, "level_no": no}, pluck="name")
        lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
        lvl.approval_process = PROCESS_CODE
        lvl.level_no = no
        lvl.level_name = name
        lvl.mandatory = 1
        lvl.approval_mode = "Any One"
        lvl.sla_policy = sla
        lvl.allows_amount_adjustment = adj
        _set_participants(lvl, "Approver", src, users)
        lvl.save(ignore_permissions=True)


# --------------------------------------------------------------------------- #
@frappe.whitelist()
def validate_ai_topup_v1():
    """Readiness report; NEVER activates."""
    _require_sm()
    checks, ok = [], True

    def c(cond, msg):
        nonlocal ok
        checks.append(("PASS" if cond else "FAIL", msg))
        ok = ok and bool(cond)

    exists = frappe.db.exists("EC Approval Process", PROCESS_CODE)
    c(exists, "process %s exists" % PROCESS_CODE)
    if exists:
        c(frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Draft",
          "process is Draft")
    c(not frappe.get_all("EC Approval Process",
                         filters={"approval_type": APPROVAL_TYPE, "status": "Active"}),
      "no Active process conflict for %s" % APPROVAL_TYPE)
    levels = frappe.get_all("EC Approval Level", filters={"approval_process": PROCESS_CODE},
                            fields=["name", "level_no", "level_name", "approval_mode", "mandatory", "sla_policy"],
                            order_by="level_no asc")
    c([l.level_no for l in levels] == [1, 2, 3], "levels 1,2,3 present in order")
    for l in levels:
        c(l.approval_mode == "Any One", "level %s mode Any One" % l.level_no)
        c(l.mandatory == 1, "level %s mandatory" % l.level_no)
        c(bool(l.sla_policy) and frappe.db.get_value("EC Approval SLA Policy", l.sla_policy, "active"),
          "level %s SLA active" % l.level_no)
        parts = frappe.get_all("EC Approval Participant",
                               filters={"parent": l.name, "participant_purpose": "Approver"},
                               fields=["source_type", "user"])
        if l.level_no == 1:
            c(any(p.source_type == "Requester Manager" for p in parts), "L1 source Requester Manager")
        else:
            users = [p.user for p in parts if p.source_type == "User"]
            c(len(users) == len(set(users)) and users, "level %s no duplicate approvers" % l.level_no)
            for u in users:
                c(_active_su(u), "level %s approver %s active System User" % (l.level_no, u))
    for code in POLICIES:
        c(frappe.db.get_value("EC Approval SLA Policy", code, "active"), "SLA %s active" % code)
    c(frappe.db.get_value("EC Approval Business Calendar", CALENDAR_CODE, "active"),
      "calendar %s active" % CALENDAR_CODE)
    fulfillers = frappe.get_all("EC Approval Participant",
                                filters={"parent": PROCESS_CODE, "parenttype": "EC Approval Process",
                                         "participant_purpose": "Fulfiller"}, fields=["user"])
    c(bool(fulfillers), "at least one Fulfiller")
    for f in fulfillers:
        c(_active_su(f.user), "fulfiller %s active System User" % f.user)
    return {"ready_for_activation": ok, "checks": checks}


def _active_su(user):
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")
