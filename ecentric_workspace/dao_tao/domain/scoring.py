# Copyright (c) 2026, eCentric and contributors
"""Tinh diem mot cau + chuoi dung + co tra loi nhanh. Thuan Python.

Luat (Hoan chot, mockup F1 "Luat choi"):
  * Theo toc do: tra loi ngay = 1.000 diem, sat het gio = 500 (tuyen tinh). Tat "tinh theo toc
    do" -> dung la 1.000.
  * Dung mot phan (thanh truot lech xa, ghep cap dung vai cap) -> diem x ti le.
  * Chuoi dung: tu cau dung thu 2 lien tiep +100, toi da +500. Dung mot phan KHONG noi chuoi.
  * Cau cuoi nhan doi (neu bat) - nhan ca diem thuong chuoi.
  * Thoi gian tinh tu luc SERVER mo cau (`opened_at`) toi luc SERVER nhan cau tra loi - dong
    ho tren may chi de nhin.
"""
from ecentric_workspace.dao_tao import constants as C


def speed_points(elapsed_ms, limit_ms, by_speed=True):
    if not by_speed or limit_ms <= 0:
        return C.POINTS_MAX
    frac = min(max(float(elapsed_ms) / float(limit_ms), 0.0), 1.0)
    return int(round(C.POINTS_MAX - (C.POINTS_MAX - C.POINTS_MIN) * frac))


def score_answer(ratio, elapsed_ms, limit_ms, prev_streak, is_last, settings):
    """-> dict(points, correct, streak). ratio None (cau khong cham) -> 0 diem, chuoi giu nguyen."""
    if ratio is None:
        return {"points": 0, "correct": None, "streak": prev_streak, "bonus": 0}
    correct = ratio >= 1.0
    base = int(round(speed_points(elapsed_ms, limit_ms, settings.get("by_speed", True)) * ratio))
    streak = prev_streak + 1 if correct else 0
    bonus = 0
    if correct and settings.get("streak", True) and streak >= 2:
        bonus = min(C.STREAK_BONUS * (streak - 1), C.STREAK_BONUS_MAX)
    pts = base + bonus
    if is_last and settings.get("last_double", True):
        pts *= C.LAST_DOUBLE
    return {"points": pts if ratio > 0 else 0, "correct": correct, "streak": streak, "bonus": bonus}


def miss(prev_streak):
    """Khong tra loi cau co cham diem -> 0 diem, mat chuoi."""
    return {"points": 0, "correct": False, "streak": 0, "bonus": 0}


def fast_flag(history):
    """history = [(elapsed_ms, correct), ...] theo thu tu cau. True khi co FAST_STREAK cau DUNG
    lien tiep, moi cau duoi FAST_MS. Chi gan co de nguoi dan xem - khong tu tru diem."""
    run = 0
    for ms, ok in history:
        if ok and ms is not None and ms < C.FAST_MS:
            run += 1
            if run >= C.FAST_STREAK:
                return True
        else:
            run = 0
    return False
