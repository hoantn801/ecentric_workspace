# Copyright (c) 2026, eCentric and contributors
"""Cap nhat bo quiz "Claude buoi 1 · Quiz sau buoi hoc" theo gop y Hoan 13/11/2026 truoc buoi hoc:
cau hoi viet de hieu hon, giai thich chi tiet hon, thay cau Booking KOC (it nguoi biet) va cau
QC skill KOC; bat "dien thoai cung thu tu + cung mau voi man chieu".

Ghi de noi dung bo seed (Hoan duyet 13/11, bo nay chi moi duoc choi thu). Phong da mo truoc do giu
nguyen cau hoi cu (phong chot ban sao luc mo)."""
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
        name = frappe.db.get_value(C.QUIZ, {"title": seed["title"]}, "name")
        if not name:
            return
        q = store.get_quiz(name)
        store.save_quiz(name, {"title": q["title"], "description": seed.get("description") or q.get("description") or "",
                               "status": q.get("status") or C.QUIZ_READY, "template": q.get("template") or "",
                               "questions": questions.require_valid(seed["questions"]),
                               "settings": settings.clean_settings(dict(q.get("settings") or {}, same_order=True)),
                               "prizes": q["prizes"] if q.get("prizes") is not None
                               else prizes.clean_prizes(seed.get("prizes"))})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "dao_tao p003 cap nhat quiz THAT BAI")
