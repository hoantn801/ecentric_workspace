# Copyright (c) 2026, eCentric and contributors
"""Mot NGAY cua mot nguoi dan toi nghia vu cham cong nao. Thuan - khong import frappe.

Han cham cong la 10:00, da chay tren ban song tu lau: `hr/checkin_reminder.py`
nhac luc 08:30 (kem Teams) va 09:30, ca hai deu ghi "cham cong truoc 10:00".
Module SLA khong dat ra luat moi - no doc lai dung luat do.

MOT NGAY LA MOT DAU VIEC. Check-in va check-out la hai dieu kien cua cung mot
ngay cong, khong phai hai dau viec. Neu tach doi thi nhom cham cong se chiem gap
doi mau so so voi cac nhom khac, va %SLA cua ca cong ty se bi mot nhom keo di.

THU TU KIEM TRA O DAY LA CO Y, khong phai tuy tien:

    chua vao lam  ->  cuoi tuan  ->  ngay le  ->  nghi phep  ->  da cham  ->  chua cham

Ba buoc dau BO HAN, khong tao ban ghi: khong ai mong doi mot dong "ngay cong"
cho Chu nhat. Buoc nghi phep thi TAO ban ghi roi loai tru - vi nguoi ta CAN
nhin thay dong do tren trang /sla de biet he thong da ghi nhan phep cua minh,
chu khong phai doan xem tai sao thang nay thieu mat mot ngay.

NGHI PHEP THANG CA KHI DA CO DAU CHAM CONG. Nguoi duoc duyet nghi ma van vao
lam thi ngay do khong phat sinh nghia vu - loai tru la trung tinh, khong cong
vao tu so lan mau so. Cham thanh "dung han" se cho ho mot diem mien phi cho mot
ngay ho khong he co nghia vu.
"""
import datetime

# Thu Hai (0) den thu Sau (4). Chu so huu chot 17/09/2026.
# Ai lam ca cuoi tuan thi nhung ngay do khong duoc do - chap nhan, vi phuong an
# kia (do moi ngay khong nam trong lich nghi) se cham `Missed` cho ca cong ty
# vao thu Bay neu mot Holiday List nao do quen khai cuoi tuan.
WORKDAYS = (0, 1, 2, 3, 4)

ACT_SKIP = "skip"        # khong tao ban ghi nao
ACT_EXCLUDE = "exclude"  # tao ban ghi, khong cham diem, co ly do nhin thay duoc
ACT_OPEN = "open"        # con no - qua 10:00 ma chua cham thi thanh Missed
ACT_CLOSE = "close"      # da cham, so moc cham voi han

REASON_BEFORE_JOIN = "chưa vào làm"
REASON_WEEKEND = "cuối tuần"
REASON_HOLIDAY = "ngày nghỉ lễ"
REASON_LEAVE = "Nghỉ phép đã được duyệt"
REASON_DONE = "đã chấm công"
REASON_PENDING = "chưa chấm công"


def _as_date(v):
    if v is None:
        return None
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    if isinstance(v, str):
        return datetime.date.fromisoformat(v.strip().replace("T", " ").split(" ")[0])
    raise ValueError("gia tri ngay khong ho tro: %r" % (v,))


def decide(day, joined_on=None, holidays=None, on_leave=False, first_checkin=None,
           workdays=WORKDAYS):
    """Tra ve (hanh_dong, moc_dong, ly_do).

    `holidays` la tap cac `date` nghi le CUA CHINH NGUOI DO (Holiday List rieng),
    khong phai mot lich chung - dung lich chung se cham sai cho bat ky ai co lich
    nghi khac.

    `first_checkin` la dau cham cong SOM NHAT trong ngay. Lay som nhat chu khong
    phai muon nhat: nguoi cham luc 9:00 roi cham lai luc 14:00 van la cham dung
    gio, va lay moc muon se bien ho thanh tre.
    """
    d = _as_date(day)
    if d is None:
        return ACT_SKIP, None, "không rõ ngày"

    joined = _as_date(joined_on)
    if joined and d < joined:
        return ACT_SKIP, None, REASON_BEFORE_JOIN
    if d.weekday() not in workdays:
        return ACT_SKIP, None, REASON_WEEKEND
    if holidays and d in holidays:
        return ACT_SKIP, None, REASON_HOLIDAY
    if on_leave:
        return ACT_EXCLUDE, None, REASON_LEAVE
    if first_checkin:
        return ACT_CLOSE, first_checkin, REASON_DONE
    return ACT_OPEN, None, REASON_PENDING


def workdays_between(start, end, holidays=None, workdays=WORKDAYS):
    """Cac ngay CO nghia vu cham cong trong khoang [start, end], da tru cuoi tuan
    va ngay le. Dung de dung lai thang 9 va de dem do phu."""
    start, end = _as_date(start), _as_date(end)
    holidays = holidays or set()
    out, d = [], start
    while d <= end:
        if d.weekday() in workdays and d not in holidays:
            out.append(d)
        d += datetime.timedelta(days=1)
    return out
