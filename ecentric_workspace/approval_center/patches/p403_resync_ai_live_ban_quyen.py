# Copyright (c) 2026, eCentric and contributors
"""p403_resync_ai_live_ban_quyen (17/11/2026): sua 2 loi chi lo tren site that sau p402.
- Cong tac Bat API / Chi ghi nhan bi CSS cua site ep input[type=checkbox] rong 14px -> ghi de bang !important.
- /ai-live/ban-quyen roi vao khu "Phe duyet" o menu trai (muc Ban quyen loc theo role nen khong keo ngu canh)
  -> muc "Quan ly AI Live" nhan them "/ai-live/*"; vo shell tinh cua trang sinh lai theo ngu canh AI.
Chi sync lai Web Page /ai-live/ban-quyen. Chay lai vo hai."""
import frappe

from ecentric_workspace.ai_tools.pages.ai_live_ban_quyen import page_sync as lic_sync


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        frappe.logger("ai_tools").info("p403_resync_ai_live_ban_quyen: %s" % (lic_sync.sync() or {}))
    except Exception:
        frappe.log_error(title="p403_resync_ai_live_ban_quyen")
