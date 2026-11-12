# Copyright (c) 2026, eCentric and contributors
"""Doi 2 cau ghim tren anh cua bo quiz "Claude buoi 1" sang anh giao dien Claude (Hoan 13/11/2026
sang): nut Manage memory va muc Projects. CHI thay 2 cau ghim cuoi - giu nguyen moi cau / luat
choi Hoan da sua tay tren site."""
import io
import json
import os

import frappe

from ecentric_workspace.dao_tao import constants as C

SEED = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "seeds", "claude_buoi1.json")


def execute():
    try:
        from ecentric_workspace.dao_tao.domain import questions
        from ecentric_workspace.dao_tao.infrastructure import store
        with io.open(SEED, encoding="utf-8") as fh:
            seed = json.load(fh)
        name = frappe.db.get_value(C.QUIZ, {"title": seed["title"]}, "name")
        if not name:
            return
        q = store.get_quiz(name)
        qs = list(q.get("questions") or [])
        new_pins = [x for x in seed["questions"] if x.get("type") == "pin"]
        pin_idx = [i for i, x in enumerate(qs) if x.get("type") == "pin"]
        if len(pin_idx) < len(new_pins):
            return
        for i, nq in zip(pin_idx[-len(new_pins):], new_pins):
            qs[i] = dict(nq)
        store.save_quiz(name, {"questions": questions.require_valid(qs)})
    except Exception:
        frappe.log_error(frappe.get_traceback(), "dao_tao p005 cau ghim THAT BAI")
