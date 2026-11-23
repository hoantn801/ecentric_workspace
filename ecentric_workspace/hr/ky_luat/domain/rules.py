# Copyright (c) 2026, eCentric and contributors
"""Luat chon the / hinh thuc / can cu, tai pham, goi y the vang - HAM THUAN.

Moi ham nhan dict thuong (khong Document) de test khong can Frappe."""
import datetime as _dt

from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.domain import dates as D


def validate_choice(case, prior_cases=()):
    """-> {field: loi}. Rong = hop le. `prior_cases`: ho so DA BAN HANH cua cung NV."""
    e = {}
    card, penalty = case.get("card"), case.get("penalty")
    if card not in C.CARDS:
        e["card"] = "Chọn thẻ đỏ hoặc thẻ đen."
        return e
    allowed = C.CARD_PENALTIES[card]
    if penalty not in allowed:
        e["penalty"] = ("Thẻ đỏ chỉ có hình thức khiển trách." if card == C.CARD_RED
                        else "Thẻ đen bắt buộc chọn một hình thức: kéo dài thời hạn nâng lương, "
                             "cách chức hoặc sa thải.")
        return e
    if penalty == C.P_EXTEND:
        try:
            m = int(case.get("extend_months") or 0)
        except (TypeError, ValueError):
            m = 0
        if not 1 <= m <= C.MAX_EXTEND_MONTHS:
            e["extend_months"] = "Thời gian kéo dài nâng lương từ 1 đến 6 tháng."
    if penalty == C.P_DEMOTE and not int(case.get("holds_position") or 0):
        e["holds_position"] = "Cách chức chỉ áp dụng cho người đang giữ chức vụ - xác nhận ô này."
    if penalty == C.P_DISMISS:
        g = str(case.get("dismissal_ground") or "")
        if g not in C.DISMISS_GROUND_CODES:
            e["dismissal_ground"] = "Sa thải bắt buộc chọn một căn cứ Điều 125."
        elif g == C.GROUND_RECIDIVISM and not active_recidivism_base(prior_cases, case.get("today")):
            e["dismissal_ground"] = ("Căn cứ (3) chỉ dùng khi nhân viên đang bị kéo dài thời hạn nâng "
                                     "lương hoặc cách chức mà chưa được xoá kỷ luật.")
    if penalty != C.P_DISMISS and case.get("dismissal_ground"):
        e["dismissal_ground"] = "Chỉ chọn căn cứ Điều 125 khi hình thức là sa thải."
    return e


def _unexpunged(row, today):
    if row.get("status") != C.S_ISSUED:
        return False
    due = D.as_date(row.get("expunge_due"))
    if due is None or today is None:
        return True          # sa thai (khong xoa) / khong biet hom nay -> coi la con hieu luc
    return D.as_date(today) < due


def active_disciplines(prior_cases, today=None):
    """Ky luat DA BAN HANH va CHUA xoa (trang thai Da ban hanh, chua toi ngay xoa)."""
    return [r for r in prior_cases or () if _unexpunged(r, today)]


def active_recidivism_base(prior_cases, today=None):
    """Ky luat keo dai nang luong / cach chuc chua xoa - can cu (3) D125."""
    return [r for r in active_disciplines(prior_cases, today) if r.get("penalty") in C.RECIDIVISM_BASE_PENALTIES]


def recidivism_note(prior_cases, today=None):
    """Chuoi canh bao tai pham cho HR khi lap ho so moi (rong neu khong co)."""
    rows = active_disciplines(prior_cases, today)
    if not rows:
        return ""
    parts = ["%s (%s, quyết định %s)" % (r.get("name"), r.get("penalty"),
                                         D.as_date(r.get("decision_date")) or "?") for r in rows]
    return "Tái phạm: nhân viên đang chịu kỷ luật chưa được xoá - " + "; ".join(parts)


def yellow_hint(notice_dates, today):
    """Goi y (KHONG tu dong) khi du YELLOW_HINT_COUNT the vang trong YELLOW_HINT_WINDOW_DAYS ngay."""
    t = D.as_date(today)
    since = t - _dt.timedelta(days=C.YELLOW_HINT_WINDOW_DAYS)
    n = sum(1 for d in notice_dates or () if d and since < D.as_date(d) <= t)
    if n >= C.YELLOW_HINT_COUNT:
        return ("%d thẻ vàng trong %d ngày gần nhất - HR cân nhắc xem xét. Hệ thống không tự lập thẻ đỏ; "
                "kỷ luật phải dựa trên hành vi có trong nội quy." % (n, C.YELLOW_HINT_WINDOW_DAYS))
    return ""


def expunge_blocked_by(case, later_cases):
    """Ho so moi DA BAN HANH cua cung NV co ngay quyet dinh trong thoi gian cho xoa -> tai pham,
    khong tu xoa (HR xem lai). -> danh sach ten ho so."""
    start, due = D.as_date(case.get("decision_date")), D.as_date(case.get("expunge_due"))
    if not start or not due:
        return []
    out = []
    for r in later_cases or ():
        if r.get("name") == case.get("name") or r.get("status") not in (C.S_ISSUED, C.S_EXPUNGED):
            continue
        d = D.as_date(r.get("decision_date"))
        if d and start < d <= due:
            out.append(r.get("name"))
    return out
