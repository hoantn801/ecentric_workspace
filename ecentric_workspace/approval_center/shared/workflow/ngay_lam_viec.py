# Copyright (c) 2026, eCentric and contributors
"""Ai DANG NGHI hom nay - de cac job nhac viec khong ban tin vao ngay nghi (03/10/2026, Hoan).

"Nghi" = mot trong ba:
  * thu Bay / Chu nhat (luon nghi, Hoan chot - khong phu thuoc Holiday List);
  * ngay le trong Holiday List cua nguoi do (Employee.holiday_list, khong co thi lich mac dinh
    cua cong ty - cung thu tu voi holidays.resolve_holiday_list);
  * co don nghi phep DA DUYET (Leave Application docstatus 1, status Approved) phu ngay do.

Khong tra loi duoc (loi tra cuu) -> coi la DI LAM: mot tin nhac thua it hai hon mot viec bi
bo quen. Nguoi khong co ho so nhan su -> chi xet cuoi tuan.
Day la ham thuan cua Approval Center (khong goi sang module SLA) - module khac can thi goi qua day."""
import frappe


def _employee(user):
    rows = frappe.get_all("Employee", filters={"user_id": user, "status": "Active"},
                          fields=["name", "company"], limit_page_length=1)
    return rows[0] if rows else None


def la_ngay_nghi(user, day=None, _cache=None):
    from frappe.utils import getdate, nowdate
    d = getdate(day or nowdate())
    if d.weekday() >= 5:
        return True
    if not user:
        return False
    cache = _cache if _cache is not None else {}
    try:
        from ecentric_workspace.approval_center.shared.workflow import holidays as _hol
        emp = _employee(user)
        if not emp:
            return False
        hl = _hol.resolve_holiday_list(employee=emp.name, company=emp.company)
        if hl:
            if hl not in cache:
                cache[hl] = {getdate(x) for x in _hol.holiday_dates(hl)}
            if d in cache[hl]:
                return True
        return bool(frappe.get_all("Leave Application", filters={
            "employee": emp.name, "docstatus": 1, "status": "Approved",
            "from_date": ["<=", d], "to_date": [">=", d]}, limit_page_length=1))
    except Exception:
        frappe.log_error(title="ngay_lam_viec.la_ngay_nghi %s" % user, message=frappe.get_traceback())
        return False


def nguoi_di_lam(users, day=None):
    """Loc danh sach nguoi nhan, bo nguoi dang nghi hom nay. Giu thu tu, bo trung."""
    cache, out = {}, []
    for u in users or []:
        if u and u not in out and not la_ngay_nghi(u, day, cache):
            out.append(u)
    return out
