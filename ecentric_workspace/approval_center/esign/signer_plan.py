# Copyright (c) 2026, eCentric and contributors
"""Read-only SIGNER PLAN resolver (Phase B1) - shared e-sign infrastructure, NOT Payment
Request specific. Composes the governed Approval Engine (process / level / participant
resolution and the frozen request snapshot) with the Digital Signature Profile signing policy
to produce a stable, UI-ready read model of the required signing SLOTS.

Guarantees: NO schema change, NO writes, NO Approval Request creation, NO package / placement /
DSR / ToDo mutation, NO workflow transition, NO SCTS / provider call. Repeated calls are
side-effect free.

  source = "frozen"  when an EC Approval Request exists (the frozen runtime snapshot WINS);
  source = "preview" otherwise (resolved from the Active process configuration).

Slot keys are deterministic, label-independent (never translated text, never random) and stable
across repeated calls and across preview<->frozen when the approval process has not changed,
because they are built from level_no (identical in EC Approval Level and EC Approval Request
Level) plus a sorted index - never from a UI label or a UUID.
"""
import frappe

from ecentric_workspace.approval_center.engine import service as engine
from ecentric_workspace.approval_center.esign import guard
from ecentric_workspace.approval_center.esign import permissions as perms

AR = "EC Approval Request"
ARL = "EC Approval Request Level"
ARA = "EC Approval Request Approver"
PROFILE = "EC Digital Signature Profile"

# Slot-key contract version. Bump when the slot_key format changes so Phase C can tell which
# contract produced a historical persisted signer_slot_key.
SLOT_KEY_VERSION = 1


# --------------------------------------------------------------------------- #
# read-model builders (pure of side effects)
# --------------------------------------------------------------------------- #
def _candidate(user, environment):
    """A business signer candidate + SCTS-mapping READINESS metadata. Business signer
    resolution and provider readiness are separate concerns: a missing/unverified mapping is
    reported, never a reason to drop the signer. NO provider API call."""
    dn = frappe.db.get_value("User", user, "full_name") or user
    mapped = perms.verified_mapping(user, environment) if environment else None
    return {"user": user, "display_name": dn,
            "scts_mapping_status": "verified" if mapped else "missing"}


def _level_signs(profile, policy, level_no, final_level):
    """Gate-INDEPENDENT mirror of guard.level_requires_signature (which uses the gate-DEPENDENT
    active profile): identical 4-branch policy, resolved from the ENABLED profile so it holds
    while provider write gates are OFF. Reuses guard._approver_signature_policy for the policy
    value - it does NOT define a second signature-policy model."""
    if policy == "None":
        return False
    if policy == "All Approval Levels":
        return True
    if policy == "Final Approval Level Only":
        return final_level is not None and int(level_no) == int(final_level)
    # Selected Approval Levels (default / backward-compatible): per-level Signing Levels row.
    return bool(frappe.db.exists("EC Digital Signature Profile Level",
                                 {"parent": profile, "level_no": level_no,
                                  "requires_signature": 1}))


def _level_slots(level_no, level_name, level_ref, legacy, mode, minimum_approvals, users,
                 environment):
    """Required signer slots for ONE signing level. Slot identity is the STABLE governed level
    identity (`level_ref` = EC Approval Level.name in preview / EC Approval Request Level.
    source_process_level when frozen), NOT level_no (which is response metadata only):
      * Any One       -> ONE pooled slot   -> level:<ref>:any-one
      * All Required  -> one USER-BOUND slot per approver -> level:<ref>:user:<canonical_user>
                         (survives process evolution: an unchanged approver keeps its key)
      * Minimum Count -> `minimum_approvals` POOLED ordinal slots -> level:<ref>:minimum:<n>
                         (1-based; never bound to a user - the satisfying subset is unknown
                         until runtime).
    Unknown/blank mode is treated as All Required (the safe superset). When the frozen level has
    no source_process_level (legacy rows), `level_ref` is None and the identity token is the
    clearly-marked non-misleading `legacy-L<level_no>`; the slot also carries legacy=True."""
    pool = [_candidate(u, environment) for u in sorted(set(users))]
    tok = level_ref if level_ref else ("legacy-L%s" % level_no)
    base = {"kind": "approval_level", "level_no": level_no, "level_name": level_name,
            "level_ref": level_ref, "approval_mode": mode, "required": True}
    if legacy:
        base["legacy"] = True
    if mode == "Any One":
        return [dict(base, slot_key="level:%s:any-one" % tok, candidates=pool)]
    if mode == "Minimum Count":
        k = int(minimum_approvals or 0)
        return [dict(base, slot_key="level:%s:minimum:%d" % (tok, i), candidates=pool)
                for i in range(1, k + 1)]
    # All Required (and any unknown mode): one user-bound slot per resolved approver.
    return [dict(base, slot_key="level:%s:user:%s" % (tok, c["user"]), candidates=[c])
            for c in pool]


def _requester_slot(requester, environment):
    return {"slot_key": "requester", "kind": "requester", "level_no": None, "level_name": None,
            "level_ref": None, "approval_mode": None, "required": True,
            "candidates": [_candidate(requester, environment)] if requester else []}


def _unresolved(bd, bn, reason, source=None, approval_type=None):
    return {"business_doctype": bd, "business_name": bn, "resolved": False, "reason": reason,
            "source": source, "slot_key_version": SLOT_KEY_VERSION,
            "process": {"approval_type": approval_type, "process": None, "environment": None},
            "summary": {"required_slots": 0}, "slots": []}


