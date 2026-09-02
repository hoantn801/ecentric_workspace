# Copyright (c) 2026, eCentric and contributors
"""Re-publish 6 approval feature pages so they stop swallowing the server's own message.

Same bug p123 closed on Payment Request, in the six pages p123 explicitly left open:

    affiliate_bonus, budget_setting, employee_info_update,
    livestream_supplies, purchase_request, service_referral

Every one of them read the server error out of `e.message`. Frappe does NOT put a
`frappe.throw` message there: it goes into `_server_messages` (a JSON string containing more
JSON strings), sometimes into `responseJSON.message`, sometimes only into `exception` as
"ValidationError: <noi dung>". So `(e && e.message) || ""` was empty on every business
error, every `if(/.../.test(m))` branch below it tested the empty string and failed, and the
user always got the catch-all sentence:

    "Đã có lỗi. Vui lòng thử lại."

Concretely: submit Purchase Request with no attachment and the server returns the exact
sentence the person needs ("Vui lòng nhập đầy đủ các trường bắt buộc..."), the page has a
branch for it in `applyBackendError`, and the branch had never run once. Same for the
"chưa có Quản lý trực tiếp" branch in `friendlyErr` - the one message that tells someone the
fix is an HR data problem, not their form.

`extractServerMsg` is copied verbatim from ai_topup (correct all along, and the source p123
used), so all eight forms now read the message from one place. Functions rewired per page:

    affiliate_bonus       mapErr, resubmitErr, friendlyErr, applyBackendError
    budget_setting        mapErr, resubmitErr, applyBackendError
    employee_info_update  mapErr
    livestream_supplies   mapErr
    purchase_request      mapErr, resubmitErr, friendlyErr, applyBackendError
    service_referral      mapErr, applyBackendError

(`friendlyErr` on budget_setting / service_referral is just `return mapErr(e)` - nothing to
change there.)

Separate patch from p118 / p119 / p123: all three have already run on production, and a
Frappe patch runs ONCE. Re-pointing an executed patch at new markup means the new markup
never reaches the site.

One broken page must not block the other five: each sync is wrapped individually, failures go
to the Error Log, and the patch re-raises at the end so the Patch Log does not record a
partial run as done.
"""
import importlib

import frappe

FEATURES = [
    "affiliate_bonus",
    "budget_setting",
    "employee_info_update",
    "livestream_supplies",
    "purchase_request",
    "service_referral",
]

_MOD = "ecentric_workspace.approval_center.features.{}.infrastructure.page_sync"


def execute():
    failed = []
    for feature in FEATURES:
        try:
            page_sync = importlib.import_module(_MOD.format(feature))
            page_sync.sync()
        except Exception:
            failed.append(feature)
            frappe.log_error(
                title="p125 server-error-message resync failed: %s" % feature,
                message=frappe.get_traceback(),
            )
    if failed:
        raise Exception(
            "p125: %d/%d feature pages failed to resync (%s) - see Error Log; "
            "raising so the Patch Log does not mark this migration as done."
            % (len(failed), len(FEATURES), ", ".join(failed))
        )
