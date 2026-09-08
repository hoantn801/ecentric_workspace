# Copyright (c) 2026, eCentric and contributors
"""Nguoi xu ly tai len duoc tep ket qua - 6 form co buoc xu ly (09/09, Hoan).

`/api/method/upload_file` co kem `doctype` + `docname` thi Frappe kiem quyen GHI tren chinh
ho so. Ca sau DocType nay chi cho System Manager ghi (rieng EC Asset Request co them
EC Ops System), trong khi nguoi xu ly that - Dong, Linh Vuong, Thuong, Tuan - khong ai co
System Manager. Ket qua: 5/6 form khong ai tai duoc tep ket qua, man hinh chi hien "Loi tai"
tron nen khong ai biet la 403. Dong bao 08/09 tren AI Topup; ra soat ra ca nhom cung dinh.

Sua theo dung cach Payment Request lam tu dau (nen no khong he dinh): tai len KHONG kem
doctype/docname -> file mo coi; server gan vao ho so luc "Hoan tat xu ly" bang
`attach_extra_files`, tuc duong da kiem quyen san (chi nguoi da nhan xu ly hoac quan tri).

Cung dot:
  * Loi tai gio noi RO LY DO tu server (va bat rieng 413 - tep qua lon). Chinh cai thong bao
    tron la thu khien ca nay phai cho toi khi nguoi dung chup man hinh gui len moi biet.
  * document_request truoc day upload voi doctype "EC Data Request" - chep nham ten DocType.
    Bo doctype la het, va go luon bien chet `DT` con sot lai.

KHONG cap them quyen cho ai: nhom duoc phep hoan tat van y nguyen.
Patch moi vi cac patch resync truoc da chay tren production. Tu VERIFY landmark tung trang.
"""
import frappe

_PAGES = (
    ("ai_topup", "approvals/ai-topup"),
    ("asset_request", "approvals/asset-request"),
    ("data_request", "approvals/data-request"),
    ("document_request", "approvals/document-request"),
    ("resignation", "approvals/resignation"),
    ("system_request", "approvals/system-request"),
)


def execute():
    missing = []
    for feature, route in _PAGES:
        mod = frappe.get_module(
            "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
        res = mod.sync()
        frappe.log_error("p164 %s sync=%s" % (feature, (res or {}).get("action")), "p164 resync")
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        # Landmark = dieu PHAI BIEN MAT. Trang nao con gui doctype khi upload la chua nhan ban moi.
        if 'fd.append("doctype"' in html:
            missing.append("%s (action=%s)" % (route, (res or {}).get("action")))
    if missing:
        raise Exception("p164: cac trang sau van con gui doctype khi upload: " + " | ".join(missing))