# --------------------------------------------------------------------------- #
# type / profile / policy resolution
# --------------------------------------------------------------------------- #
def _profile_env_policy(profile):
    env = frappe.db.get_value(PROFILE, profile, "environment")
    policy = guard._approver_signature_policy(profile)
    req_sig = bool(frappe.db.get_value(PROFILE, profile, "requester_signature_required"))
    return env, policy, req_sig


def _resolve_type_and_profile(business_doctype, business_name, ar):
    if ar:
        at = frappe.db.get_value(AR, ar, "approval_type")
    else:
        at = frappe.db.get_value(business_doctype, business_name, "approval_type") \
            if frappe.db.has_column(business_doctype, "approval_type") else None
        if not at:
            rows = frappe.get_all(PROFILE,
                                  filters={"business_doctype": business_doctype, "enabled": 1},
                                  fields=["approval_type"], limit_page_length=5)
            if not rows:
                return None, None, "profile_not_configured"
            ats = sorted({r.approval_type for r in rows})
            if len(ats) != 1:
                return None, None, "ambiguous_profile"
            at = ats[0]
    if not at:
        return None, None, "approval_type_missing"
    try:
        profile = guard.get_enabled_profile(business_doctype, at)
    except frappe.ValidationError:
        return at, None, "ambiguous_profile"   # >1 enabled profile for the exact pair
    if not profile:
        return at, None, "profile_not_configured"
    return at, profile, None


# --------------------------------------------------------------------------- #
# public service (permission-safe; NO admin/SM/ignore_permissions bypass; NO writes)
# --------------------------------------------------------------------------- #
def resolve_signer_plan(business_doctype, business_name):
    perms.assert_can_view_business(business_doctype, business_name)   # governed view gate
    ar = perms.business_approval_request(business_doctype, business_name)
    at, profile, err = _resolve_type_and_profile(business_doctype, business_name, ar)
    if err:
        return _unresolved(business_doctype, business_name, err,
                           source=("frozen" if ar else "preview"), approval_type=at)
    environment, policy, req_sig = _profile_env_policy(profile)
    if ar:
        return _frozen_plan(business_doctype, business_name, ar, at, profile,
                            environment, policy, req_sig)
    return _preview_plan(business_doctype, business_name, at, profile,
                         environment, policy, req_sig)


def _frozen_plan(bd, bn, ar, at, profile, environment, policy, req_sig):
    requester = frappe.db.get_value(AR, ar, "requested_by")
    final_level = guard.request_final_level(ar)
    slots = []
    if req_sig:
        slots.append(_requester_slot(requester, environment))
    levels = frappe.get_all(ARL, filters={"approval_request": ar},
                            fields=["level_no", "level_name", "approval_mode", "minimum_approvals",
                                    "source_process_level"],
                            order_by="level_no asc")
    for lvl in levels:
        if not _level_signs(profile, policy, lvl.level_no, final_level):
            continue
        # STABLE level identity = the governed process level (source_process_level). Legacy
        # frozen rows may lack it -> level_ref None + legacy flag (a clearly-marked, non-
        # misleading legacy-L<level_no> token), never a fabricated stable key.
        level_ref = lvl.source_process_level or None
        legacy = not bool(lvl.source_process_level)
        users = frappe.get_all(ARA, filters={"approval_request": ar, "level_no": lvl.level_no},
                               pluck="approver")
        slots += _level_slots(lvl.level_no, lvl.level_name, level_ref, legacy, lvl.approval_mode,
                              lvl.minimum_approvals, users, environment)
    return {"business_doctype": bd, "business_name": bn, "resolved": True, "reason": None,
            "source": "frozen", "slot_key_version": SLOT_KEY_VERSION,
            "process": {"approval_type": at,
                        "process": frappe.db.get_value(AR, ar, "approval_process"),
                        "environment": environment},
            "summary": {"required_slots": len(slots)}, "slots": slots}


def _preview_plan(bd, bn, at, profile, environment, policy, req_sig):
    requester = frappe.db.get_value(bd, bn, "owner")
    try:
        process = engine.resolve_process(at)
        levels = engine.resolve_levels(process.name)
    except frappe.ValidationError:
        return _unresolved(bd, bn, "process_not_resolved", source="preview", approval_type=at)
    if not levels:
        return _unresolved(bd, bn, "process_not_resolved", source="preview", approval_type=at)
    final_level = max(l.level_no for l in levels)
    context = {"reference_doctype": bd, "reference_name": bn}
    slots = []
    if req_sig:
        slots.append(_requester_slot(requester, environment))
    for lvl in levels:
        if not _level_signs(profile, policy, lvl.level_no, final_level):
            continue
        approvers = engine.resolve_participants(
            [p for p in lvl.participants if p.participant_purpose == "Approver"],
            requester, context=context)
        users = [u for (u, _label) in approvers]
        if not users:
            return _unresolved(bd, bn, "approvers_unresolved", source="preview", approval_type=at)
        # preview level identity = the EC Approval Level document (== frozen source_process_level)
        slots += _level_slots(lvl.level_no, lvl.level_name, lvl.name, False, lvl.approval_mode,
                             lvl.minimum_approvals, users, environment)
    return {"business_doctype": bd, "business_name": bn, "resolved": True, "reason": None,
            "source": "preview", "slot_key_version": SLOT_KEY_VERSION,
            "process": {"approval_type": at, "process": process.name, "environment": environment},
            "summary": {"required_slots": len(slots)}, "slots": slots}
