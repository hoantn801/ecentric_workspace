# Copyright (c) 2026, eCentric and contributors
"""Ham thuan cho danh muc (phan mem ban quyen + mau thiet bi): khoa so trung va do giong ten.

Muc tieu (Hoan 27/11/2026): "Windows 11 Pro" / "wins 11 pro" / "window 11 pro" phai ve MOT dong.
- name_key: bo dau, bo hoa thuong, bo moi ky tu khong phai chu / so -> trung khoa = cung mot ten (chan cung).
- similar: ten moi GIONG ten co san (difflib >= nguong) -> hoi lai "dung cai co san?" (chan mem,
  nguoi quan ly van tao duoc neu chac la khac - force).
Khong goi frappe: test chay khong can bench.
"""
import difflib
import re
import unicodedata

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def clean_name(s):
    """Gon khoang trang, giu nguyen chu hoa / dau - day la ten hien thi."""
    return re.sub(r"\s+", " ", str(s or "")).strip()


def name_key(s):
    s = unicodedata.normalize("NFD", clean_name(s).replace("đ", "d").replace("Đ", "D"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return _NON_ALNUM.sub("", s)


def _words(s):
    s = unicodedata.normalize("NFD", clean_name(s).replace("đ", "d").replace("Đ", "D"))
    s = "".join(ch for ch in s if unicodedata.category(ch) != "Mn").lower()
    return " ".join(w for w in _NON_ALNUM.split(s) if w)


def similar(name, rows, ratio, label="label", limit=3):
    """Cac dong co ten giong `name` (cao -> thap). rows: list dict co khoa `label` (+ name...).
    So ca chuoi co khoang trang ("wins 11 pro" ~ "windows 11 pro") lan chuoi da bo khoang trang."""
    a, ak = _words(name), name_key(name)
    if not ak:
        return []
    out = []
    for r in rows:
        b = r.get(label) or ""
        score = max(difflib.SequenceMatcher(None, a, _words(b)).ratio(),
                    difflib.SequenceMatcher(None, ak, name_key(b)).ratio())
        if score >= ratio:
            out.append((round(score, 3), r))
    out.sort(key=lambda x: -x[0])
    return [dict(r, score=s) for s, r in out[:limit]]


def code_for(name, prefix, taken):
    """Ma doc duoc cho mau thiet bi moi: EC-DELL-LATITUDE-5420 (trung thi them -2, -3...)."""
    base = prefix + "-" + "-".join(_words(name).upper().split())[:60].strip("-")
    code, i = base, 2
    while code in taken:
        code, i = "%s-%d" % (base, i), i + 1
    return code
