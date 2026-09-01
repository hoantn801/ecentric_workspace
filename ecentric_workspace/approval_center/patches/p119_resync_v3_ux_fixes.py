# Copyright (c) 2026, eCentric and contributors
"""Re-publish the Payment Request page and the esign ops page with three UX fixes from the
round-3 audit.

1. The "Tài liệu & ký số" block used to vanish silently when its endpoint failed. The 31/08
   patch that was supposed to stop swallowing that error wrote the message into `#ecdMsg` -
   an element that does not exist - and its fallback lived inside a drawer that is closed at
   that moment. So the block still disappeared without a word; the fix existed only on paper.
   It now reveals the block and writes into a real alert box it creates inside its own root.

2. `request_attachment` is mandatory, but its field is hidden by an esign CSS rule (the real
   upload surface lives inside the document section). Validation focused the hidden field,
   so the user got an error pointing at nothing. The error now names the document section and
   the page scrolls there instead.

3. The ops page could not say WHY a signed PDF had not arrived. The retrieval path had a
   silent branch: the cron touched a package every 30 minutes, decided "not ready", and
   returned without recording anything. On live data (01/09) five packages whose signing was
   fully complete sat with zero retrieval events, so the page guessed "nobody has tried yet -
   SCTS has not finished signing" - a guess that turned out to be wrong, and the stall alarm
   could not fire because it counts events that were never written. The reason the machine
   actually returned is now recorded and shown in plain Vietnamese.

4. On the ops page, the result of an irreversible action (cancel a signing leg, waive a
   signature debt, stop retrying) was overwritten a moment later by the reload's own
   "Đang tải…". The person who pressed the button never got to read what happened - on the
   page built to end exactly that kind of silence. The message is now restored after reload.
"""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    page_sync.sync()          # main_section.html + document_signing_section.html
    ops_page_sync.sync()      # ops_page.html
