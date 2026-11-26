# Copyright (c) 2026, eCentric and contributors
"""Quy tac thuan cua module tai san - KHONG import frappe, test chay khong can bench.

- merge_status_options: noi them trang thai moi vao o Select co san ma khong lam mat gia tri cu.
- category_defaults: mac dinh thoi gian khau hao / co linh kien / mau cau hinh theo loai.
- audit_assets: ra soat du lieu so tai san (dot 0) - cung bo quy tac se dung cho canh bao dot 1.
"""
import datetime as _dt
import re

from ecentric_workspace.tai_san import constants as C


def merge_status_options(existing):
    """Options moi cho o trang thai: theo thu tu C.STATUSES, gia tri la (khong co trong
    STATUSES) giu lai o cuoi - khong bao gio xoa mot gia tri dang co du lieu dung."""
    current = [v.strip() for v in (existing or "").split("\n") if v.strip()]
    extra = [v for v in current if v not in C.STATUSES]
    return "\n".join(list(C.STATUSES) + extra)


def category_defaults(category):
    """(so thang khau hao, la linh kien 0/1, mau cau hinh) cho mot Asset Category; None neu
    loai chua co mac dinh (de nguoi dung tu dien)."""
    row = C.CATEGORY_DEFAULTS.get((category or "").strip().upper())
    if not row:
        return None
    return row["life"], row["component"], row["spec"]


def _date(v):
    if not v:
        return None
    if isinstance(v, _dt.date):
        return v
    try:
        return _dt.date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def _norm_serial(v):
    return re.sub(r"\s+", "", str(v or "")).upper()


def audit_assets(assets, employee_status=None):
    """Ra soat danh sach Asset (dict co cac field trong constants). Tra ve
    {asset_name: [ma van de, ...]} - chi chua may co van de, thu tu ma theo thu tu kiem.

    employee_status: {employee_id: "Active" | "Left" | ...}; thieu thi bo qua kiem nghi viec.
    """
    employee_status = employee_status or {}
    by_name = {a["name"]: a for a in assets}
    serial_count = {}
    for a in assets:
        s = _norm_serial(a.get(C.SERIAL_FIELD))
        if s and s not in C.PLACEHOLDER_SERIALS:
            serial_count[s] = serial_count.get(s, 0) + 1

    out = {}
    for a in assets:
        issues = []
        status = a.get(C.OPS_STATUS_FIELD)
        holder = a.get("custodian")
        category = (a.get("asset_category") or "").upper()
        parent = a.get(C.INSTALLED_ON_FIELD)

        if holder and status in C.HOLDER_REQUIRED and \
                employee_status.get(holder) == C.EMPLOYEE_LEFT:
            issues.append(C.ISSUE_HOLDER_LEFT)
        if holder and status in C.HOLDER_FORBIDDEN:
            issues.append(C.ISSUE_AVAILABLE_WITH_HOLDER)
        if not holder and not parent and status in C.HOLDER_REQUIRED and \
                category not in C.SHARED_CATEGORIES:
            issues.append(C.ISSUE_IN_USE_NO_HOLDER)

        serial = _norm_serial(a.get(C.SERIAL_FIELD))
        if serial in C.PLACEHOLDER_SERIALS:
            issues.append(C.ISSUE_NO_SERIAL)
        elif serial_count.get(serial, 0) > 1:
            issues.append(C.ISSUE_DUP_SERIAL)

        if not re.match(C.TAG_PATTERN, a.get(C.TAG_FIELD) or ""):
            issues.append(C.ISSUE_BAD_TAG)

        bought, in_use = _date(a.get("purchase_date")), _date(a.get("available_for_use_date"))
        if bought and in_use and in_use < bought:
            issues.append(C.ISSUE_DATE_ORDER)

        price = a.get("net_purchase_amount") or 0
        if not price:
            issues.append(C.ISSUE_NO_PRICE)
        if parent:
            if price >= C.COMPONENT_PRICE_ALERT:
                issues.append(C.ISSUE_COMPONENT_PRICE)
            mother = by_name.get(parent)
            if mother and mother.get(C.OPS_STATUS_FIELD) != status:
                issues.append(C.ISSUE_COMPONENT_STATUS)

        if issues:
            out[a["name"]] = issues
    return out
