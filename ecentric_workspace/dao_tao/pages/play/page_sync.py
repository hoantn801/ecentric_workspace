# Copyright (c) 2026, eCentric and contributors
"""Web Page /quiz/choi - Chơi quiz. Repo so huu toan bo byte (trang moi). Dung sua trong Desk: sua
main_section.html canh ben, chay lai sync (patch resync + resync_manifest.json)."""
import os

from ecentric_workspace.dao_tao.pages import sync as site_sync

ROUTE = "quiz/choi"
NAME = "quiz-chơi"
TITLE = "Chơi quiz"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None):
    return site_sync.sync_one(ROUTE, NAME, TITLE, html if html is not None else _html())
