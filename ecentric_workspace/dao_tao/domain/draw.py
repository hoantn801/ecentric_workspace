# Copyright (c) 2026, eCentric and contributors
"""Quay so tuan (Hoan chot 12/11/2026 toi). Thuan Python.

  * MOI VE = MOT LUOT RIENG: ai co 3 ve thi giu 3 so, trung duoc nhieu qua.
  * Nguoi choi tu chon so trong dai 1..N (khong trung). Toi gio khoa (truoc gio quay 5 phut),
    ve nao chua chon so thi may chon giup mot so con trong.
  * Quay KHONG LAP trong CA DAI 1..N, tu giai NHO toi giai LON: so co nguoi giu -> nguoi do
    trung; so khong ai giu -> qua DE LAI (khong trao, khong don sang tuan sau).
  * Gio quay mac dinh 16:00 thu Sau, Ban dao tao doi duoc; qua cai theo dong (ten + so luong)
    giong /khao-sat.
Cung luat voi so may man cua /khao-sat (surveys/domain/rewards.py lucky_draw) nhung viet lai o
day de hai module khong phu thuoc nhau (frappe-rules muc 3).
"""
import datetime

from ecentric_workspace.dao_tao.domain.errors import FieldErrors, QuizError

RANGE_DEFAULT = 100
RANGE_MIN = 10
RANGE_MAX = 999
LOCK_BEFORE_MIN = 5
MAX_PRIZE_ROWS = 20
MAX_PRIZE_QTY = 50
DRAW_WEEKDAY = 4          # thu Sau
DRAW_HOUR = 16


def default_draw_at(week_start):
    d = week_start + datetime.timedelta(days=DRAW_WEEKDAY)
    return datetime.datetime(d.year, d.month, d.day, DRAW_HOUR, 0)


def lock_at(draw_at):
    return draw_at - datetime.timedelta(minutes=LOCK_BEFORE_MIN)


def clean_prizes(raw):
    """[{label, quantity}] -> [{id, label, quantity}] (dong dau = giai lon nhat)."""
    if not isinstance(raw, list):
        raise QuizError("Danh sách quà không hợp lệ.")
    out, errs = [], {}
    for i, r in enumerate(raw[:MAX_PRIZE_ROWS]):
        if not isinstance(r, dict):
            continue
        label = " ".join(str(r.get("label") or "").split())[:60]
        try:
            qty = int(r.get("quantity") or 0)
        except (TypeError, ValueError):
            qty = 0
        if not label and not qty:
            continue
        if not label:
            errs["prize%d" % (i + 1)] = "Quà cần tên."
        elif not 1 <= qty <= MAX_PRIZE_QTY:
            errs["prize%d" % (i + 1)] = "Số lượng từ 1 đến %d." % MAX_PRIZE_QTY
        out.append({"id": "p%d" % (len(out) + 1), "label": label, "quantity": qty})
    if errs:
        raise FieldErrors("Còn dòng quà chưa đúng.", errs)
    return out


def clean_range(v):
    try:
        n = int(v)
    except (TypeError, ValueError):
        raise FieldErrors("Dải số không hợp lệ.", {"range": "Nhập số từ %d đến %d." % (RANGE_MIN, RANGE_MAX)})
    if not RANGE_MIN <= n <= RANGE_MAX:
        raise FieldErrors("Dải số không hợp lệ.", {"range": "Nhập số từ %d đến %d." % (RANGE_MIN, RANGE_MAX)})
    return n


def draw_order(prizes):
    """Tu giai NHO toi giai LON, moi phan qua mot luot: [(prize_id, rank)]."""
    out = []
    for rank, p in reversed(list(enumerate(prizes, start=1))):
        out.extend([(p["id"], rank)] * int(p.get("quantity") or 0))
    return out


def lucky_draw(prizes, holders, top, rng):
    """holders {so: user}. -> [{prize, rank, number, user|None}] theo thu tu quay."""
    order = draw_order(prizes)
    nums = rng.sample(range(1, int(top) + 1), min(len(order), int(top)))
    return [{"prize": pid, "rank": rank, "number": n, "user": holders.get(n)}
            for (pid, rank), n in zip(order, nums)]


def assign_missing(top, taken, needs, rng):
    """needs = [(user, slot)] chua co so. -> {so: (user, slot)} tu cac so con trong (het so thi
    ve con lai khong co so - trang quan ly canh bao khi dai so nho hon tong so ve)."""
    free = [n for n in range(1, int(top) + 1) if n not in taken]
    rng.shuffle(free)
    return dict(zip(free, sorted(needs)))


def format_number(n, top=RANGE_DEFAULT):
    return str(int(n)).zfill(max(2, len(str(int(top or 0)))))
