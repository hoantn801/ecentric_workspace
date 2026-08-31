# Copyright (c) 2026, eCentric and contributors
"""Re-publish the ops page: stop blaming the user's permissions for the system's own faults.

The page reported every load failure as "Cần quyền System Manager". On 31/08 the real failure
was a query asking for `business_doctype` on the signing-leg DocType, where that column does
not exist - MySQL 1054, HTTP 500. The admin page then told a System Manager to go get System
Manager rights: a message that is both false and points at the wrong fix.

Now the page only claims a permission problem when the server actually answers 403; anything
else is reported as a system error with its status code, and says plainly that it is not a
permissions issue.

Found by opening the page in a browser after a green deploy check. Every API-level check
passed - the markup was correct, the patches had run, the fields existed. The page was broken
anyway, because nothing had asked it to actually load its data.
"""
from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    ops_page_sync.sync()
