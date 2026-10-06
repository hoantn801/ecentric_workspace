# Copyright (c) 2026, eCentric and contributors
"""Dong bo lai Web Page /sla sau khi them o chon ky.

HTML trong repo da doi (them o chon thang + luong goi API mang `period`), nen
BASELINE_SHA256 doi theo. Khong co patch nay thi code moi nam trong repo con
ban song van la HTML cu - trang khong he co o chon, va khong mot thong bao loi
nao xuat hien de ai do nhan ra.

FAIL-SAFE: nuot moi loi va ghi Error Log. Mot patch hong CHAN CA lan deploy, va
cai gia cua viec do lon hon nhieu so voi mot trang tam thoi thieu o chon ky.
"""
import frappe

TITLE = "p015 resync trang /sla (o chon ky)"


def execute():
    try:
        from ecentric_workspace.sla.pages.scoreboard import page_sync
        res = page_sync.sync()
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
        return

    try:
        frappe.log_error(title=TITLE, message="action=%s route=%s name=%s" % (
            res.get("action"), res.get("route"), res.get("name")))
    except Exception:
        pass
