# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page: supplement documents get their own, correct door.

Supersedes the 30/08 stopgap in p104. That one un-hid the LEGACY `request_attachment` field
on the edit screen - which rebuilt the very second upload surface this design had removed,
and put the control outside "TÀI LIỆU & KÝ SỐ", where nobody looks for it. Reverted.

The rule agreed 30/08, after checking what the provider actually allows:

  * "Yêu cầu bổ sung" is for EVIDENCE ONLY - an invoice, a receipt, a quote. It attaches to
    the request, never joins the signing package, never goes to SCTS, and invalidates no
    existing signature. Nobody signs again.
  * Changing a document that must be SIGNED is not this path: the approver rejects, and the
    requester raises a new request.

That split is not a preference, it follows from the provider: SCTS takes the file list at
document-creation time only. There is no endpoint to add a page to a document that already
exists, so "keep the old signatures AND put the new file on the SCTS side" is not a thing
that can be built.

Changes carried by this resync:
  * "+ Tải tài liệu" opens while the request sits at Information Required, with a line saying
    the file is supporting evidence;
  * a file outside a LOCKED package is reported as supporting, not as "requires signature" -
    it could never join that package, so asking for a signature on it would be a promise the
    screen cannot keep.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
