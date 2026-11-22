# Copyright (c) 2026, eCentric and contributors
"""Cap HOF co dieu kien o Offer V2 (Hoan chot 23/11/2026) - ham THUAN.

HOF chi duyet khi luong offer VUOT muc luong da duyet tren Hiring Request lien ket (Hiring da qua
CEO). Thieu du lieu de so sanh (khong co luong offer dang so, Hiring khong co muc luong) -> GIU HOF:
khi khong chung minh duoc la trong ngan sach thi de nguoi giu ngan sach xem."""


def _num(v):
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return f if f > 0 else None


def _vnd(v):
    return "{:,.0f}".format(v).replace(",", ".")


def bo_cap_hof(luong_offer, muc_hiring):
    """-> (bo: bool, ly_do: str)."""
    o, h = _num(luong_offer), _num(muc_hiring)
    if o is None:
        return False, "Thiếu lương offer dạng số - giữ cấp HOF"
    if h is None:
        return False, "Hiring Request chưa có mức lương đã duyệt - giữ cấp HOF"
    if o <= h:
        return True, "Lương offer %s ≤ mức đã duyệt trên Hiring %s - bỏ cấp HOF" % (_vnd(o), _vnd(h))
    return False, "Lương offer %s > mức đã duyệt trên Hiring %s - cần HOF duyệt" % (_vnd(o), _vnd(h))
