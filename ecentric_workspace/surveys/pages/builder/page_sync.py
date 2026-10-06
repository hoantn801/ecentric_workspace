# Copyright (c) 2026, eCentric and contributors
"""Web Page /khao-sat/soan - Soạn khảo sát. Repo so huu toan bo byte, upsert khong khoa troi (trang moi,
khong co lich su song can giu - giong ai_tools/pages/ai_video). Dung sua trong Desk: sua
main_section.html canh ben, chay lai sync (patch resync + resync_manifest.json)."""
import os

from ecentric_workspace.surveys.pages import sync as site_sync

ROUTE = "khao-sat/soan"
NAME = "soạn-khảo-sát"
TITLE = "Soạn khảo sát"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    return site_sync.sync_one(ROUTE, NAME, TITLE, html if html is not None else _html())
