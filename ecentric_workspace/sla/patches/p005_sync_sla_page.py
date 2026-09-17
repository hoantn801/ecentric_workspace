# Copyright (c) 2026, eCentric and contributors
"""Tao Web Page /sla lan dau tu ma nguon trong repo.

FAIL-SAFE. Patch nay chi dung trang - khong co no thi module SLA van chay dung,
chi la khong ai mo duoc bang diem. Doi lai, mot patch nem loi se CHAN CA BAN
DEPLOY. Nen moi loi o day deu bi nuot va ghi vao Error Log; con duong sua la
goi lai `ecentric_workspace.sla.controllers.api.sync_sla_page`, khong phai roll
back ca dot.

CHAY LAI DUOC. `page_sync.sync()` tim trang theo ten chuan, theo route, va theo
slug Frappe se dat - roi CAP NHAT tai cho. Khong bao gio `insert` de dam vao
khoa chinh, khong bao gio xoa trang.

`refused` LA MOT KET QUA KHAC HAN, va phai co tieu de log khac. Khoa chong ghi
de tra ve `refused` khi HTML tren ban song khong khop snapshot cua repo - luc
do deploy van xanh, patch van xanh, va trang van la ban cu. Ghi chung mot tieu
de voi lan thanh cong nghia la kieu hong do khong bao gio noi len tieng.
"""
import frappe

TITLE_OK = "p005 dong bo trang /sla"
TITLE_REFUSED = "p005 trang /sla BI TU CHOI GHI (live da troi khoi snapshot)"


def execute():
    try:
        from ecentric_workspace.sla.pages.scoreboard import page_sync
        res = page_sync.sync()
    except Exception:
        frappe.log_error(title=TITLE_OK, message=frappe.get_traceback())
        return

    try:
        refused = isinstance(res, dict) and res.get("action") == "refused"
        frappe.log_error(title=TITLE_REFUSED if refused else TITLE_OK,
                         message=repr(res))
    except Exception:
        pass
