# Copyright (c) 2026, eCentric and contributors
"""Loi vao huong dan tren the: O VUONG BO GOC chua mot dau "?", bo chu "Huong dan".

Y Hoan 09/09 sau khi nhin ban p162 tren prod: chu "Huong dan" nam canh nut "Tao
yeu cau" lam hang chan nang; mot o vuong nho co dau ? la du. Chu giai chuyen han
vao title/aria-label - mot dau ? tran khong tu noi duoc no dan di dau, nen no
khong duoc mat phan giai thich, chi la giai thich khi ro chuot / khi trinh doc man
hinh doc toi.

Kem theo: bo han SVG viet tay o cho nay. Ban SVG dau tien quen class="icon" (noi
trang khai fill:none / stroke:currentColor) nen tren prod no ra mot CHAM TRON DEN
DAC - mot loi chi mat nhin ra, test headless khong thay. Mot ky tu "?" trong o
vuong khong co cach nao hong kieu do.
"""
import frappe

from ecentric_workspace.approval_center.ui.hub import page_sync as hub_sync

_EXPECT = ('class="card-help"', 'aria-label="Xem hướng dẫn">?</a>')
#: dau vet cua ban truoc - con lai tuc la sync khong toi noi
_FORBID = ("</svg>Hướng dẫn</a>",)


def execute():
    res = hub_sync.sync()
    frappe.log_error("p164 hub sync=%s" % (res or {}).get("action"), "p164 hub help button")
    html = frappe.db.get_value("Web Page", {"route": "approvals"}, "main_section_html") or ""
    missing = [m for m in _EXPECT if m not in html]
    left = [m for m in _FORBID if m in html]
    if missing or left:
        raise Exception("p164: /approvals thieu=%s con-sot=%s (action=%s)"
                        % (missing, left, (res or {}).get("action")))
