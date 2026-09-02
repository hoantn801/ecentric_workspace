# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: server message on every error path, and a detail
view that cannot fall back to a stale state after Duyet / Tu choi / Bo sung / Duyet thay.

Two things Hoan reported on 02/09, both on this page.

1. "Loi khi o ngoai form"
   p123 rewired mapErr / friendlyErr / applyBackendError to `extractServerMsg`, but only the
   paths inside the create/edit form. Outside it the page still either read `e.message`
   (always empty for a `frappe.throw` - the sentence lives in `_server_messages`) or dropped
   the error object altogether:

       resubmitErr            read e.message -> "Khong the gui lai yeu cau" for every error
       loadList  .catch()     no argument    -> "Khong tai duoc danh sach", nothing else
       loadApprovals .catch() no argument    -> "Khong tai duoc", nothing else
       renderDetail .catch()  read e.message -> permission test never matched, so a
                                                PermissionError showed as "Khong tai duoc"
       uploadFile .catch()    read e.message (own Error objects - kept working, now goes
                                                through the same extractor)
       boot .catch()          no argument    -> "Khong tai duoc trang"

   All of them now surface `mapErr(e)` / `extractServerMsg(e)`, the same way the form does.
   A standalone test (test_pr_error_paths_and_fresh_detail.py) walks every `.catch(` in the
   template and fails on any handler that does not go through one of those helpers; the
   three deliberately silent ones (background balance re-read, modal re-enable, readiness
   probe) are listed there with their reason.

2. "Bam Duyet xong phai F5 moi thay"
   refreshDetail() does re-read the record from the API - that part was never the bug.
   Two things around it were:

   a. `loadSignReady` cached signing readiness ONCE per record id (`_signReadyFor===id`).
      Readiness is computed by the server for the CURRENT level (level_requires_signature,
      active_approver). After Duyet the level moves to N+1, drawDetail() runs with the fresh
      record, calls loadSignReady() without force, and the id matches -> skipped. The
      action panel then chose "Duyet" vs "Duyet & Ky" from level N's readiness for anyone
      who is also an approver at N+1. Only F5 (which wipes the state) fixed it. The cache
      key is now (id, approval_status, current_level).

   b. renderDetail() had no guard against out-of-order responses. Several get_detail loads
      can be in flight at once (readiness -> refreshDetail, the 5-second SIGNWAIT poll, the
      refresh right after an action); whichever answered LAST was drawn, even when it had
      been sent before the action. Each load now carries a sequence number and a response
      that is not the newest is dropped - the same `_loadTok` pattern the document signing
      section already uses.

Separate patch from p123 (already run on production - a patch runs ONCE; re-pointing it at
new markup would leave the site on the old markup forever).
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
