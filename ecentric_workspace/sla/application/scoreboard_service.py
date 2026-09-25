# Copyright (c) 2026, eCentric and contributors
"""Bang diem: ti le cua mot nguoi, phan tich theo nhom, va xep hang phong ban.

Ba cau hoi cua chu so huu, theo dung thu tu ong ay hoi:
  1. SLA thang nay cua toi la bao nhieu?
  2. xx%% do la do dau?  -> `contribution`
  3. ca phong the nao?    -> `department_board`

Moi con so tra ve deu kem MAU SO. Mot ti le khong kem mau so la mot y kien.
"""
import frappe

from ecentric_workspace.sla import permissions
from ecentric_workspace.sla.constants import (
    ALL_GROUPS, DEFAULT_MIN_SAMPLE, DT_OBLIGATION, GROUP_COUNTS_TOWARD_SLA,
    GROUP_LABEL,
    GROUP_MIN_SAMPLE, GROUP_SORT, GROUP_UNIT, MAX_PAGE_SIZE, SCOPE_ALL,
    SCOPE_DEPARTMENT, STATUS_CANCELLED,
)
from ecentric_workspace.sla.domain import due_rules, scoring

_ROW_FIELDS = ["name", "group_key", "counts_toward_sla", "status", "due_at",
               "closed_at", "opened_at", "paused_seconds", "title",
               "source_doctype", "source_name", "source_detail", "late_seconds",
               "excluded_reason"]

# Tran doc. Cham tran la PHAI ghi log: mot bang diem bi cat am tham se hien ra
# mot ti le tinh tren mot phan du lieu, trong nhu that va khong ai nghi ngo.
_ROW_CAP = MAX_PAGE_SIZE * 4          # 2.000 dau viec / nguoi / thang
_BOARD_CAP = MAX_PAGE_SIZE * 40       # 20.000 dau viec / phong / thang


def current_period():
    from frappe.utils import now_datetime
    return due_rules.period_of(now_datetime())


def _rows_for(user, period):
    """Cac dau viec cua mot nguoi trong ky, DA LOC theo pham vi nguoi xem.

    Loc lai o day chu khong chi dua vao `can_view_user`: hai ham do hai thu
    khac nhau. `can_view_user` hoi "hom nay hai nguoi co chung phong khong",
    con moi dong nghia vu mang phong ban DA CHUP luc no phat sinh. Mot nguoi
    chuyen tu Tai chinh sang Kinh doanh thang truoc se lam dong nghiep Kinh
    doanh doc duoc ca bang diem Tai chinh cu cua ho neu chi hoi cau thu nhat.
    Hai cau hoi, hai ket qua - va o day phai lay cau hep hon.
    """
    filters = {"owner_user": user, "period_month": period,
               "status": ("!=", STATUS_CANCELLED)}
    scope, depts = permissions.get_scope()
    if user != frappe.session.user and scope == SCOPE_DEPARTMENT:
        filters["department"] = ("in", depts)
    rows = frappe.get_all(DT_OBLIGATION, filters=filters, fields=_ROW_FIELDS,
                          limit_page_length=_ROW_CAP, order_by="opened_at asc")
    if len(rows) >= _ROW_CAP:
        frappe.log_error(
            title="sla: bang diem ca nhan bi cat",
            message="user=%s ky=%s cham tran %d dong - ti le hien ra se thieu."
                    % (user, period, _ROW_CAP))
    return rows


def _decorate_groups(groups):
    """Them nhan/don vi/thu tu de UI khong phai biet ve hang so cua backend."""
    out = []
    for g in sorted(groups, key=lambda k: GROUP_SORT.get(k, 999)):
        b = dict(groups[g])
        b.update({
            "group_key": g,
            "label": GROUP_LABEL.get(g, g),
            "unit": GROUP_UNIT.get(g, ""),
            "counts_toward_sla": bool(GROUP_COUNTS_TOWARD_SLA.get(g, 1)),
            "min_sample": GROUP_MIN_SAMPLE.get(g, DEFAULT_MIN_SAMPLE),
        })
        out.append(b)
    return out


def person_board(user, period=None):
    """Bang diem mot nguoi. Nem PermissionError neu nguoi xem khong duoc phep."""
    from frappe.utils import now_datetime
    period = period or current_period()
    if not permissions.can_view_user(user):
        frappe.throw("Khong co quyen xem diem SLA cua nguoi nay.", frappe.PermissionError)
    rows = _rows_for(user, period)
    agg = scoring.aggregate(rows, now=now_datetime(), min_sample_by_group=GROUP_MIN_SAMPLE)
    return {
        "user": user,
        "period": period,
        "overall": agg["overall"],
        "groups": _decorate_groups(agg["groups"]),
        "contribution": scoring.contribution(agg["groups"]),
    }


