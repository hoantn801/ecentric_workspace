# Copyright (c) 2026, eCentric and contributors
"""Web Page /alerts/rules (Brand Defaults + Advanced Exceptions) - nguon trong repo, dong bo co khoa chong troi.

Xem ecentric_workspace/alerts/site_pages/__init__.py. Sua trang = sua `main_section.html`
canh ben, dat BASELINE_SHA256 = sha moi, day gia tri cu xuong dau SUPERSEDES_SHA256 --
ca ba trong CUNG mot commit (`tools/ci/check.py --only pagesync` bat neu quen), roi them
patch goi sync() + cap nhat approval_center/patches/resync_manifest.json.
"""
import os

from ecentric_workspace.alerts.site_pages import sync as site_sync

ROUTE = "alerts/rules"
NAME = "alert-center-rules"
TITLE = "Alert Center Rules"


def _html():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 cua dung khoi HTML commit nay ship (UTF-8, LF).
BASELINE_SHA256 = "b7435c068316f36336e5cea337a5e0a2e1b66e40faec27cd2d17b71ad3b8dee1"
#: Cac ban live duoc phep ghi de (moi nhat o dau).
SUPERSEDES_SHA256 = (
    "2cb3d306356b62e9c77e2d1ae3af16eef31a7dd59f8a7d37b6f22ad11ae0907f",   # ban live 29/09/2026 (truoc NHIEU_LOP: khoi inline, csrf-fetch-patch)
)


def sync(html=None, force=0):
    """Tra ve {action: created|updated|unchanged|skipped|refused, route, name, ...}."""
    html = html if html is not None else _html()
    return site_sync.sync_one(ROUTE, NAME, TITLE, html,
                              (BASELINE_SHA256,) + SUPERSEDES_SHA256, force=force)
