# Copyright (c) 2026, eCentric and contributors
"""Trang /tai-san/luan-chuyen (moves): repo so huu toan bo HTML (main_section.html canh file nay)."""
import io
import os

from ecentric_workspace.tai_san.pages import sync as site_sync

ROUTE = "tai-san/luan-chuyen"
NAME = "tài-sản-cấp-phát-thu-hồi"
TITLE = "Cấp phát & thu hồi"


def _html():
    with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    return site_sync.sync_one(ROUTE, NAME, TITLE, html if html is not None else _html())