def person_items(user, period=None, group_key=None, only_failed=0):
    """Danh sach dau viec de nguoi ta KIEM CHUNG duoc con so.

    Mot ti le khong mo ra duoc thanh tung dong la mot ti le khong ai cai duoc,
    va mot ti le khong ai cai duoc thi khong ai sua hanh vi theo. Day la ly do
    ham nay ton tai, khong phai de "co them tinh nang".
    """
    from frappe.utils import now_datetime
    period = period or current_period()
    if not permissions.can_view_user(user):
        frappe.throw("Khong co quyen xem diem SLA cua nguoi nay.", frappe.PermissionError)
    now = now_datetime()
    out = []
    for r in _rows_for(user, period):
        if group_key and r["group_key"] != group_key:
            continue
        eff = scoring.effective_status(r, now)
        if int(only_failed or 0) and eff not in ("Late", "Missed"):
            continue
        row = dict(r)
        row["effective_status"] = eff
        row["group_label"] = GROUP_LABEL.get(r["group_key"], r["group_key"])
        out.append(row)
    return out


def department_board(department=None, period=None):
    """Xep hang trong phong. Tra ve nhung nguoi NGUOI XEM duoc phep thay."""
    from frappe.utils import now_datetime
    period = period or current_period()
    scope, depts = permissions.get_scope()
    if scope == SCOPE_ALL:
        filters = {"period_month": period, "status": ("!=", STATUS_CANCELLED)}
        if department:
            filters["department"] = department
    elif scope == SCOPE_DEPARTMENT:
        allowed = [department] if (department and department in depts) else list(depts)
        if not allowed:
            # `IN ()` la loi cu phap SQL, khong phai "khong co ket qua". Hom nay
            # get_scope khong bao gio tra ve rong o nhanh nay, nhung mot lan sua
            # o cho khac se lam no rong va trang /sla se do 500 thay vi trong.
            return {"period": period, "scope": scope, "rows": [], "truncated": False}
        filters = {"period_month": period, "status": ("!=", STATUS_CANCELLED),
                   "department": ("in", allowed)}
    else:
        filters = {"period_month": period, "status": ("!=", STATUS_CANCELLED),
                   "owner_user": frappe.session.user}

    rows = frappe.get_all(DT_OBLIGATION, filters=filters,
                          fields=["owner_user", "department", "group_key",
                                  "counts_toward_sla", "status", "due_at",
                                  "paused_seconds"],
                          order_by="owner_user asc, opened_at asc",
                          limit_page_length=_BOARD_CAP)
    truncated = len(rows) >= _BOARD_CAP
    if truncated:
        frappe.log_error(title="sla: bang xep hang bi cat",
                         message="filters=%r cham tran %d dong." % (filters, _BOARD_CAP))
    now = now_datetime()
    by_user, dept_of = {}, {}
    for r in rows:
        # Khoa theo NGUOI, khong theo (nguoi, phong). Nguoi chuyen phong giua
        # thang se bi tach thanh hai dong, moi dong mot nua mau so - va neu ca
        # hai nua deu duoi nguong thi ho bien thanh "chua du mau" o ca hai cho,
        # trong khi thuc te ho co du du lieu. Mot nguoi, mot dong.
        by_user.setdefault(r["owner_user"], []).append(r)
        dept_of[r["owner_user"]] = r.get("department")

    board = []
    for user, urows in by_user.items():
        agg = scoring.aggregate(urows, now=now, min_sample_by_group=GROUP_MIN_SAMPLE)
        board.append({
            "user": user, "department": dept_of.get(user),
            "overall": agg["overall"],
            "groups": {g: agg["groups"][g]["rate"] for g in ALL_GROUPS},
        })
    # Chua du mau xep CUOI, khong xep dau. Mot nguoi co 2 dau viec dung ca 2
    # khong phai nguoi dan dau - ho la nguoi chua do duoc.
    board.sort(key=lambda b: (b["overall"]["rate"] is None,
                              -(b["overall"]["rate"] or 0), b["user"]))
    return {"period": period, "scope": scope, "rows": board, "truncated": truncated}
