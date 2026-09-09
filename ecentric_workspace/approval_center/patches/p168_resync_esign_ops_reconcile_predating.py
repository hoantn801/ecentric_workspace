# Copyright (c) 2026, eCentric and contributors
"""Resync trang van hanh ky so: them nut "Doi soat - chap nhan chu ky ky truoc lenh".

Nguoi duyet (HOF/CEO) quen mo mail cua SCTS roi ky thang tren cong TRUOC khi ho bam Duyet
tren ERP. Chu ky la that, dung nguoi, dung tai lieu - nhung moc thoi gian `signed_after` cua
ERP tu choi no, va chan ky nam Manual Review. Truoc dot nay chi co script chay tay moi bat
duoc co `accept_predating`; nut "Doi soat" tren trang khong truyen co do (mac dinh TAT, co
chu dinh), nen bam vao van bi tu choi.

Nut moi CHI hien voi chan ky dang Manual Review, bat buoc ly do, va khong rong hon "Doi soat"
o bat ky chieu nao khac: co chi go DUNG phep kiem thoi gian, va chi trong nhanh dem duoc chu
ky. Sai nguoi / sai tai lieu / chua ky / khong du chu ky van bi tu choi nguyen ven.

Patch moi vi p159 (resync ops gan nhat) da chay - patch chay MOT LAN, khong bao gio tro lai
patch cu.
"""
import frappe

from ecentric_workspace.platform.esign import ops_page_sync


def execute():
    try:
        frappe.log_error("p168 ops sync=%s" % (ops_page_sync.sync() or {}).get("action"),
                         "p168 resync")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p168 resync failed")
        raise
