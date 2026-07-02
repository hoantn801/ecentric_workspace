# Copyright (c) 2026, eCentric and contributors
"""p004_update_approvals_page_ui: refresh the existing /approvals Web Page after
the B2b UI/IA correction.

p003_create_approvals_page is a run-once patch (recorded in Patch Log), so a
plain migrate will NOT re-apply source-HTML changes to an already-created page.
This new patch re-runs the SAME idempotent, code-owned upsert so production picks
up approval_center/frontend/approvals.main_section.html.

Idempotent + non-destructive. Updates only the `approvals` Web Page. Does NOT
touch /approval. No schema / API / seed / other-module change.
Rollback: non-destructive (re-run with prior HTML, or un-publish the page).
"""
from ecentric_workspace.approval_center.patches import p003_create_approvals_page


def execute():
    # Reuse the exact code-owned Web Page upsert (create-or-update by route).
    p003_create_approvals_page.execute()
