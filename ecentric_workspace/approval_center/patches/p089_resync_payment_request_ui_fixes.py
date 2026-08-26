# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page after three UI fixes found during the UAT pilots.

1. "Ký thử" turned the button blue but drew nothing: the preview loop iterated a scratch
   property that is never assigned anywhere, so it always ran over an empty list. It now
   reads the boxes actually present, refuses out loud when there is no box, and surfaces the
   backend's reason instead of a generic sentence.
2. The last signer card (CEO) was clipped by the drawer footer, so its button could not be
   clicked: grid children default to min-height:auto and could not shrink, and the signer
   column had no bottom padding.
3. A second drag-and-drop area appeared next to "+ Tải tài liệu": the site-wide form kit
   wrapped the drawer's own hidden file input. The upload area now declares ownership.

Web Pages are served from the database, so the code change alone does not reach users.
Idempotent: page_sync compares content and skips when unchanged.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
