# Copyright (c) 2026, eCentric and contributors
"""p241_resync_si_tool_nav: doi nhan menu "AI Tool" -> "SI Tool" (01/10, Hoan yeu cau) va sua
mau chu tieu de trang /ai-video (chu den tren nen xanh).

Sidebar tinh trong HTML moi trang do shell.fallback sinh tu registry; doi nhan menu thi byte
4 trang doi: trang chu, Viec cua toi, Tong quan, AI Video. ec_shell.js van ve dung menu luc
chay - day la sua lop du phong + trang /ai-video co sua CSS that.

- home: co khoa drift; ban live cu (cfb286e5...) da nam trong SUPERSEDES.
- my_work, tong_quan, ai_video: repo so huu toan bo byte, khong khoa drift."""
import frappe


def _home():
    from ecentric_workspace.legacy_pages.home import page_sync
    return page_sync.sync()


def _my_work():
    from ecentric_workspace.action_center.pages.my_work import page_sync
    return page_sync.sync()


def _tong_quan():
    from ecentric_workspace.hr.pages.tong_quan import page_sync
    return page_sync.sync()


def _ai_video():
    from ecentric_workspace.ai_tools.pages.ai_video import page_sync
    return page_sync.sync()


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    log = frappe.logger("approval_center")
    for name, fn in (("home", _home), ("my_work", _my_work), ("tong_quan", _tong_quan), ("ai_video", _ai_video)):
        try:
            log.info("p241 %s: %s" % (name, fn()))
        except Exception:
            # Mot trang loi khong duoc chan migrate cua ca site - chi ghi lai.
            frappe.log_error(title="p241_resync_si_tool_nav: %s" % name)
