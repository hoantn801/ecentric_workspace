# Copyright (c) 2026, eCentric and contributors
"""Luat choi cua mot bo quiz (mockup F1 "Luat choi" + "Kieu thi" + "Muc bao ve"). Thuan Python."""
from ecentric_workspace.dao_tao import constants as C

DEFAULTS = {
    "mode": C.MODE_SOLO,            # ca nhan | ca nhan + duong dua phong ban
    "show_on_phone": True,          # bat = kieu Quizizz; tat = chi o mau, nhin may chieu
    "same_order": True,             # dien thoai giu dung thu tu + mau dap an nhu may chieu (Hoan 13/11)
    "by_speed": True,               # 1.000 -> 500 theo toc do
    "streak": True,                 # chuoi dung +100, toi da +500
    "last_double": True,            # cau cuoi nhan doi
    "board": C.BOARD_EACH,          # bang xep hang moi cau / moi 5 cau / cuoi game
    "guard": C.GUARD_STANDARD,      # muc bao ve
    "allow_nick": True,             # cho dat ten trong game
    "allow_avatar": True,           # cho trang tri nhan vat
}


def _bool(v, default):
    if v is None:
        return default
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "on")
    return bool(v)


def clean_settings(raw):
    raw = raw if isinstance(raw, dict) else {}
    out = dict(DEFAULTS)
    if raw.get("mode") in C.MODES:
        out["mode"] = raw["mode"]
    if raw.get("board") in C.BOARD_MODES:
        out["board"] = raw["board"]
    if raw.get("guard") in C.GUARD_LEVELS:
        out["guard"] = raw["guard"]
    for k in ("show_on_phone", "same_order", "by_speed", "streak", "last_double", "allow_nick", "allow_avatar"):
        out[k] = _bool(raw.get(k), DEFAULTS[k])
    return out


def shuffles_options(s):
    """Xao dap an tung nguoi: muc Chuan tro len VA dien thoai co hien cau hoi (che do "chi o mau"
    thi moi nguoi phai nhin cung mot thu tu tren may chieu - xao se lam bam nham o).
    Hoan 13/11: mac dinh "same_order" - dien thoai cung thu tu + cung mau voi may chieu, tranh doc
    tren man chieu roi bam nham o tren may. Tat di moi xao rieng tung nguoi."""
    return (s.get("guard") in (C.GUARD_STANDARD, C.GUARD_STRICT) and s.get("show_on_phone", True)
            and not s.get("same_order", True))


def one_device(s):
    return s.get("guard") in (C.GUARD_STANDARD, C.GUARD_STRICT)


def block_automation(s):
    return s.get("guard") in (C.GUARD_STANDARD, C.GUARD_STRICT)


def strict(s):
    return s.get("guard") == C.GUARD_STRICT
