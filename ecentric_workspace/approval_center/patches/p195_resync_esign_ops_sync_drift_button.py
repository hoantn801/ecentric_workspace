# Copyright (c) 2026, eCentric and contributors
"""Resync trang van hanh: them nut "Dong bo chu ky tu cong" tren dong soi lech.

PATCH MOI, KHONG tro lai p193. p193 da chay tren prod luc 15/09 15:57:50 (co trong Patch
Log), va mot patch chi chay MOT LAN - tro lai no thi noi dung moi cua ops_page.html nam im
trong repo, deploy sach ma man hinh khong doi. Dung cai bay da ghi trong
`feedback_patch_runs_once_never_repoint`.

VI SAO CAN NUT. Sang 15/09 khi dua muc soi lech len trang, toi CO Y de cot hanh dong rong,
voi lap luan: "dong bo la hanh dong CONG NHAN mot chu ky, nut phai nam o trang phieu noi
nguoi bam nhin thay ho so". Lap luan dua tren MOT GIA DINH KHONG AI KIEM: rang trang phieu
co nut do. No khong co. `sync_signatures_from_provider` la mot API co that ma KHONG GIAO
DIEN NAO GOI - dung lop loi ma chinh trang van hanh sinh ra de xoa bo.

Hau qua trong ngay: ca thong bao cua cron lan muc moi deu bao nguoi ta "mo phieu roi dong bo
chu ky ve", mot viec khong bam duoc o dau ca; EC-PAYR-2026-00103 phai goi API bang tay.

Nut bat nhap can cu (>= 10 ky tu, may chu cung doi) va hop xac nhan noi ro no KHONG tao ra
chu ky nao - chi doc lai phia SCTS roi cong nhan chu ky da co.
"""
import frappe

from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    try:
        frappe.log_error("p195 ops sync=%s" % (ops_page_sync.sync() or {}).get("action"),
                         "p195 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p195 resync failed")
        raise
