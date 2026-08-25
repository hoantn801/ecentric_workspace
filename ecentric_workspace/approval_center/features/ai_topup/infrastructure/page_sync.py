# Copyright (c) 2026, eCentric and contributors
"""Versioned, idempotent AI Topup Web Page sync. Replaces reliance on the
run-once p006: a whitelisted admin-safe function + a versioned patch (p007) that
create/update the page from the current source HTML. Publishes the page for
controlled/direct UAT; NEVER activates the catalog card."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "approvals/ai-topup"
NAME = "approval-center-ai-topup"
TITLE = "AI Topup"


def _html():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "ui", "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# --- drift lock (#144, 2026-08-03) -------------------------------------------
# sha256 of the exact HTML this commit ships. Verified equal to the live
# main_section_html on team.ecentric.vn at the time of the commit, so the first
# sync after deploy returns "unchanged".
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values below. That is the whole point: several of these
# pages have been edited directly on the site in the past, and without the lock
# a stray call to the whitelisted sync endpoint would silently revert live to
# whatever the repo happened to hold.
#
# Deliberate update = edit the frontend source, bump BASELINE_SHA256 to the new
# sha, and move the value it replaced into SUPERSEDES_SHA256 -- all in the same
# commit. SUPERSEDES_SHA256 exists for repo-authored edits: at deploy time live
# still holds the bytes being superseded, and after the first successful write
# it holds the new snapshot; both are "not drifted", so both must be accepted.
BASELINE_SHA256 = "fb8d7ee657fc288436113eeab5ddbb23bdfd20d21696929bbb4fc56976e14b3d"

# Giá trị live mà snapshot này được phép ghi đè.
#
# 1c56e03b... là bytes của d6d412c (GD2 C2 UAT fix), tức là baseline ĐÚNG cho tới khi
# PR #241 (b082c2a, ec-datepicker: thêm data-ec-dp-range vào form lọc) sửa
# frontend/ai_topup.main_section.html mà KHÔNG bump hằng số này. Từ đó BASELINE_SHA256
# không còn khớp HTML repo ship, nên sync ghi được đúng một lần rồi refused vĩnh viễn.
# tools/ci/check.py (phép kiểm `pagesync`) bắt được sai lệch đó.
#
# Liệt kê ở đây để cả hai trạng thái live đều đi tiếp được: môi trường còn giữ bytes
# d6d412c thì sync tiến lên, môi trường đã nhận bytes #241 thì trả về "unchanged".
# Bỏ entry này khi đã xác nhận deploy trên mọi môi trường.
SUPERSEDES_SHA256 = (
    "d48a62f1226b2b8a9ac0c886235d978c0164817e1f688995e3ec97e1253f2a97",  # superseded by fb8d7ee657fc (upload UX + tick)
    "6106ed84d949c5349c811a504457b45b809df27a6b909e6fe783bfcf11e4b534",  # superseded by d48a62f1226b (nhớ tab khi quay lại hub)
    "674def069d7c1aa381c1ef8f4db0641bb9ab4decf3f59b6cccfb98247ad15a32",  # superseded by 6106ed84d949 (hub: bỏ 3 tab + upload nhiều tệp)
    "2645973df8a3bcfad7c10b38e44119256e073144c6d4bfb5910a7ba2650e5457",  # superseded by 674def069d7c
    "1c56e03bccf777286e281dc39fafdd375610c2ebd14bb6c1978b467aa7fae802",
)


def sync(html=None, force=0):
    """Guarded sync (#144). Delegates to the shared upsert helper -- this module
    used to carry its own hand-rolled copy of the lookup/insert/update logic,
    which meant the drift lock and the publish-preserve rule could not reach it.

    publish="preserve" -- never re-publishes a page an operator un-published;
                          a page that does not exist yet is created published.
    expect_sha         -- refuses (writes nothing) when live has drifted away
                          from the snapshot this commit ships.
    force=1            -- drops ONLY the drift lock; it never force-publishes.

    Returns {action: created|updated|unchanged|skipped|refused, route, name}."""
    html = html if html is not None else _html()
    return page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )


@frappe.whitelist(methods=["POST"])
def sync_ai_topup_page():
    """Admin-safe re-sync (System Manager only). No manual Web Page edits needed."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the AI Topup page."), frappe.PermissionError)
    return sync()
