# Copyright (c) 2026, eCentric and contributors
"""Hang so cua popup "Hom nay o eCentric" (PO Hoan chot 29/09/2026)."""

REACTION_DT = "EC Home Reaction"
ANNOUNCEMENT_DT = "EC Home Announcement"

#: 4 nut tha cam xuc - thu tu = thu tu hien. Doi o day thi doi ca Select trong DocType.
REACTION_KINDS = ("heart", "flower", "cake", "party")

#: Sinh nhat: hom nay + 7 ngay toi (PO chot).
BIRTHDAY_DAYS_AHEAD = 7
#: Thong bao khong dat ngay ket thuc: hien 7 ngay ke tu ngay bat dau.
NEWS_DEFAULT_DAYS = 7
#: Nghi le: toi da 3 ngay le trong 200 ngay toi (Tet Nguyen dan thuong cach ~4 thang).
HOLIDAY_DAYS_AHEAD = 200
HOLIDAY_MAX = 3
NEWS_MAX = 8

#: Trang tri trang chu (PO chot 29/09): ca cong ty Nhe, cung phong ban Vua, nguoi sinh nhat Ruc ro.
LEVEL_NONE, LEVEL_LIGHT, LEVEL_DEPT, LEVEL_ME = 0, 1, 2, 3

#: Du lieu dung chung cho moi nguoi (khong phu thuoc ai xem) cache theo ngay.
CACHE_KEY = "ec_home_today:v1:"
CACHE_TTL = 600
#: Ban moi hom nay (goi ham cua chat HR, 1 + N truy van) - cache ngan vi mo cua 08:30.
ONBOARD_TTL = 60
#: celebration() loi -> nho 10 phut: khong ghi Error Log / khong truy van lai MOI lan mo trang chu.
FAIL_TTL = 600

#: Loai thong bao (Select trong EC Home Announcement) -> (lop mau, nhan) tren popup.
NEWS_TAGS = {
    "Tính năng mới": ("mod", "Tính năng mới"),
    "Module mới": ("mod", "Module mới"),
    "Chính sách": ("pol", "Chính sách"),
    "Sự kiện": ("inf", "Sự kiện"),
    "Thông báo": ("inf", "Thông báo"),
}
NEWS_TAG_DEFAULT = ("inf", "Thông báo")
#: Kieu hien "chi anh": moi thong bao thanh MOT o rieng, anh hien full khung ben phai.
DISPLAY_POSTER = "Chỉ ảnh (hiện full)"

WEEKDAYS = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")

#: O "Quay so may man" hien khi co luot quay trong 7 ngay toi (theo doi "Luot quay tiep theo").
DRAW_TILE_DAYS = 7
