# Copyright (c) 2026, eCentric and contributors
"""Loi vao huong dan tren the: tu goc TREN phai xuong HANG CHAN, canh nut CTA.

Y Hoan sau khi nhin ban p161 tren prod: goc tren phai da co nhan trang thai
("Dang hoat dong"), nhet them mot dau ? tron vao do thi chat va xau. O hang chan,
ben phai nut "Tao yeu cau", no doc duoc thanh mot cau: tao yeu cau... hay xem
huong dan truoc. Kem theo doi hinh: vong tron + chu "Huong dan" thay vi mot dau
? tran - dau ? mot minh khong noi ro no dan di dau.
"""
import frappe

from ecentric_workspace.approval_center.ui.hub import page_sync as hub_sync

_EXPECT = ('class="card-foot"', 'class="card-help"', "c.guide_route")
#: dau vet cua ban cu - con lai tuc la sync khong toi noi
_FORBID = ('class="card-top-r"',)


def execute():
    res = hub_sync.sync()
    frappe.log_error("p162 hub sync=%s" % (res or {}).get("action"), "p162 hub guide link")
    html = frappe.db.get_value("Web Page", {"route": "approvals"}, "main_section_html") or ""
    missing = [m for m in _EXPECT if m not in html]
    left = [m for m in _FORBID if m in html]
    if missing or left:
        raise Exception("p162: /approvals thieu=%s con-sot=%s (action=%s)"
                        % (missing, left, (res or {}).get("action")))
