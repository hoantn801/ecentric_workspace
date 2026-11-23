# Copyright (c) 2026, eCentric and contributors
"""Ai xem / lam duoc gi - BIEN GIOI BAO MAT cua module Ky luat (thuan Python, test khong can bench).

Moi duong doc / ghi (API trang /ky-luat, tab Ky luat tren ho so nhan su, has_permission +
permission_query_conditions cua DocType -> tai tep private) deu hoi cac ham o day.

The vang:  NV (cua minh) · LM (team minh: cap duoi truc tiep va gian tiep theo reports_to,
           hoac chinh nguoi gui) · HR / CnB / CEO / System Manager (tat ca).
Ho so do/den: HR / CnB / CEO / SM (tat ca) · LM (team minh, ke ca de xuat cua minh) ·
           NV (cua minh, TU KHI duoc thong bao hop) · dai dien cong doan (ho so co minh du hop,
           tu khi thong bao). Nguoi khac: khong thay gi - ho so rieng tu.
"""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.domain.errors import KyLuatForbidden


class Ctx:
    """Nguoi dang goi. `employee` = ma Employee cua chinh ho (None neu khong co ho so);
    `team` = tap ma Employee ho quan ly (truc tiep + gian tiep)."""

    def __init__(self, user, roles, employee=None, team=()):
        self.user = user
        self.roles = set(roles or ())
        self.employee = employee
        self.team = set(team or ())

    @property
    def is_admin(self):
        return self.user == "Administrator" or bool(self.roles & set(C.ADMIN_ROLES))

    @property
    def is_hr(self):
        return self.is_admin or bool(self.roles & set(C.HR_ROLES))

    @property
    def is_ceo(self):
        return bool(self.roles & set(C.CEO_ROLES))

    @property
    def sees_all(self):
        return self.is_hr or self.is_ceo

    def manages(self, employee):
        return bool(employee) and employee in self.team


# --------------------------------------------------------------------------- the vang --
def can_view_notice(ctx, n):
    if ctx.sees_all:
        return True
    if n.get("employee_user") == ctx.user or (ctx.employee and n.get("employee") == ctx.employee):
        return True
    return n.get("issued_by") == ctx.user or ctx.manages(n.get("employee"))


def can_issue_notice(ctx, employee):
    """LM (cua team) hoac HR. Khong tu gui cho chinh minh."""
    if employee and employee == ctx.employee:
        return False
    return ctx.is_hr or ctx.manages(employee)


def is_notice_owner(ctx, n):
    return n.get("employee_user") == ctx.user or (ctx.employee and n.get("employee") == ctx.employee)


# ------------------------------------------------------------------------- ho so do/den --
def can_view_case(ctx, c):
    if ctx.sees_all:
        return True
    if c.get("proposed_by") == ctx.user or ctx.manages(c.get("employee")):
        return True
    notified = c.get("status") in C.CASE_VISIBLE_TO_EMPLOYEE
    if notified and (c.get("employee_user") == ctx.user or (ctx.employee and c.get("employee") == ctx.employee)):
        return True
    return notified and bool(c.get("union_rep_user")) and c.get("union_rep_user") == ctx.user


def is_case_subject(ctx, c):
    return c.get("employee_user") == ctx.user or bool(ctx.employee and c.get("employee") == ctx.employee)


def can_propose_case(ctx, employee):
    if employee and employee == ctx.employee:
        return False
    return ctx.is_hr or ctx.manages(employee)


def require(ok, msg="Bạn không có quyền với hồ sơ này."):
    if not ok:
        raise KyLuatForbidden(msg)


def require_hr(ctx):
    require(ctx.is_hr, "Chỉ HR / C&B lập và xử lý hồ sơ kỷ luật.")


#: Truong NOI BO cua HR - an voi NV / dai dien cong doan / LM khi tra ve trinh duyet.
CASE_INTERNAL_FIELDS = ("hr_note", "block_note", "investigation_note")


def redact_case(ctx, c):
    """Ban sao dict da bo truong noi bo voi nguoi khong phai HR/CEO."""
    if ctx.sees_all:
        return dict(c)
    return {k: v for k, v in c.items() if k not in CASE_INTERNAL_FIELDS}
