# Copyright (c) 2026, eCentric and contributors
"""Seed the eContract transition metadata so the signing call can NAME the next handler.

Captured from the provider's own portal on 2026-08-27 (browser network log, not guessed):

    POST https://api-econtract.scts.com.vn/api/Workflow/transition
    { instanceId, userId, toUsers:[<next handler>], transitionId:"-2",
      transitionName:"Trình ký", processAction:"WfFunctionRunSignedOther",
      signType:"ky-tham-gia", signatureInfo:{id,name}, comment }

`toUsers` is the field our API path never sent, which is why eContract broadcast every
submission to the whole role pool - and why somebody outside the approval chain was able to
sign EC-PAYR-2026-00026 forty seconds after it was submitted.

Both observed stages are seeded. They differ ONLY in the transition id/name:

    requester submission -> transitionId "-2", "Trình ký"
    approval             -> transitionId "-9", "Phê duyệt"

Per the operator who captured them, eContract asks for an explicit recipient on those two
steps only; from the step after that it assigns the next signer itself. Handing over still
requires the next person to have a VERIFIED provider mapping - when they do not, the leg
falls back to the pool-wide call and records `HandoverPoolFallback` with the reason, so the
remaining gap stays visible instead of silently reopening the hole.

Idempotent: the row is matched on (parent, action, stage) and updated in place.
"""
import frappe

PROFILE_CODE = "PAYMENT-REQUEST-SCTS-UAT"
CHILD = "EC Digital Signature Profile Transition"

_NOTE = "Captured from the eContract portal 2026-08-27. Do not edit without a new capture."

STAGES = [
    {"action": "Sign", "stage": "requester", "transition_id": -2,
     "transition_name": "Trình ký", "process_action": "WfFunctionRunSignedOther",
     "sign_type": "ky-tham-gia", "terminal": 0, "notes": _NOTE},
    {"action": "Sign", "stage": "approval", "transition_id": -9,
     "transition_name": "Phê duyệt", "process_action": "WfFunctionRunSignedOther",
     "sign_type": "ky-tham-gia", "terminal": 0, "notes": _NOTE},
]


def execute():
    # has_column() takes the DOCTYPE name (it prefixes "tab" itself). The first version of
    # this guard passed a mangled table name, so BOTH probes were false and the patch
    # returned silently having done nothing - a patch that no-ops without saying so is worse
    # than one that fails. Fail loud instead: if the column is genuinely missing the next
    # migrate (after model sync) will run this patch again.
    if not frappe.db.has_column(CHILD, "process_action"):
        frappe.logger().info("p088: %s.process_action not synced yet, will retry next migrate"
                             % CHILD)
        raise frappe.ValidationError(
            "p088: column %s.process_action missing - run model sync first" % CHILD)
    if not frappe.db.exists("EC Digital Signature Profile", PROFILE_CODE):
        frappe.logger().info("p088: profile %s absent, nothing to seed" % PROFILE_CODE)
        return

    profile = frappe.get_doc("EC Digital Signature Profile", PROFILE_CODE)
    for spec in STAGES:
        row = None
        for r in (profile.transitions or []):
            if r.action == spec["action"] and (r.stage or "") == spec["stage"]:
                row = r
                break
        if row is None:
            row = profile.append("transitions", {})
        for key, value in spec.items():
            setattr(row, key, value)
    profile.save(ignore_permissions=True)
    frappe.logger().info("p088: seeded %d eContract transitions for %s"
                         % (len(STAGES), PROFILE_CODE))
