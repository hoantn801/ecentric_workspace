# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page so a rejected request can be raised again.

A rejected request is a permanent dead end, by design: `resubmit` only accepts
"Information Required", and the reject dialog tells the approver so ("Sau khi từ chối, yêu
cầu sẽ kết thúc"). That part stays.

What did not work was the aftermath. The requester had to retype everything - amount, bank
account, reason - and re-upload every file, even when the rejection was over a single wrong
digit.

And this path just became the main road rather than the exception: it was settled on 30/08
that changing a document that must be SIGNED goes through Từ chối, not "Yêu cầu bổ sung",
because SCTS accepts the file list only at document-creation time.

So: "Tạo phiếu mới từ phiếu này" on a Rejected or Cancelled request. It copies the editable
fields and attaches the same files to a fresh draft. The old request is not touched - not
edited, not deleted, audit trail intact. The confirmation checkbox is deliberately NOT
copied: it is a personal attestation, and carrying it over would tick it on the user's behalf
for a file set they have not re-read.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
