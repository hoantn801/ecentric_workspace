# Copyright (c) 2026, eCentric and contributors
"""Web Page /alerts/locks (Stock Safety: hang doi review dry-run + pause) - nguon trong repo, dong bo co khoa chong troi.

Xem ecentric_workspace/alerts/site_pages/__init__.py. Sua trang = sua `main_section.html`
canh ben, dat BASELINE_SHA256 = sha moi, day gia tri cu xuong dau SUPERSEDES_SHA256 --
ca ba trong CUNG mot commit (`tools/ci/check.py --only pagesync` bat neu quen), roi them
patch goi sync() + cap nhat approval_center/patches/resync_manifest.json.
"""
import os

from ecentric_workspace.alerts.site_pages import sync as site_sync

ROUTE = "alerts/locks"
NAME = "alert-center-locks"
TITLE = "Alert Center Locks"


def _html():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 cua dung khoi HTML commit nay ship (UTF-8, LF).
BASELINE_SHA256 = "aab025b9225ce150cc4ad020e05ce6a91c55045665a7693d7f319f3df7a60b01"
#: Cac ban live duoc phep ghi de (moi nhat o dau).
SUPERSEDES_SHA256 = (
    "04c93c168192613f02aa463795b7930e898fb7edc685636d082b5ce67a8d4166",   # ban live 29/09/2026 (truoc NHIEU_LOP: khoi inline, csrf-fetch-patch)
)


def sync(html=None, force=0):
    """Tra ve {action: created|updated|unchanged|skipped|refused, route, name, ...}."""
    html = html if html is not None else _html()
    return site_sync.sync_one(ROUTE, NAME, TITLE, html,
                              (BASELINE_SHA256,) + SUPERSEDES_SHA256, force=force)
