# Copyright (c) 2026, eCentric and contributors
"""Re-publish the esign ops page so it can say WHY a signed PDF has not arrived.

Content: the retrieval path used to have a silent branch - the cron touched a package every
30 minutes, decided "not ready", and returned without recording anything. Five packages whose
signing was fully complete sat with zero retrieval events, so the page guessed "nobody has
tried yet", which was wrong, and the stall alarm could not fire because it counts events that
were never written. `signed_files` now records the reason the machine actually returned, and
this page translates it into plain Vietnamese.

WHY A SEPARATE PATCH FROM p119.
p119 already ran on production. A patch runs ONCE - Frappe records it in Patch Log and never
calls it again. The ops template was edited a second time AFTER p119 had shipped, and the
manifest still pointed at p119, so the newer markup would have sat in the repo forever while
the site served the older page. Caught by reading the live page instead of trusting that
"the manifest has a patch" means "the page is current".

The manifest guard verifies that a template's hash is matched by a declared, existing patch -
it cannot know whether that patch has already executed on a given site. So the rule is: touch
a template after its patch has been committed, add a NEW patch. Never re-point an existing
one.
"""
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    ops_page_sync.sync()
