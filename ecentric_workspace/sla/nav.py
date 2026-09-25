# Copyright (c) 2026, eCentric and contributors
"""Muc dieu huong cua module SLA. Thuan Python, khong import frappe.

MOT MUC DUY NHAT. Bon tab cua trang /sla la bon cach nhin cung mot bang diem,
khong phai bon diem den - tach chung thanh bon dong tren sidebar se bien mot
cau hoi ("diem cua toi bao nhieu") thanh bon cho phai thu.

DAT TRONG NHOM "Nhan su", ngay sau Phieu luong. Vi tri nay la co y: ba muc
trong nhom do (cham cong, nghi phep, phieu luong) deu la nhung thu NOI VE
CHINH NGUOI DANG DANG NHAP, va diem SLA cung vay. Dat no o nhom Bao cao se
lam no thanh mot bao cao quan tri - tuc la thu nguoi ta doc mot lan roi thoi.
"""

SLA_ITEMS = [
    {
        "key": "sla.scoreboard",
        "label": "Điểm SLA",
        "route": "/sla",
        "icon": "target",
        "group": "Nhân sự",
        "order": 30,
        "active_patterns": ["/sla"],
        "visible_when": "internal",
        "keywords": ["sla", "diem sla", "ti le sla", "dung han", "tre han",
                     "bang diem", "xep hang", "cach tinh sla", "scoreboard"],
        "owner": "sla",
    },
]


def items():
    return list(SLA_ITEMS)
