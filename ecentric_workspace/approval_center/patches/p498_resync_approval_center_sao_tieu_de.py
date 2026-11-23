# Copyright (c) 2026, eCentric and contributors
"""p498_resync_approval_center_sao_tieu_de (23/11/2026, Hoan: "ngoi sao nay hoi lech"): sync lai /approvals
tu nguon repo (A65). Icon sao o tieu de khoi "Da ghim" bi quy tac chung svg.icon{margin:auto} day ra giua
khung -> margin:0; bo doi lan chuot doc thanh cuon ngang tren hang chip (chip "Tat ca" bi cat); bo dong mo ta duoi tieu de (Hoan: cho gon); dau "?" co dinh goc duoi phai the. Co khoa chong troi. KHONG nem loi, KHONG xoa du lieu."""
import frappe

MOD = "ecentric_workspace.approval_center.ui.hub.page_sync"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        res = frappe.get_module(MOD).sync() or {}
        frappe.logger("approval_center").info("p498 hub: %s" % res)
        if isinstance(res, dict) and res.get("action") == "refused":
            frappe.log_error("p498: /approvals refused (live drift): %s" % res, "p498_resync_approval_center_sao_tieu_de")
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        frappe.log_error(frappe.get_traceback(), "p498_resync_approval_center_sao_tieu_de failed")
