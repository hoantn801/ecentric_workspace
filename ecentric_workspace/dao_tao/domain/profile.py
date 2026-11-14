# Copyright (c) 2026, eCentric and contributors
"""Ten trong game + nhan vat (kieu Kahoot). Thuan Python.

Hoan 12/11: nguoi choi tu dat ten, toi da 16 ky tu; email cong ty LUON hien nho ben duoi (o
sanh, bang xep hang, co gian lan) nen ten khong can duy nhat. Ten co tu khong phu hop bi chan.
Nhan vat: mau than, mau nen, mat, phu kien - luu theo tai khoan cho lan choi sau.

Loc tu: so tren TUNG TU (khong so chuoi con) - "ngu" khong duoc chan "Nguyễn", "đần" khong
chan "Đan". Tieng Anh thi so chuoi con (it trung ten nguoi Viet).
"""
import re
import unicodedata

from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain.errors import QuizError
from ecentric_workspace.dao_tao.domain.questions import strip_marks

BODY_COLORS = ("#7C5CFF", "#FF6B6B", "#16A34A", "#F59E0B", "#0EA5E9", "#EC4899")
BG_COLORS = ("#EEF2FF", "#FEF3C7", "#DCFCE7", "#FCE7F3", "#E0F2FE", "#F1F5F9")
EYES = ("round", "smile", "glasses", "sleepy")
ACCESSORIES = ("none", "hat", "headphones", "crown", "bow")
AVATAR_KEYS = {"b": BODY_COLORS, "g": BG_COLORS, "e": EYES, "a": ACCESSORIES}

#: So khop NGUYEN TU (co dau, chu thuong).
_BAD_WORDS = {"đần", "địt", "đĩ", "lồn", "cặc", "buồi", "đéo", "đụ", "dái", "điếm", "khốn", "ngu"}
#: So khop nguyen tu sau khi bo dau (viet tat, khong dau).
_BAD_WORDS_PLAIN = {"dit", "dm", "dcm", "dmm", "vcl", "vkl", "clm", "clgt", "cmm", "dkm"}
#: So chuoi con (tieng Anh).
_BAD_SUBSTR = ("fuck", "shit", "bitch", "dick", "pussy", "cunt", "nigg", "asshole")
#: Cap tu (co dau) - "óc chó", "súc vật".
_BAD_PAIRS = {("óc", "chó"), ("súc", "vật"), ("thằng", "ngu"), ("con", "chó")}


def _words(s):
    return [w for w in re.split(r"[^\w]+", s, flags=re.UNICODE) if w]


def bad_name(name):
    s = unicodedata.normalize("NFC", name).lower()
    words = _words(s)
    plain = [strip_marks(w) for w in words]
    if any(w in _BAD_WORDS for w in words):
        return True
    if any(w in _BAD_WORDS_PLAIN for w in plain):
        return True
    for a, b in zip(words, words[1:]):
        if (a, b) in _BAD_PAIRS:
            return True
    squashed = re.sub(r"[^a-z]", "", strip_marks(s))
    return any(b in squashed for b in _BAD_SUBSTR)


def clean_nickname(raw):
    s = unicodedata.normalize("NFC", str(raw or ""))
    s = "".join(ch for ch in s if unicodedata.category(ch)[0] != "C")   # bo ky tu dieu khien
    s = re.sub(r"\s+", " ", s).strip()
    if len(s) < C.NICK_MIN:
        raise QuizError("Tên trong game cần ít nhất %d ký tự." % C.NICK_MIN)
    if len(s) > C.NICK_MAX:
        raise QuizError("Tên trong game tối đa %d ký tự." % C.NICK_MAX)
    if bad_name(s):
        raise QuizError("Tên này không phù hợp, bạn chọn tên khác nhé.")
    if "<" in s or ">" in s:
        raise QuizError("Tên không được chứa ký tự < >.")
    return s


def default_nickname(full_name, email):
    base = (full_name or "").strip().split(" ")[-1] if full_name else ""
    base = base or (email or "").split("@")[0]
    base = re.sub(r"\s+", " ", base)[:C.NICK_MAX]
    return base if len(base) >= C.NICK_MIN and not bad_name(base) else "Người chơi"


def clean_avatar(raw):
    """dict {b, g, e, a} chi so -> dict hop le (sai thi ve 0, khong bao loi - chi la trang tri)."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for k, options in AVATAR_KEYS.items():
        try:
            v = int(raw.get(k, 0))
        except (TypeError, ValueError):
            v = 0
        out[k] = v if 0 <= v < len(options) else 0
    return out


def avatar_for(user):
    """Nhan vat mac dinh on dinh theo email (lan dau vao chua tu trang tri)."""
    h = sum(ord(ch) for ch in (user or ""))
    return {"b": h % len(BODY_COLORS), "g": (h // 7) % len(BG_COLORS), "e": (h // 3) % len(EYES),
            "a": 0}
