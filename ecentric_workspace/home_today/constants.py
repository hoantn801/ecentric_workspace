# Copyright (c) 2026, eCentric and contributors
"""Hang so cua popup "Hom nay o eCentric" (PO Hoan chot 29/09/2026)."""

REACTION_DT = "EC Home Reaction"
NEWS_DT = "News Post"
POLICY_DT = "Company Policy"

#: 4 nut tha cam xuc - thu tu = thu tu hien. Doi o day thi doi ca Select trong DocType.
REACTION_KINDS = ("heart", "flower", "cake", "party")

#: Sinh nhat: hom nay + 7 ngay toi (PO chot).
BIRTHDAY_DAYS_AHEAD = 7
#: Tin noi bo tich "Dua len popup" ma khong dat ngay het: hien 7 ngay tu ngay dang.
NEWS_DEFAULT_DAYS = 7
#: Chinh sach tu len popup 7 ngay ke tu ngay hieu luc (PO chot, khong can tich).
POLICY_DAYS = 7
#: Nghi le: toi da 3 ngay le trong 200 ngay toi (Tet Nguyen dan thuong cach ~4 thang).
HOLIDAY_DAYS_AHEAD = 200
HOLIDAY_MAX = 3
NEWS_MAX = 5

#: Trang tri trang chu (PO chot 29/09): ca cong ty Nhe, cung phong ban Vua, nguoi sinh nhat Ruc ro.
LEVEL_NONE, LEVEL_LIGHT, LEVEL_DEPT, LEVEL_ME = 0, 1, 2, 3

#: Du lieu dung chung cho moi nguoi (khong phu thuoc ai xem) cache theo ngay.
CACHE_KEY = "ec_home_today:v1:"
CACHE_TTL = 600
#: Ban moi hom nay (goi ham cua chat HR, 1 + N truy van) - cache ngan vi mo cua 08:30.
ONBOARD_TTL = 60
#: celebration() loi -> nho 10 phut: khong ghi Error Log / khong truy van lai MOI lan mo trang chu.
FAIL_TTL = 600

#: Nhan the tin. News Post.category (site) -> nhan hien tren popup.
NEWS_TAGS = {
    "MODULE MỚI": ("mod", "Module mới"),
    "CHÍNH SÁCH": ("pol", "Chính sách"),
}
NEWS_TAG_DEFAULT = ("inf", "Thông báo")
POLICY_TAG = ("pol", "Chính sách")

WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")
