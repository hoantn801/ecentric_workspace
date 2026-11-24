# Copyright (c) 2026, eCentric and contributors
"""Cap duyet nao chay cho mot phieu Contract Review (THUAN - khong goi frappe, de test).

PO chot 24/11/2026 (cau D ban giao chat Ky so): hop dong LAO DONG di "Nhan su (C&B) duyet noi dung
tren ERP -> CEO ky"; moi loai hop dong khac giu luong cu Truong phong -> Finance -> HOF -> CEO.

CONTRACT_REVIEW-V2 (infrastructure/setup_v2.py) co 5 cap, tim theo TEN cap (khong theo so):
    Department Manager Review -> Finance Team Review -> Head of Finance Review
    -> HR & C&B Review (chi HD lao dong) -> CEO Review
Moi cap mandatory=0 de service bo duoc; engine ghi audit "Skipped" kem ly do cho tung cap bo.
Process V1 (4 cap, chua co cap Nhan su) van chay dung: phieu lao dong di du 4 cap nhu truoc.
"""

DEPT = "Department Manager Review"
FINANCE = "Finance Team Review"
HOF = "Head of Finance Review"
HR = "HR & C&B Review"
CEO = "CEO Review"

#: Cap cua luong thuong (khong phai lao dong).
STANDARD = (DEPT, FINANCE, HOF)

REASON_LABOR = "Hợp đồng lao động: Nhân sự (C&B) duyệt nội dung rồi CEO ký - không qua Trưởng phòng / Finance / HOF."
REASON_NOT_LABOR = "Cấp Nhân sự chỉ dành cho hợp đồng lao động."
REASON_ADJUST = "Hợp đồng sẵn có, chỉ điều chỉnh — CEO nhận thông báo, không cần duyệt"


def level_no(levels, name):
    """So cap mang ten `name` trong danh sach [(level_no, level_name), ...] hoac None."""
    for no, nm in levels or ():
        if nm == name:
            return no
    return None


def has_labor_route(levels):
    """Process co cap Nhan su (V2) -> phieu lao dong duoc di luong rieng."""
    return level_no(levels, HR) is not None


def plan(levels, is_labor, skip_ceo):
    """-> (skip_level_nos tuple, ly do). `levels`: [(level_no, level_name), ...] cua process se chay.

    * Lao dong + process co cap Nhan su: bo Truong phong / Finance / HOF; giu Nhan su + CEO
      (khong bao gio bo CEO - CEO ky hop dong lao dong).
    * Lao dong tren process cu (V1): khong bo gi (du 4 cap nhu truoc).
    * Loai khac: bo cap Nhan su (neu co) + CEO khi `skip_ceo` (dieu chinh hop dong san co)."""
    skips, reasons = [], []
    if is_labor and has_labor_route(levels):
        skips = [no for no, nm in levels if nm in STANDARD]
        reasons.append(REASON_LABOR)
    else:
        hr = level_no(levels, HR)
        if hr is not None:
            skips.append(hr)
            reasons.append(REASON_NOT_LABOR)
        if skip_ceo:
            ceo = level_no(levels, CEO)
            if ceo is not None:
                skips.append(ceo)
                reasons.append(REASON_ADJUST)
    return tuple(sorted(set(skips))), (" ".join(reasons) or None)


def snapshot_is_labor_route(level_names):
    """Snapshot cua yeu cau duyet da gui la luong lao dong rieng (co cap Nhan su, khong co Truong phong)."""
    names = set(level_names or ())
    return HR in names and DEPT not in names
