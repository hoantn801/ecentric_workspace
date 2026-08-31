# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page with the fixes from the 31/08 three-bot E2E audit.

Four browser-side fixes ride this resync (the page injects all three templates):

1. Stored XSS in the approval stepper (main_section.html): approver names and rejection
   comments were concatenated into `.step-meta` innerHTML unescaped, while the timeline and
   banner escaped the very same data. Anyone who could type a rejection comment could run
   script in the browser of anyone viewing the request. Escaped at the point the data enters
   the string - the "Qua han" span in the same string is intentional markup.
2. The sidebar user card linked to /app/user (Desk) - the existing no-desk-urls QC gate only
   scans action_center, so it never saw this page. Now /me.
3. Three swallowed errors: setup_state's empty catch left "Dang tai..." hanging forever on a
   500; openDrawer's Promise.all had no catch at all, opening an empty drawer with no
   message; the requester panel's readiness refresh failed silently even mid-poll. All three
   now say what happened and what to do.
4. (Server-side, same release, no resync needed but documented here because the symptom is
   visible on this page: requester legs stuck in Manual Review.) poll_pending and the ops
   reconcile both routed REQUESTER legs down the approver completion path, where
   engine.approve refuses them - so the rescue button re-created the exact failure it was
   rescuing. Both now route by actor_type via _complete_dsr.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
