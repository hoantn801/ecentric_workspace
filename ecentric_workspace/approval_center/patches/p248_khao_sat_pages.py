# Copyright (c) 2026, eCentric and contributors
"""p248_khao_sat_pages: module Khao sat noi bo (01/10/2026, Hoan yeu cau).

1. Tao 4 Web Page tu repo: /khao-sat (hub), /khao-sat/lam (lam bai), /khao-sat/quan-ly,
   /khao-sat/soan. Route /khao-sat dang thuoc trang vong quay tra sua 07/2026 -> trang cu
   duoc DOI ROUTE sang /khao-sat-cu (giu noi dung, khong xoa) - xem surveys/pages/sync.py.
2. Menu trai them muc "Khảo sát" (trang chu: alias, nhom Workspace) -> sidebar tinh trong
   HTML cua trang chu, Viec cua toi, Tong quan doi byte (giong p241). ec_shell.js / server_nav
   van ve dung menu luc chay; day la lop du phong.

- home: co khoa drift; ban live truoc (a347101b...) da nam trong SUPERSEDES.
- my_work, tong_quan, 4 trang khao sat: repo so huu toan bo byte."""
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


def _surveys():
    from ecentric_workspace.surveys.pages import sync
    return sync.sync_all()


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    log = frappe.logger("approval_center")
    for name, fn in (("surveys", _surveys), ("home", _home), ("my_work", _my_work), ("tong_quan", _tong_quan)):
        try:
            log.info("p248 %s: %s" % (name, fn()))
        except Exception:
            # Mot trang loi khong duoc chan migrate cua ca site - chi ghi lai.
            frappe.log_error(title="p248_khao_sat_pages: %s" % name)
