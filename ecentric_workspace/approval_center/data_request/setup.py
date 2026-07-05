# Copyright (c) 2026, eCentric and contributors
"""Idempotent, System-Manager-only setup for DATA_REQUEST-V1 (Draft):
Level 1 Data Review (Any One) + process Fulfillers (Data Fulfillment queue).
User identities are INPUT arguments (config seed) - never hardcoded in engine
runtime logic. dry-run by default; apply=1 required. Leaves the process Draft
and the catalog card inactive. No SLA policy configured in v1 (no misleading SLA)."""
import json

import frappe
from frappe import _

from ecentric_workspace.approval_center.engine.user_rules import require_active_system_user

PROCESS_CODE = "DATA_REQUEST-V1"
APPROVAL_TYPE = "DATA_REQUEST"
# Config seed defaults (may be overridden by args). Emails allowed in setup/config only.
DEFAULT_REVIEWERS = ["linh.vuong@ecentric.vn", "hoan.tran@ecentric.vn"]
DEFAULT_FULFILLERS = ["linh.vuong@ecentric.vn", "hoan.tran@ecentric.vn"]


def _require_sm():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may run Data Request setup."), frappe.PermissionError)


def _parse(v, default):
    if v is None:
        return list(default)
    if isinstance(v, str):
        v = json.loads(v) if v.strip().startswith("[") else [x.strip() for x in v.split(",") if x.strip()]
    return list(dict.fromkeys(v or []))


def _validate_users(label, users, rep):
    if not users:
        rep["errors"].append("No %s users supplied." % label)
    for u in users:
        try:
            require_active_system_user(u, label)
        except Exception as e:
            rep["errors"].append("%s: %s" % (label, str(e)))


def _set_participants(doc, purpose, users):
    keep = [p for p in doc.participants if p.participant_purpose != purpose]
    doc.set("participants", keep)
    for i, u in enumerate(users or []):
        doc.append("participants", {"participant_purpose": purpose, "source_type": "User",
                                    "user": u, "sort_order": i})


@frappe.whitelist()
def setup_data_request_v1(review_approvers=None, fulfillers=None, dry_run=1, apply=0):
    _require_sm()
    dry = int(apply or 0) != 1
    rep = {"mode": "dry_run" if dry else "apply", "planned": [], "errors": [], "warnings": [], "result": None}
    rev = _parse(review_approvers, DEFAULT_REVIEWERS)
    ff = _parse(fulfillers, DEFAULT_FULFILLERS)
    _validate_users("Data Review Approver", rev, rep)
    _validate_users("Data Fulfiller", ff, rep)

    if not frappe.db.exists("EC Approval Type", APPROVAL_TYPE):
        rep["errors"].append("EC Approval Type %s missing (run p002 seed first)." % APPROVAL_TYPE)
    if frappe.db.get_value("EC Approval Process", PROCESS_CODE, "status") == "Active":
        rep["errors"].append("%s is Active; setup refuses to overwrite an Active process." % PROCESS_CODE)
    active = frappe.get_all("EC Approval Process",
                            filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                     "name": ["!=", PROCESS_CODE]}, pluck="name")
    if active:
        rep["warnings"].append("Another Active process exists for %s: %s" % (APPROVAL_TYPE, active))

    rep["planned"] = [
        "process %s (Draft), no SLA policy (v1)" % PROCESS_CODE,
        "L1 Data Review (Any One) approvers=%s" % rev,
        "process Fulfillers (Data Fulfillment queue)=%s" % ff,
    ]
    rep["blockers"] = rep["errors"]
    if rep["errors"]:
        rep["result"] = "BLOCKED"
        return rep
    if dry:
        rep["result"] = "DRY_RUN_OK (no writes)"
        return rep

    _upsert_process(rev, ff)
    frappe.db.commit()
    rep["result"] = "APPLIED (process left Draft; card inactive)"
    return rep


def _upsert_process(rev, ff):
    proc = frappe.get_doc("EC Approval Process", PROCESS_CODE) if frappe.db.exists(
        "EC Approval Process", PROCESS_CODE) else frappe.new_doc("EC Approval Process")
    if not proc.process_code:
        proc.process_code = PROCESS_CODE
    proc.title = "Data Request V1"
    proc.approval_type = APPROVAL_TYPE
    proc.version_no = proc.version_no or 1
    proc.status = "Draft"
    proc.fulfillment_sla_policy = None
    _set_participants(proc, "Fulfiller", ff)
    proc.save(ignore_permissions=True)

    existing = frappe.get_all("EC Approval Level",
                              filters={"approval_process": PROCESS_CODE, "level_no": 1}, pluck="name")
    lvl = frappe.get_doc("EC Approval Level", existing[0]) if existing else frappe.new_doc("EC Approval Level")
    lvl.approval_process = PROCESS_CODE
    lvl.level_no = 1
    lvl.level_name = "Data Review"
    lvl.mandatory = 1
    lvl.approval_mode = "Any One"
    lvl.minimum_approvals = 1
    lvl.allows_amount_adjustment = 0
    lvl.sla_policy = None
    _set_participants(lvl, "Approver", rev)
    lvl.save(ignore_permissions=True)


@frappe.whitelist()
def validate_data_request_v1():
    proc = frappe.db.get_value("EC Approval Process", {"process_code": PROCESS_CODE},
                               ["name", "status"], as_dict=True)
    checks = []

    def c(cond, msg):
        checks.append({"check": msg, "ok": bool(cond)})

    c(bool(proc), "process %s exists" % PROCESS_CODE)
    if proc:
        c(proc.status in ("Draft", "Active"), "status is Draft or Active")
        levels = frappe.get_all("EC Approval Level", filters={"approval_process": proc.name},
                                fields=["level_no", "level_name", "approval_mode"], order_by="level_no asc")
        c([l.level_no for l in levels] == [1], "exactly one level (Data Review)")
        c(bool(levels) and levels[0].level_name == "Data Review" and levels[0].approval_mode == "Any One",
          "L1 Data Review Any One")
        for l in frappe.get_all("EC Approval Level", filters={"approval_process": proc.name}, pluck="name"):
            users = frappe.get_all("EC Approval Participant",
                                   filters={"parent": l, "participant_purpose": "Approver"}, pluck="user")
            c(bool(users) and len(users) == len(set(users)), "reviewers present, no duplicates")
            for u in users:
                c(_active(u), "reviewer %s active System User" % u)
        ffs = frappe.get_all("EC Approval Participant",
                             filters={"parent": PROCESS_CODE, "parenttype": "EC Approval Process",
                                      "participant_purpose": "Fulfiller"}, pluck="user")
        c(bool(ffs), "at least one Fulfiller")
        for u in ffs:
            c(_active(u), "fulfiller %s active System User" % u)
        c(not frappe.get_all("EC Approval Process",
                             filters={"approval_type": APPROVAL_TYPE, "status": "Active",
                                      "process_code": ["!=", PROCESS_CODE]}),
          "no OTHER Active process for %s" % APPROVAL_TYPE)
    return {"ok": all(x["ok"] for x in checks), "checks": checks}


def _active(user):
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")
