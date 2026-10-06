# Copyright (c) 2026, eCentric and contributors
"""Dua bai huong dan "Chot cong thang va phan bo cong viec" len /huong-dan (01/10/2026).

HAI viec, cung mot lan:
1. /huong-dan/chot-cong-thang - bai moi (anh chup man hinh nhung base64 luc sync).
2. /huong-dan                 - muc luc sinh lai tu guides.registry de co the bai moi.
   Tep main_section.html cua muc luc KHONG doi (the bai sinh luc sync tu {{guides_list}}),
   nen manifest khong doi cho muc luc - nhung trang live van phai sync lai.

Popup "Hom nay o eCentric" tro toi bai nay (thong bao EC Home Announcement dang tay,
khong nam trong patch). Idempotent: sync la ghi de tu nguon repo.
"""
import frappe

_EXPECT = {
    "huong-dan": (
        'class="gcards"',
        'href="/huong-dan/chot-cong-thang"',     # bai moi co mat trong muc luc
        'href="/huong-dan/dnmh-dntt"',           # bai cu van con
    ),
    "huong-dan/chot-cong-thang": (
        'data:image/jpeg;base64,',               # anh da nhung, khong phai link gay
        'class="deadline"',                      # hop han chot
        'class="ec-shell-crumblink" href="/huong-dan"',
        'href="/ec-hr/phan-bo-cong-viec"',
    ),
}


def execute():
    from ecentric_workspace.guides.pages.chot_cong_thang import page_sync as guide_sync
    from ecentric_workspace.guides.pages.index import page_sync as index_sync
    for name, mod in (("chot-cong-thang", guide_sync), ("index", index_sync)):
        try:
            res = mod.sync() or {}
            frappe.log_error("p239 huong-dan %s sync=%s" % (name, res.get("action")),
                             "p239 huong dan chot cong")
        except Exception:
            # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
            frappe.log_error(frappe.get_traceback(), "p239 failed %s" % name)
    for route, marks in _EXPECT.items():
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        missing = [m for m in marks if m not in html]
        if missing:
            frappe.log_error("p239: route=%s thieu landmark=%s" % (route, missing),
                             "p239 KHONG toi noi")
