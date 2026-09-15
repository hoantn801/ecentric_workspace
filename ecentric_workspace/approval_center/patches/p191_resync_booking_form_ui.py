# Copyright (c) 2026, eCentric and contributors
"""Booking Request: bon van de giao dien Hoan bao 15/09.

1. O BRAND KHONG GIONG SO/PO. Ban cu dung `<input list=datalist>` nen no nam NGOAI
   `ec_formkit` - asset toan site nang moi <select> tu 6 muc tro len thanh combobox co o tim.
   Trinh duyet tu ve mot dropdown khac han: khong tim duoc, khong giong bat ky o nao con lai
   cua ERP. Nay la <select> that; viec go brand MOI thanh mot muc "+ Them brand moi..." o cuoi
   danh sach, mo ra o nhap ten - ro rang hon datalist, vi voi datalist nguoi dung khong bao
   gio biet minh dang go ten moi hay chon ten co san.

2. BANG KOL/KOC "KHONG SU DUNG DUOC". O Kenh co 7 muc nen formkit nang no thanh combobox;
   trong mot o bang rong 15% thi bang tim bung ra de len hang duoi va bi vien bang cat. Nay o
   do tu khai `data-ec-no-formkit` (luat vua mo rong cho <select>, truoc chi co cho o tep).
   Kem theo: o nhap trong bang truoc gio KHONG duoc tao kieu - luat cu chi nham `.fld input`
   ma o trong bang khong nam trong `.fld`, nen chung roi ve mac dinh trinh duyet.
   Them mot dong cong tong ngan sach cac dong va bao khi vuot ngan sach du kien: hai so do
   lech nhau la chuyen hay gap, noi ra luc nhap re hon mot vong tra lai.

3. KHONG CO CHO DINH KEM. DocType da co san truong `request_attachment` va lop dung chung da
   biet nhan `_attachments` - chi thieu o tren man hinh. Them, va KHONG bat buoc.

4. THIEU TIEN TRINH DUYET O DAU FORM. Ban cu la mot danh sach <ol> bang chu o CUOI trang;
   cau hoi "gui xong ai duyet" lai la cau ho hoi TRUOC khi dien. Nay dung dung `renderStepsHTML`
   + `previewSteps` co san cua trang, dat len dau.

Landmark = dieu PHAI CO tren ban song sau khi sync."""
import frappe

from ecentric_workspace.approval_center.features.booking_request.infrastructure import page_sync

_LANDMARKS = ("id=\"f-brand-new\"", "data-ec-no-formkit", "book-att-input", "kol-sum")
# Dau hieu cua BAN CU. Co y KHONG dung chu "datalist": no xuat hien 3 lan trong chinh phan
# chu thich giai thich vi sao bo datalist, nen cong se bao dong gia - dung loi da mac o p176
# (_FORBID khop vao chu thich cua chinh minh, Error Log keu oan suot mot tuan).
# `dsId` la ten bien CHI co trong ban cu: 0 lan trong ban moi.
_FORBID = ("dsId",)


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p191 booking-request sync=%s" % action, "p191 resync")
    if action == "refused":
        frappe.log_error("p191: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p191 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/booking-request"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    if thieu:
        frappe.log_error("p191: trang booking-request thieu dau moc %s" % thieu,
                         "p191 KHONG toi noi")
    con = [m for m in _FORBID if m in html]
    if con:
        frappe.log_error("p191: ban cu van con tren trang: %s" % con, "p191 BAN CU")
