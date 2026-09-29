# Copyright (c) 2026, eCentric and contributors
"""Web Page /alerts/policies (Price Setup + Gift Exemptions) - nguon trong repo, dong bo co khoa chong troi.

Xem ecentric_workspace/alerts/site_pages/__init__.py. Sua trang = sua `main_section.html`
canh ben, dat BASELINE_SHA256 = sha moi, day gia tri cu xuong dau SUPERSEDES_SHA256 --
ca ba trong CUNG mot commit (`tools/ci/check.py --only pagesync` bat neu quen), roi them
patch goi sync() + cap nhat approval_center/patches/resync_manifest.json.
"""
import os

from ecentric_workspace.alerts.site_pages import sync as site_sync

ROUTE = "alerts/policies"
NAME = "alert-center-policies"
TITLE = "Alert Center Policies"


def _html():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 cua dung khoi HTML commit nay ship (UTF-8, LF).
BASELINE_SHA256 = "7157c23133d16ffe0dc827c6ccdbb831af85c73b24d13cdb922c2d59142a120f"
#: Cac ban live duoc phep ghi de (moi nhat o dau).
SUPERSEDES_SHA256 = (
    "9353c6bcca9a27b0b59170e765113cc825048ac7dddfe29ac5f425b621278ada",   # ban live 29/09/2026 (truoc NHIEU_LOP: khoi inline, csrf-fetch-patch)
)


def sync(html=None, force=0):
    """Tra ve {action: created|updated|unchanged|skipped|refused, route, name, ...}."""
    html = html if html is not None else _html()
    return site_sync.sync_one(ROUTE, NAME, TITLE, html,
                              (BASELINE_SHA256,) + SUPERSEDES_SHA256, force=force)
