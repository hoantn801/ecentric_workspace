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
BASELINE_SHA256 = "a52de4d380799defc1f806c2de3218ae93d0e8153e7c3b177943dc5fbf77ff44"
#: Cac ban live duoc phep ghi de (moi nhat o dau).
SUPERSEDES_SHA256 = (
    "5732f0e6ffe17af27c63091e1252e1bcfff06825d58a3d710f0b0f6711483dd7",   # p223 (29/09/2026) - truoc khi can giua noi dung (10/10)
    "0a06538a47c70eca3bfcea6eae5ac2cdb9713ac2304b07f43834079e8706b6a0",   # ban live 29/09/2026 (truoc NHIEU_LOP: khoi inline, csrf-fetch-patch)
)


def sync(html=None, force=0):
    """Tra ve {action: created|updated|unchanged|skipped|refused, route, name, ...}."""
    html = html if html is not None else _html()
    return site_sync.sync_one(ROUTE, NAME, TITLE, html,
                              (BASELINE_SHA256,) + SUPERSEDES_SHA256, force=force)
