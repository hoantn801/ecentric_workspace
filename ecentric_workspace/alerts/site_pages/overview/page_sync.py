# Copyright (c) 2026, eCentric and contributors
"""Web Page /alerts (Dashboard + danh sach alert (#al-alert-list)) - nguon trong repo, dong bo co khoa chong troi.

Xem ecentric_workspace/alerts/site_pages/__init__.py. Sua trang = sua `main_section.html`
canh ben, dat BASELINE_SHA256 = sha moi, day gia tri cu xuong dau SUPERSEDES_SHA256 --
ca ba trong CUNG mot commit (`tools/ci/check.py --only pagesync` bat neu quen), roi them
patch goi sync() + cap nhat approval_center/patches/resync_manifest.json.
"""
import os

from ecentric_workspace.alerts.site_pages import sync as site_sync

ROUTE = "alerts"
NAME = "alert-center"
TITLE = "Alert Center"


def _html():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 cua dung khoi HTML commit nay ship (UTF-8, LF).
BASELINE_SHA256 = "0a06538a47c70eca3bfcea6eae5ac2cdb9713ac2304b07f43834079e8706b6a0"
#: Cac ban live duoc phep ghi de. Rong: anh chup nay CHINH LA ban live 29/09/2026.
SUPERSEDES_SHA256 = ()


def sync(html=None, force=0):
    """Tra ve {action: created|updated|unchanged|skipped|refused, route, name, ...}."""
    html = html if html is not None else _html()
    return site_sync.sync_one(ROUTE, NAME, TITLE, html,
                              (BASELINE_SHA256,) + SUPERSEDES_SHA256, force=force)
