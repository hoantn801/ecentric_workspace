# Copyright (c) 2026, eCentric and contributors
"""Danh ba noi bo dung chung cho cac form approval (23/11/2026, o CC cua Phe duyet dot xuat).

Chi tra nguoi dung NOI BO dang hoat dong (System User, enabled, khong Administrator/Guest) va chi
cac truong cong khai trong cong ty: email, ho ten, phong ban. Khong tra luong, SDT, ngay sinh...
Form nao can o "chon nguoi" (CC, nguoi nhan ban giao...) goi qua api cua feature minh, khong goi
thang DocType User o client.
"""
import frappe

MAX_CC = 15
_HIDDEN = ("Administrator", "Guest")


def _clean(q):
    return (q or "").strip()[:60]


def search_internal_users(q, limit=12):
    """-> [{user, full_name, department}] khop email hoac ho ten (LIKE). Toi thieu 2 ky tu."""
    q = _clean(q)
    if len(q) < 2:
        return []
    like = "%" + q.replace("%", "").replace("_", "\\_") + "%"
    rows = frappe.db.sql(
        """SELECT u.name AS user, u.full_name
             FROM `tabUser` u
            WHERE u.enabled = 1 AND u.user_type = 'System User'
              AND u.name NOT IN %(hidden)s
              AND (u.name LIKE %(like)s OR u.full_name LIKE %(like)s)
            ORDER BY u.full_name
            LIMIT %(lim)s""",
        {"hidden": _HIDDEN, "like": like, "lim": int(limit or 12)}, as_dict=True) or []
    depts = {}
    users = [r.user for r in rows]
    if users:
        for e in frappe.get_all("Employee", filters={"user_id": ["in", users], "status": "Active"},
                                fields=["user_id", "department"]) or []:
            depts[e.user_id] = e.department
    return [{"user": r.user, "full_name": r.full_name or r.user, "department": depts.get(r.user) or ""}
            for r in rows]


def parse_users(value):
    """Chuoi "a@x, b@x" / xuong dong / list -> list user (giu thu tu, bo trung, bo rong)."""
    if not value:
        return []
    if isinstance(value, (list, tuple)):
        items = value
    else:
        items = str(value).replace("\n", ",").replace(";", ",").split(",")
    return list(dict.fromkeys(i.strip().lower() for i in items if i and i.strip()))


def validate_cc(value, requester=None, max_n=MAX_CC):
    """-> (list user hop le, list loi tieng Viet). Nguoi gui tu bo khoi danh sach (khong loi)."""
    users = [u for u in parse_users(value) if u != (requester or "").lower()]
    errs = []
    if len(users) > max_n:
        errs.append("Chỉ CC tối đa %d người." % max_n)
    bad = []
    for u in users:
        row = frappe.db.get_value("User", u, ["enabled", "user_type"], as_dict=True)
        if u in _HIDDEN or not row or not row.enabled or row.user_type != "System User":
            bad.append(u)
    if bad:
        errs.append("Người được CC không hợp lệ hoặc đã nghỉ: %s" % ", ".join(bad[:5]))
    return users, errs
