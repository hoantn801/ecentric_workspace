# Copyright (c) 2026, eCentric and contributors
"""Form GBS SO / PO: HTML server ve DUNG trang thai cuoi, het "nhieu lop" - 29/09/2026.

Brief NHIEU_LOP/brief_gbs.md (chat Trang chu/Shell). Do bang NHIEU_LOP/do_lop_trang.js truoc khi sua:
  - /gbs-so-form-v2: gone 30, mv 2 (#title 150 px, #cpBody 25), api 26 (get_csrf x3, web_lookup x4,
    gbs_list x4, gbs_list_so_lookups x2), 24 khoi chen;
  - /gbs-po-form-v2: gone 33, mv 3 (#campaignNo 443 px, #title 86, #cpBody 25), api 29 (get_csrf x3,
    web_lookup x4, gbs_list x6, gbs_list_po_lookups x2), 24 khoi chen.

Sua o NGUON trang (A65), khong them <script id="ec-..."> moi:
  - thanh chon che do, o Muc uu tien, khung combobox (.ec-cb), khung MSO (SO), khung NCC EC (PO), o
    Store + 2 o ngay, cot UOM / VAT, o Kho mac dinh (PO), khung chain: nam san trong markup;
  - che do (SO direct/gbsrev, PO ecbuy/gbsbuy) tinh 1 lan o dau trang -> <html data-ec-*-mode>; CSS ve
    dung che do ngay lan dau; phan chi thuoc 1 che do an bang CSS thay vi JS an/doi cho sau khi tai;
  - CSS truoc day 9-10 block chen vao <head> luc chay: gom ve 1 <style> dau trang;
  - get_csrf / gbs_list_*_lookups / web_lookup brand con 1 lan; web_lookup client nap khi chon brand;
    4-5 danh sach boxme chi nap o che do GBS (gom 1 lan goi khi server gbs_list nhan `entities`);
  - bo 4 block chet cua sidebar cu (ACTIVE-MENU-JS, fillUser, ec-userinfo-fix(+css), ec-form-userfill).
Do lai (HTML moi chay trong khung an tren trang live, cung cach do cho ra dung so ban cu):
  SO gone 2 / mv 0 / api 16-20, PO gone 2 / mv 0 / api 17-22; 2 tu con lai la the ten nguoi dung cua menu.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = {
    "gbs-so-form-v2": (
        'data-ec-so-mode',                  # che do dat truoc khi ve
        '<div id="ec-pri-wrap"',            # o Muc uu tien nam san
        'id="ecMsoPanel"',                  # khung MSO nam san
    ),
    "gbs-po-form-v2": (
        'data-ec-po-mode',
        '<div id="ec-pri-wrap"',
        'id="ecPoWrap"',                    # khung NCC (EC) + SO tham chieu nam san
    ),
}


def execute():
    from ecentric_workspace.legacy_pages.gbs_so_form_v2 import page_sync as gbs_so
    from ecentric_workspace.legacy_pages.gbs_po_form_v2 import page_sync as gbs_po

    for route, mod in (("gbs-so-form-v2", gbs_so), ("gbs-po-form-v2", gbs_po)):
        try:
            res = mod.sync()
            action = (res or {}).get("action")
            frappe.log_error("p223 %s sync=%s" % (route, action), "p223 gbs form nhieu lop")
            if action == "refused":
                frappe.log_error(
                    "p223 %s: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                    "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha trong "
                    "ket qua roi them vao SUPERSEDES_SHA256." % route, "p223 REFUSED")
                continue
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            missing = [m for m in _EXPECT[route] if m not in html]
            if missing:
                frappe.log_error("p223 %s: thieu landmark=%s" % (route, missing), "p223 KHONG toi noi")
        except Exception:
            # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
            frappe.log_error(frappe.get_traceback(), "p223 %s failed" % route)
