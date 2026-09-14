# Copyright (c) 2026, eCentric and contributors
"""De nghi thanh toan: ky ghi nhan chi phi + VAT + brand ngoai danh muc - 12/09, Hoan chot.

BA VIEC, deu de PnL doc chi phi cho dung:

1. `ec_ky_chi_phi` (Date) - THANG HOAT DONG phat sinh khoan chi, khong phai thang tra tien.
   Truoc dot nay PnL quy ky theo `payment_date`, va so lieu cho thay hau qua: 49/49 phieu dau
   tien deu roi vao thang 9 du nhieu khoan la chi phi cua thang 8, con thang 7-8 khong co mot
   dong chi phi nha cung cap nao. Chi phi luon lech pha mot thang so voi doanh thu, nen bien
   loi nhuan cua mot thang khong bao gio dung. Form tu dien san theo ngay thanh toan roi cho
   sua, nen bat buoc truong nay khong ton them thao tac cua ai.

2. `ec_vat_pct` (Select 0/8/10) - `payment_amount` la so THUC TRA, gom VAT; so ke toan ghi chi
   phi thuan. Khong tach ra thi ERP cao hon so mot cach co he thong 8-10% voi moi nha cung cap
   co hoa don. Mac dinh 0 nen moi phieu da co giu nguyen gia tri cu.

3. `ec_brand_moi` + `ec_brand_ten` - chi cho brand ngoai danh muc, lam dung khuon Booking
   Request (`tao_brand_moi`), ke ca `ec_can_chuan_hoa = 1` de admin ra lai chinh ta va gop
   trung. KHAC booking mot diem co chu dich: khong bat chon nguoi phu trach, vi de nghi thanh
   toan khong biet ai phu trach brand - bat them chi khien nguoi ta chon bua.
   Chi phi DUNG CHUNG nhieu brand thi van gan brand `EC` nhu moi nguoi dang lam san; khong
   them o tich nao cho viec do (Hoan 12/09: "trong Brand co ecentric => chinh la cong ty roi").

Bon truong nam trong fixtures/custom_field.json nen migrate tu tao. Chung deu KHONG bat buoc o
tang DocType - rang buoc nam o validate_payment, de phieu cu khong bi chan khi mo lai.

Cung phai them vao `editable_fields` trong domain/definition.py: thieu o do thi form gui len
bao nhieu cung bi bo im lang.
"""
import frappe

_EXPECT = (
    'data-model="ec_ky_chi_phi"',     # o chon ky ghi nhan
    'data-model="ec_vat_pct"',        # o chon thue suat
    'data-model="ec_brand_moi"',      # o tich brand ngoai danh muc
    'Tháng HOẠT ĐỘNG',                # cau giai thich, de chac markup moi da toi noi
)


def execute():
    from ecentric_workspace.approval_center.features.payment_request.infrastructure import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p182 payment_request sync=%s" % action, "p182 ky chi phi")
        if action == "refused":
            frappe.log_error(
                "p182: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang KHONG duoc cap nhat. Doi chieu live_sha "
                "trong ket qua roi them vao SUPERSEDES_SHA256.", "p182 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "approvals/payment-request"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p182: thieu landmark=%s" % (missing,), "p182 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p182 failed")
