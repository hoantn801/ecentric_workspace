# Copyright (c) 2026, eCentric and contributors
"""Bo huong dan nhan su day du tren /huong-dan (24/11/2026, Hoan: "ok xu li di").

BA viec, cung mot lan:
1. 7 bai MOI: tuyen-dung (Tuyen dung tu A-Z: Hiring -> HR tuyen dung -> Offer -> Chuan bi nhan su
   moi -> Onboard -> Thu viec) + 6 bai ngan cho cac loai phieu nhom Nhan su con thieu
   (PROMOTION_REQUEST, LATERAL_MOVE, EMPLOYEE_INFO_UPDATE, EMPLOYEE_REFERRAL, HR_ACTIVITY, BRAND_WEIGHT).
2. Resync 5 bai CO SAN theo thay doi 24/11: nhan-su (tong quan: tien trinh A-Z, bang "Viec cua ban",
   khoi Tom tat "con thieu"), offer-new-staff (ngay onboard: loi gioi thieu, 08:30, 10:00),
   nghi-viec-clearance (00:30 Left + khoa ERP, 00:45 chuyen phieu, M365 do IT), danh-gia-nhan-su,
   ky-luat (sa thai -> Clearance + khoa 00:30).
3. /huong-dan (muc luc) - sinh lai tu guides.registry (them 7 the).

Idempotent: sync la ghi de tu nguon repo. KHONG nem loi (patch chay trong migrate - bai hoc p116),
khong goi ra ngoai, khong dung du lieu nghiep vu. Thieu landmark -> log, khong dung deploy.
"""
import frappe

_NEW = ("tuyen_dung", "thang_chuc_dieu_chinh_luong", "dieu_chuyen_noi_bo", "cap_nhat_thong_tin_nhan_su",
        "gioi_thieu_ung_vien", "hoat_dong_nhan_su", "phan_bo_ty_trong_brand")
_RESYNC = ("nhan_su", "offer_new_staff", "nghi_viec_clearance", "danh_gia_nhan_su", "ky_luat")

#: Landmark chung cua moi bai: CSS + mermaid + renderer cuc bo, co so do, duong ve muc luc.
_COMMON = (
    '/assets/ecentric_workspace/guides/ec_guide.css?v=',
    '/assets/ecentric_workspace/vendor/mermaid/mermaid.min.js?v=',
    '/assets/ecentric_workspace/guides/ec_guide_flow.js?v=',
    'class="ecg-flow" data-state="pending"',
    'class="ec-shell-crumblink" href="/huong-dan"',
    'class="ecg-steps"',
)

_EXPECT = {
    "huong-dan": (
        'href="/huong-dan/tuyen-dung"',
        'href="/huong-dan/phan-bo-ty-trong-brand"',
        'href="/huong-dan/nhan-su"',
    ),
    "huong-dan/tuyen-dung": _COMMON + ('href="/approvals/hiring-request"', "Sửa lời giới thiệu / ngày onboard",
                                       "10:00 ngày onboard"),
    "huong-dan/thang-chuc-dieu-chinh-luong": _COMMON + ('href="/approvals/promotion"',),
    "huong-dan/dieu-chuyen-noi-bo": _COMMON + ('href="/approvals/lateral-move"',),
    "huong-dan/cap-nhat-thong-tin-nhan-su": _COMMON + ('href="/approvals/employee-information-update"',),
    "huong-dan/gioi-thieu-ung-vien": _COMMON + ('href="/approvals/employee-referral"',),
    "huong-dan/hoat-dong-nhan-su": _COMMON + ('href="/approvals/hr-activity"',),
    "huong-dan/phan-bo-ty-trong-brand": _COMMON + ('href="/ec-hr/phan-bo-cong-viec"',),
    "huong-dan/nhan-su": ("Mới từ 24/11", 'href="/huong-dan/tuyen-dung"'),
    "huong-dan/offer-new-staff": ('href="/huong-dan/tuyen-dung"', "Từ 08:30 ngày onboard"),
    "huong-dan/nghi-viec-clearance": ("00:45 sáng sau ngày cuối", "Microsoft 365"),
    "huong-dan/danh-gia-nhan-su": ('href="/huong-dan/tuyen-dung"',),
    "huong-dan/ky-luat": ("Quyết định <b>sa thải</b>",),
}


def execute():
    import importlib
    for key in _NEW + _RESYNC + ("index",):
        try:
            mod = importlib.import_module("ecentric_workspace.guides.pages.%s.page_sync" % key)
            res = mod.sync() or {}
            frappe.log_error("p550 huong-dan %s sync=%s" % (key, res.get("action")),
                             "p550 huong dan nhan su day du")
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p550 failed %s" % key)
    for route, marks in _EXPECT.items():
        try:
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        except Exception:
            html = ""
        missing = [m for m in marks if m not in html]
        if missing:
            frappe.log_error("p550: route=%s thieu landmark=%s" % (route, missing),
                             "p550 KHONG toi noi")
