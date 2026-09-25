# Copyright (c) 2026, eCentric and contributors
"""Resync trang van hanh ky so: them muc "Da ky ben SCTS ma ERP chua dung".

Hoan bao 15/09: cron soi lech gui thong bao "Chu ky da co ben SCTS ma ERP chua dung - X da
ky 1 chu ky, phieu van cho o cap 4", nhung mo trang van hanh ra thi KHONG THAY GI.

Ca hai deu dung, va do moi la van de. Bon muc cu cua trang deu liet ke CHAN KY dang gap van
de; o ca nay chua bao gio co chan ky nao duoc tao - nguoi duyet ky thang tren cong SCTS thay
vi bam "Duyet & Ky" trong ERP. Khong co chan ky thi khong co dong nao de hien, nen o "Chan ky
dang cho xu ly" bao 0 - dung su that ma khong tra loi dung cau hoi.

Mot thong bao tro toi mot man hinh khong co gi trong nhu he thong noi doi, va lan sau khong
ai doc no nua. Cron da chay tu 09/09; phan hien ra man hinh la mon no tu do den nay
(viec #29 trong so).

Muc moi dat NGAY SAU muc dau - do la thu nguoi ta mo trang ra de tim. CHI DOC, khong co nut:
dong bo chu ky la hanh dong CONG NHAN mot chu ky, no dong mot cap duyet va day phieu di tiep,
nen nut phai nam o trang phieu noi nguoi bam nhin thay ho so va phai nhap can cu. Mot nut
"dong bo" ngay tren bang liet ke se bien mot quyet dinh thanh mot cu bam nhanh.

Patch moi vi p168 (resync ops gan nhat) da chay - patch chay MOT LAN, khong bao gio tro lai
patch cu.
"""
import frappe

from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    try:
        frappe.log_error("p193 ops sync=%s" % (ops_page_sync.sync() or {}).get("action"),
                         "p193 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p193 resync failed")
        raise
