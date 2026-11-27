# Copyright (c) 2026, eCentric and contributors
"""Dua bai huong dan "Hop dong" (form 27 Contract Review) len /huong-dan (22/11/2026).

HAI viec, cung mot lan:
1. /huong-dan/hop-dong - bai moi: so do quy trinh theo vai tro (goi dinh dang ISO
   guides/pages/hop_dong/quy_trinh.json, ve bang ec_iso_docs.js nhu trang /tai-lieu/<ma>).
2. /huong-dan          - muc luc sinh lai tu guides.registry de co the bai moi.
   Tep main_section.html cua muc luc KHONG doi (the bai sinh luc sync tu {{guides_list}}),
   nen manifest khong doi cho muc luc - nhung trang live van phai sync lai.

Icon "?" tren the form 27 o /approvals tu hien: catalog doc guides.registry (CONTRACT_REVIEW),
khong can sua trang hub. Idempotent: sync la ghi de tu nguon repo. Loi -> Error Log, KHONG nem
(patch nem = migrate dung lai).
"""
import frappe

_EXPECT = {
    "huong-dan": (
        'class="gcards"',
        'href="/huong-dan/hop-dong"',            # bai moi co mat trong muc luc
        'href="/huong-dan/dnmh-dntt"',           # bai cu van con
    ),
    "huong-dan/hop-dong": (
        "data-eti-flow",                         # so do theo vai tro
        "ec_iso_docs.js",                        # dung bo ve cua Thu vien ISO
        'data-r="KT"',                           # chip vai tro Ke toan
        'class="ec-shell-crumblink" href="/huong-dan"',
        'href="/approvals/contract-review"',
    ),
}


def execute():
    from ecentric_workspace.guides.pages.hop_dong import page_sync as guide_sync
    from ecentric_workspace.guides.pages.index import page_sync as index_sync
    for name, mod in (("hop-dong", guide_sync), ("index", index_sync)):
        try:
            res = mod.sync() or {}
            frappe.log_error("p553 huong-dan %s sync=%s" % (name, res.get("action")),
                             "p553 huong dan hop dong")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p553 failed %s" % name)
    for route, marks in _EXPECT.items():
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        missing = [m for m in marks if m not in html]
        if missing:
            frappe.log_error("p553: route=%s thieu landmark=%s" % (route, missing),
                             "p553 KHONG toi noi")
