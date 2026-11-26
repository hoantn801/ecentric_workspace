# Copyright (c) 2026, eCentric and contributors
"""Trang /kalodata: repo so huu toan bo HTML (main_section.html canh file nay)."""
import io
import os

from ecentric_workspace.shared_tools.pages import sync as site_sync

ROUTE = "kalodata"
NAME = "kalodata-dùng-chung"
TITLE = "Kalodata dùng chung"


def _html():
    with io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    return site_sync.sync_one(ROUTE, NAME, TITLE, html if html is not None else _html())
