# Copyright (c) 2026, eCentric and contributors
"""Dua 8 bai huong dan "Quy trinh nhan su" len /huong-dan (23/11/2026, brief HR Agent F).

HAI viec, cung mot lan:
1. /huong-dan/nhan-su (tong quan) + 7 bai: gan-phieu-duyet, phe-duyet-dot-xuat,
   offer-new-staff, nghi-viec-clearance, danh-gia-nhan-su, khao-sat-nhan-su, ky-luat.
   So do luong la ma mermaid trong trang, ve tai trinh duyet bang asset cuc bo
   (public/vendor/mermaid/mermaid.min.js 10.9.1 + public/guides/ec_guide_flow.js) - khong CDN.
2. /huong-dan (muc luc) - sinh lai tu guides.registry (bai chia nhom) + chuyen khoi
   <style id="ec-guides-index-css"> sang asset public/guides/ec_guide.css (A65: khoi cu chi giam).

Idempotent: sync la ghi de tu nguon repo. KHONG nem loi (patch chay trong migrate - bai hoc
p116), khong goi ra ngoai, khong dung du lieu nghiep vu. Thieu landmark -> log, khong dung deploy.
"""
import frappe

_GUIDES = ("nhan_su", "gan_phieu_duyet", "phe_duyet_dot_xuat", "offer_new_staff",
           "nghi_viec_clearance", "danh_gia_nhan_su", "khao_sat_nhan_su", "ky_luat")

#: Landmark chung cua moi bai moi: CSS + mermaid + renderer cuc bo, co so do, duong ve muc luc.
_COMMON = (
    '/assets/ecentric_workspace/guides/ec_guide.css?v=',
    '/assets/ecentric_workspace/vendor/mermaid/mermaid.min.js?v=',
    '/assets/ecentric_workspace/guides/ec_guide_flow.js?v=',
    'class="ecg-flow" data-state="pending"',
    'class="ec-shell-crumblink" href="/huong-dan"',
)

_EXPECT = {
    "huong-dan": (
        'class="ggroup"',                          # muc luc chia nhom
        'href="/huong-dan/nhan-su"',
        'href="/huong-dan/ky-luat"',
        'href="/huong-dan/dnmh-dntt"',             # bai cu van con
        '/assets/ecentric_workspace/guides/ec_guide.css?v=',
    ),
    "huong-dan/nhan-su": _COMMON + ('href="/huong-dan/gan-phieu-duyet"',),
    "huong-dan/gan-phieu-duyet": _COMMON + ('class="ecg-steps"',),
    "huong-dan/phe-duyet-dot-xuat": _COMMON + ('class="ecg-steps"',),
    "huong-dan/offer-new-staff": _COMMON + ('href="/approvals/offer-request"',),
    "huong-dan/nghi-viec-clearance": _COMMON + ('href="/approvals/resignation"',),
    "huong-dan/danh-gia-nhan-su": _COMMON + ('class="ecg-steps"',),
    "huong-dan/khao-sat-nhan-su": _COMMON + ('href="/khao-sat"',),
    "huong-dan/ky-luat": _COMMON + ('class="ecg-steps"',),
}


def execute():
    import importlib
    for key in _GUIDES + ("index",):
        try:
            mod = importlib.import_module("ecentric_workspace.guides.pages.%s.page_sync" % key)
            res = mod.sync() or {}
            frappe.log_error("p470 huong-dan %s sync=%s" % (key, res.get("action")),
                             "p470 huong dan nhan su")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p470 failed %s" % key)
    for route, marks in _EXPECT.items():
        try:
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        except Exception:
            html = ""
        missing = [m for m in marks if m not in html]
        if missing:
            frappe.log_error("p470: route=%s thieu landmark=%s" % (route, missing),
                             "p470 KHONG toi noi")
