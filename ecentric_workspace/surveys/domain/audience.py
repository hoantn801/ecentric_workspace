# Copyright (c) 2026, eCentric and contributors
"""Ai duoc lam mot khao sat.

Quy tac (PO Hoan chot 01/10/2026 - chon nguoi tham gia, phong ban tham gia, nguoi KHONG
duoc tham gia):

  * mode "all"    : moi nhan vien dang Active (Employee.status = Active, co user_id).
  * mode "custom" : nhan vien Active thuoc mot phong ban duoc chon - TINH CA PHONG CON
                    (giong quyet dinh cua Bai viet noi bo) - CONG nhung nguoi duoc chon
                    dich danh (ke ca nguoi khong co ho so Employee, vd tai khoan quan tri).
  * Loai tru LUON THANG: nguoi trong danh sach loai tru khong bao gio lam duoc, du ho thuoc
    phong ban duoc chon hay duoc chon dich danh.

Cay phong ban doc theo `parent_department`, khong dua vao lft/rgt: hai cot nested-set co
the lech neu ai do sua cay bang SQL, con cha-con thi luon dung voi cai nguoi ta nhin thay.
"""
from ecentric_workspace.surveys import constants as C

ACTIVE = "Active"


def _ancestors(dept, parent_of, limit=50):
    out, cur = [], dept
    while cur and len(out) < limit:
        out.append(cur)
        cur = parent_of.get(cur)
        if cur in out:          # cay hong (vong lap) - dung lai thay vi treo
            break
    return out


def split_targets(targets):
    """(departments, users, excluded) tu cac dong EC Survey Target."""
    depts, users, excluded = set(), set(), set()
    for t in targets or []:
        kind = t.get("kind")
        if kind == C.TARGET_DEPARTMENT and t.get("department"):
            depts.add(t["department"])
        elif kind == C.TARGET_USER and t.get("user"):
            users.add(t["user"])
        elif kind == C.TARGET_EXCLUDE and t.get("user"):
            excluded.add(t["user"])
    return depts, users, excluded


def eligible_users(mode, targets, employees, departments):
    """Tap user (email) duoc lam khao sat.

    employees   : [{user_id, department, status}]
    departments : [{name, parent_department}]
    """
    depts, users, excluded = split_targets(targets)
    parent_of = {d["name"]: d.get("parent_department") for d in departments or []}
    out = set()
    for e in employees or []:
        uid = e.get("user_id")
        if not uid or e.get("status") != ACTIVE:
            continue
        if mode == C.AUDIENCE_ALL:
            out.add(uid)
        elif depts and set(_ancestors(e.get("department"), parent_of)) & depts:
            out.add(uid)
    if mode != C.AUDIENCE_ALL:
        out |= users
    return out - excluded


def is_eligible(user, mode, targets, employees, departments):
    return bool(user) and user in eligible_users(mode, targets, employees, departments)


def describe(mode, targets, dept_label=None, user_label=None):
    """Mot dong tom tat cho the khao sat: "Cả công ty", "Phòng Kế toán + 3 người", ..."""
    dept_label = dept_label or (lambda x: x)
    user_label = user_label or (lambda x: x)
    depts, users, excluded = split_targets(targets)
    if mode == C.AUDIENCE_ALL:
        text = "Cả công ty"
    else:
        parts = [dept_label(d) for d in sorted(depts)]
        if users:
            parts.append("%d người" % len(users) if parts else ", ".join(
                user_label(u) for u in sorted(users)[:3]) + ("..." if len(users) > 3 else ""))
        text = " + ".join(parts) if parts else "Chưa chọn ai"
    if excluded:
        text += " (trừ %d người)" % len(excluded)
    return text
