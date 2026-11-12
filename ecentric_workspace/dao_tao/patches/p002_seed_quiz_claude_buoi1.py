# Copyright (c) 2026, eCentric and contributors
"""Nap san bo quiz "Claude buoi 1 · Quiz sau buoi hoc" (21 cau, 8 kieu cau) cho buoi dao tao
Claude Team 13/11/2026 - Hoan 12/11: "dua luon bai Quiz ... len, cho nhieu loai cau tra loi".

Noi dung o dao_tao/seeds/claude_buoi1.json, chuan hoa qua dung domain cua trinh soan. Da co bo
cung ten (vd Ban dao tao da sua) thi KHONG dung toi. Trang thai "San sang": vao /quiz bam Mo phong."""
import io
import json
import os

import frappe

from ecentric_workspace.dao_tao import constants as C

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds", "claude_buoi1.json")


def execute():
    try:
        from ecentric_workspace.dao_tao.domain import prizes, questions, settings
        from ecentric_workspace.dao_tao.infrastructure import store
        with io.open(SEED, encoding="utf-8") as fh:
            seed = json.load(fh)
        if frappe.db.exists(C.QUIZ, {"title": seed["title"]}):
            return
        store.insert_quiz({"title": seed["title"], "description": seed.get("description") or "",
                           "status": C.QUIZ_READY, "template": seed.get("template") or "",
                           "questions": questions.require_valid(seed["questions"]),
                           "settings": settings.clean_settings(seed.get("settings")),
                           "prizes": prizes.clean_prizes(seed.get("prizes"))})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "dao_tao p002 seed quiz THAT BAI")
