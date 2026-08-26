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

Only the REQUESTER stage is seeded here: those values are the ones actually observed. The
approval stage uses a different transition id / action code which has not been captured yet;
until it is, approval legs keep the old pool-wide call and each one records a
`HandoverPoolFallback` event naming the reason, so the remaining gap stays visible.

Idempotent: the row is matched on (parent, action, stage) and updated in place.
"""
import frappe

PROFILE_CODE = "PAYMENT-REQUEST-SCTS-UAT"
CHILD = "EC Digital Signature Profile Transition"

REQUESTER_STAGE = {
    "action": "Sign",
    "stage": "requester",
    "transition_id": -2,
    "transition_name": "Trình ký",
    "process_action": "WfFunctionRunSignedOther",
    "sign_type": "ky-tham-gia",
    "terminal": 0,
    "notes": "Captured from the eContract portal 2026-08-27. Do not edit without a new capture.",
}


def execute():
    if not frappe.db.has_column(CHILD.replace(" ", "").lower(), "process_action") \
            and not frappe.db.has_column("tab" + CHILD, "process_action"):
        # schema not synced yet on a partial migrate; the next run will pick it up
        return
    if not frappe.db.exists("EC Digital Signature Profile", PROFILE_CODE):
        frappe.logger().info("p088: profile %s absent, nothing to seed" % PROFILE_CODE)
        return

    profile = frappe.get_doc("EC Digital Signature Profile", PROFILE_CODE)
    row = None
    for r in (profile.transitions or []):
        if r.action == REQUESTER_STAGE["action"] and (r.stage or "") == REQUESTER_STAGE["stage"]:
            row = r
            break
    if row is None:
        row = profile.append("transitions", {})
    for key, value in REQUESTER_STAGE.items():
        setattr(row, key, value)
    profile.save(ignore_permissions=True)
    frappe.logger().info("p088: seeded eContract requester transition for %s" % PROFILE_CODE)
