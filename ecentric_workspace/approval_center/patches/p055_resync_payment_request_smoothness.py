# Copyright (c) 2026, eCentric and contributors
"""Re-sync the Payment Request Web Page after (a) the overnight drawer-smoothness
pass and (b) the reorg path fix for _PLATFORM_ESIGN_UI (3-dirname bug composed the
page WITHOUT the esign panels, so a 2026-08-21 manual resync briefly published the
page missing the unified 'Tai lieu & ky so' section).

Repo convention: a fresh patch pushes edited page HTML into the live Web Page on
the next bench migrate (Frappe Cloud deploy) with no manual command. Idempotent:
upsert_web_page returns 'unchanged' when content already matches."""
from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync


def execute():
    page_sync.sync()
