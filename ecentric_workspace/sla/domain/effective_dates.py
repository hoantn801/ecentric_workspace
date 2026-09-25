# Copyright (c) 2026, eCentric and contributors
"""Tu ngay nao thi mot nhom bat dau duoc cham diem. Thuan - khong import frappe.

Chu so huu chot 17/09/2026, va moi nhom mot moc khac nhau:

    Cham cong              01/09/2026   do luon ca thang 9
    Phan hoi phe duyet     21/09/2026
    RSVP lich hop          21/09/2026
    Bao cao tuan           21/09/2026
    Cong viec              21/09/2026   (van ngoai %SLA)

VI SAO CHAM CONG DUOC TINH HOI TO MA NHUNG NHOM KIA THI KHONG: luat cham cong
truoc 10:00 da chay tren ban song tu lau, co nhac 08:30 va 09:30 moi ngay. Moi
nguoi da biet luat va da song voi no ca thang - do lai thang 9 khong bat ai phai
chiu mot cai han ho chua tung nghe. Con han phan hoi phe duyet thi vua duoc cau
hinh ngay 16/09; ap nguoc lai se cham `Missed` cho nhung buoc ma luc do KHONG
he co han nao ca.

TAI SAO SO SANH THEO `opened_at` CHU KHONG PHAI `due_at`: nghia vu PHAT SINH luc
mo, va `period_month` cung duoc chot theo luc mo. Dung hai moc khac nhau cho
"thuoc ky nao" va "co duoc tinh khong" se tao ra nhung dong thuoc ky thang 9
nhung lai bi loai theo moc thang 10 - khong ai giai thich noi.

21/09/2026 la thu Hai, nen ranh gioi nay khong cat ngang mot tuan bao cao nao:
tuan 14-19/09 bi loai tron ven, tuan 21-26/09 duoc tinh tron ven.
"""
import datetime


def _as_date(v):
    """Chuan hoa ve `date`. Nhan date, datetime, hoac chuoi ISO."""
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        s = v.strip().replace("T", " ")
        return datetime.date.fromisoformat(s.split(" ")[0])
    raise ValueError("gia tri ngay khong ho tro: %r" % (v,))


def is_before_start(opened_at, effective_from):
    """Nghia vu mo luc `opened_at` co nam TRUOC ngay bat dau ap dung khong?

    Ngay bat dau duoc TINH (>=), khong bi loai. Mot moc "tu 21/09" ma lai loai
    ca ngay 21/09 la kieu lech mot ngay khong ai doc code cung phat hien, va no
    lam ca cong ty mat hoac duoc them dung mot ngay diem.

    Khong co moc -> khong loai gi (tra ve False). Fail-safe theo huong DO: mot
    cau hinh thieu khong duoc bien thanh mot thang khong ai bi do.
    """
    if effective_from is None:
        return False
    opened = _as_date(opened_at)
    if opened is None:
        return False
    return opened < _as_date(effective_from)
