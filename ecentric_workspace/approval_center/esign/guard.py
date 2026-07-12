# Copyright (c) 2026, eCentric and contributors
"""Signing-required approve guard - the server-side bypass control.

SECURITY MODEL (user directives 2026-07-11):
  1. NO ROLE BYPASS. When the active approval level requires digital signature,
     the normal approve path AND the admin override fail closed for every role.
     Approval may complete only through the governed verified-signature path.
     No break-glass override exists in S2A.
  2. frappe.flags IS ONLY A CALL MARKER. The flag carries the candidate
     EC Digital Signature Request name set in-process by the orchestrator
     (HTTP arguments cannot populate frappe.flags). Authorization NEVER rests
     on the flag: every completion is validated against PERSISTED rows -
     request, runtime level, approver row, business document, package
     version+hash, provider-verified signature, idempotency/likeness - under a
     row lock, at the moment engine.approve() runs.

Fail-closed: any lookup miss, mismatch, or error blocks the approval.
Types without an enabled signing profile: one indexed query, behavior unchanged.
"""
import frappe
from frappe import _

FLAG_KEY = "ec_esign_completion_dsr"

_MSG_SIGN_REQUIRED = "Cấp duyệt này yêu cầu ký số. Vui lòng dùng chức năng 'Duyệt & Ký'."


def _gates_open(provider, environment):
    s = frappe.db.get_value("EC Digital Signature Provider Settings",
                            {"provider": provider, "environment": environment},
                            ["integration_enabled", "allow_signing", "allow_production_signing"],
                            as_dict=True)
    if not s or not s.integration_enabled or not s.allow_signing:
        return False
    if environment == "Production" and not s.allow_production_signing:
        return False
    return True


def get_active_profile(reference_doctype, approval_type):
    """Enabled profile whose provider gates are open, or None. None => signing layer
    inert for this type (existing behavior, bit-identical)."""
    rows = frappe.get_all("EC Digital Signature Profile",
                          filters={"business_doctype": reference_doctype,
                                   "approval_type": approval_type, "enabled": 1},
                          fields=["name", "provider", "environment"], limit_page_length=5)
    for r in rows:
        if _gates_open(r.provider, r.environment):
            return r.name
    return None


def level_requires_signature(reference_doctype, approval_type, level_no):
    """True only when an enabled+gated profile marks this level requires_signature."""
    profile = get_active_profile(reference_doctype, approval_type)
    if not profile:
        return False
    return bool(frappe.db.exists("EC Digital Signature Profile Level",
                                 {"parent": profile, "level_no": level_no,
                                  "requires_signature": 1}))


def _deny(reason_code):
    frappe.throw(_(_MSG_SIGN_REQUIRED) + " [%s]" % reason_code, frappe.PermissionError)


def validate_completion(dsr_name, req, level_no, actor):
    """Persisted-DB validation of a verified signing request. Every check reads the
    database; the in-process flag only NAMES the candidate row. Throws on the first
    failure with a short reason code (safe to surface)."""
    if not dsr_name:
        _deny("no_completion_marker")

    # Freshness + concurrency: lock the DSR row for this transaction, then read.
    frappe.db.get_value("EC Digital Signature Request", dsr_name, "name", for_update=True)
    dsr = frappe.db.get_value(
        "EC Digital Signature Request", dsr_name,
        ["name", "approval_request", "request_level", "approver_row", "approver", "action",
         "status", "package", "package_version", "package_hash", "verified_at"],
        as_dict=True)
    if not dsr:
        _deny("dsr_missing")
    if dsr.action != "Sign":
        _deny("dsr_wrong_action")
    if dsr.status != "Signed":
        # Also covers 'completion already occurred' (status would be Approval Completed)
        _deny("dsr_not_in_signed_state:%s" % dsr.status)
    if not dsr.verified_at:
        _deny("dsr_not_verified")
    if dsr.approval_request != req.name:
        _deny("approval_request_mismatch")
    if dsr.approver != actor:
        _deny("actor_mismatch")

    # Runtime level match (persisted snapshot, not caller-supplied).
    rl = frappe.db.get_value("EC Approval Request Level", dsr.request_level,
                             ["level_no", "approval_request", "level_status"], as_dict=True)
    if not rl or rl.approval_request != req.name:
        _deny("request_level_mismatch")
    if rl.level_no != level_no or req.current_level != level_no:
        _deny("level_no_mismatch")

    # Current approver row still pending (also proves the level is not completed).
    ar = frappe.db.get_value("EC Approval Request Approver", dsr.approver_row,
                             ["approver", "level_no", "status", "approval_request"], as_dict=True)
    if not ar or ar.approval_request != req.name or ar.approver != actor:
        _deny("approver_row_mismatch")
    if ar.level_no != level_no:
        _deny("approver_row_level_mismatch")
    if ar.status != "Pending":
        _deny("approver_row_not_pending:%s" % ar.status)

    if req.approval_status != "Pending":
        _deny("request_not_pending:%s" % req.approval_status)

    # Package: business document + version + hash + not superseded/cancelled.
    pkg = frappe.db.get_value(
        "EC Digital Signature Package", dsr.package,
        ["approval_request", "business_doctype", "business_name", "status",
         "package_version", "package_hash"], as_dict=True)
    if not pkg or pkg.approval_request != req.name:
        _deny("package_mismatch")
    if pkg.status != "Active":
        _deny("package_not_active:%s" % pkg.status)
    if pkg.business_doctype != req.reference_doctype or pkg.business_name != req.reference_name:
        _deny("business_document_mismatch")
    if not pkg.package_hash or dsr.package_hash != pkg.package_hash:
        _deny("package_hash_mismatch")
    if int(dsr.package_version or 0) != int(pkg.package_version or -1):
        _deny("package_version_mismatch")

    # Idempotency/concurrency still hold: no OTHER completion for this level.
    other = frappe.db.exists("EC Digital Signature Request",
                             {"approval_request": req.name, "request_level": dsr.request_level,
                              "status": "Approval Completed", "name": ["!=", dsr.name]})
    if other:
        _deny("level_already_completed_by:%s" % other)
    return True


def assert_level_completable(req, level_no, actor):
    """Called from engine.service.approve() AND admin_override_current_level() for every
    request. No-op unless the active level requires signature under an enabled+gated
    profile; then the persisted verified-signature completion is mandatory - for
    EVERY role, with NO override."""
    if not level_requires_signature(req.reference_doctype, req.approval_type, level_no):
        return
    dsr_name = getattr(frappe.flags, FLAG_KEY, None)  # call marker ONLY (see module docstring)
    validate_completion(dsr_name, req, level_no, actor)
