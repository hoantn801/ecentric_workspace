# Copyright (c) 2026, eCentric and contributors
"""p005_fix_approvals_sidebar_alignment: re-apply the /approvals Web Page so the
sidebar left-alignment CSS fix reaches production.

Prior page patches (p003/p004) are run-once (Patch Log); a plain migrate will
not re-push updated source HTML/CSS to the already-created page. This patch
re-runs the SAME idempotent, code-owned upsert from
approval_center/frontend/approvals.main_section.html.

Idempotent + non-destructive. Updates only the `approvals` Web Page. Does NOT
touch /approval. No schema / API / seed / other-module change.
"""
from ecentric_workspace.approval_center.patches import p003_create_approvals_page


def execute():
    p003_create_approvals_page.execute()
