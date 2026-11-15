# Copyright (c) 2026, eCentric and contributors
"""Khung chung cho job nen Giong doc AI: kill switch + commit / rollback + log loi (khong nem ra worker)."""
import frappe

from ecentric_workspace.ai_tools.features.ai_voice import constants as C


def disabled():
    return bool(frappe.conf.get(C.KILL_SWITCH))


def guarded(title, fn):
    """Chay fn(); thanh cong -> commit, loi -> rollback + Error Log. Tra ket qua hoac None."""
    try:
        out = fn()
        frappe.db.commit()
        return out
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title=("ai_voice " + title)[:140])
        return None
