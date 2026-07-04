# Copyright (c) 2026, eCentric and contributors
"""AI Topup orchestration glue over the generic approval engine.
Business-type-specific: requester context, material-change restart, fulfillment
assignment/claim/completion, and EC AI Account upsert after completion."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.engine.user_rules import normalize_email

BUSINESS_DT = "EC AI Topup Request"
APPROVAL_TYPE = "AI_TOPUP"

MATERIAL_FIELDS = ["ai_tool", "account_mode", "ai_account", "account_email", "account_manager",
                   "proposed_account_email", "proposed_account_manager", "requested_amount",
                   "department", "requested_plan", "billing_cycle",
                   "subscription_start_date", "subscription_end_date"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("This request has already been submitted."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("You can only submit your own request."))
    user = doc.requested_by or frappe.session.user
    emp = _requester_context(user)
    doc.requested_by = user
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    if not (doc.request_title or "").strip():
        frappe.throw(_("Request title is required before submitting."))
    if not doc.approved_amount and doc.requested_amount:
        doc.approved_amount = doc.requested_amount   # controlled default (== requested); NOT a Finance adjustment
    doc.request_datetime = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


@frappe.whitelist(methods=["POST"])
def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Not submitted."))
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


@frappe.whitelist(methods=["POST"])
def finance_approve(name, approved_amount=None, comment=None, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    eff = actor or frappe.session.user
    cl = frappe.db.get_value("EC Approval Request", doc.approval_request, "current_level")
    if not engine._actor_pending_row(doc.approval_request, cl, eff):
        frappe.throw(_("You are not a pending approver for the current level."))
    if approved_amount is not None:
        if (doc.requested_amount is not None and float(approved_amount) != float(doc.requested_amount)
                and not (comment or "").strip()):
            frappe.throw(_("A finance comment is mandatory when approved_amount differs from requested_amount."))
        doc.approved_amount = approved_amount
        doc.finance_adjustment_comment = comment
        doc.save(ignore_permissions=True)
        if doc.requested_amount is not None and float(approved_amount) != float(doc.requested_amount):
            engine.log_action(doc.approval_request, "Amount Adjusted", actor or frappe.session.user,
                              comment=_("Approved {0} vs requested {1}. {2}").format(
                                  approved_amount, doc.requested_amount, comment or ""))
    engine.approve(doc.approval_request, actor=actor, comment=comment)


def on_final_approval(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    proc = frappe.get_doc("EC Approval Process", proc_name)
    fulfillers = [u for u, _lbl in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]
    emp = frappe.db.get_value("Employee", {"user_id": doc.requested_by}, ["name", "company"], as_dict=True)
    sla = engine.resolve_sla(proc.fulfillment_sla_policy,
                             employee=emp.name if emp else None,
                             company=(emp.company if emp else None) or doc.company)
    frappe.db.set_value(BUSINESS_DT, name, {
        "fulfillment_status": "Assigned",
        "fulfillment_due_at": sla["due_at"] if sla else None,
        "fulfillment_sla_calendar": sla["calendar"] if sla else None,
        "fulfillment_sla_holiday_list": sla["holiday_list"] if sla else None,
    })
    if fulfillers:
        engine.assign(BUSINESS_DT, name, fulfillers, _("AI Topup fulfillment queue"))
    engine.notify([doc.requested_by] + fulfillers,
                  _("Approved - fulfillment assigned: {0}").format(name), BUSINESS_DT, name)


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(name, user=None):
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("You are not an eligible fulfiller for this request."))
    # Guarded atomic claim (conditional UPDATE) - documented direct SQL: sets owner
    # only if still 'Assigned'; concurrency-safe against simultaneous claims.
    frappe.db.sql(
        """update `tabEC AI Topup Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC AI Topup Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("This request has already been claimed by another fulfiller."))
    engine.close_todos(BUSINESS_DT, name, keep_user=user)
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Started", user, comment=_("Fulfillment claimed"),
                      new_status="In Progress")  # durable audited claim event
    engine.notify([doc.requested_by], _("Fulfillment claimed by {0}: {1}").format(user, name),
                  BUSINESS_DT, name)
    return {"owner": user}


@frappe.whitelist(methods=["POST"])
def complete_fulfillment(name, user=None):
    user = user or frappe.session.user
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Only the claimed owner or a System Manager may complete this request."))
    doc.fulfillment_status = "Completed"
    doc.save(ignore_permissions=True)
    _upsert_account(doc)
    engine.notify([doc.requested_by, doc.confirmed_account_manager, doc.fulfillment_owner],
                  _("AI Topup completed: {0}").format(name), BUSINESS_DT, name)


def _upsert_account(doc):
    if doc.account_mode == "New Account":
        acc = frappe.get_doc({
            "doctype": "EC AI Account", "ai_tool": doc.ai_tool,
            "account_email": normalize_email(doc.actual_account_email or doc.proposed_account_email),
            "account_manager": doc.confirmed_account_manager or doc.proposed_account_manager,
            "status": "Active", "current_plan": doc.actual_plan or doc.requested_plan,
            "billing_cycle": doc.billing_cycle, "company": doc.company,
            "subscription_start_date": doc.subscription_start_date,
            "subscription_end_date": doc.subscription_end_date,
            "latest_topup_request": doc.name, "last_topup_at": now_datetime(),
        }).insert(ignore_permissions=True)
        frappe.db.set_value(BUSINESS_DT, doc.name, "actual_ai_account", acc.name)
    else:
        acc_name = doc.actual_ai_account or doc.ai_account
        if not acc_name:
            return
        acc = frappe.get_doc("EC AI Account", acc_name)
        if doc.actual_plan:
            acc.current_plan = doc.actual_plan
        if doc.subscription_start_date:
            acc.subscription_start_date = doc.subscription_start_date
        if doc.subscription_end_date:
            acc.subscription_end_date = doc.subscription_end_date
        acc.latest_topup_request = doc.name
        acc.last_topup_at = now_datetime()
        if doc.confirmed_account_manager and doc.confirmed_account_manager != acc.account_manager:
            if (acc.manager_change_reason or "").strip():
                acc.account_manager = doc.confirmed_account_manager
        acc.save(ignore_permissions=True)
