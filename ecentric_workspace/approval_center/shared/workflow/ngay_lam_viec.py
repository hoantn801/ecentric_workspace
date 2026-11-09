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


# --------------------------------------------------------------------------- dem ngay lam viec
# 09/11/2026 (Trung tam Du lieu, data_hub/): han tinh theo NGAY LAM VIEC cua cong ty. Ba ham
# thuan duoi day KHONG cham DB (ngay le truyen vao) de module nao cung test duoc; ngay_le_cong_ty()
# la cho duy nhat doc Holiday List mac dinh cua cong ty (cung nguon voi la_ngay_nghi).
# "Ngay lam viec" o day = khong phai T7/CN va khong nam trong ngay_le (KHONG xet nghi phep tung
# nguoi - han cua mot yeu cau khong doi theo lich nghi cua nguoi nhan).

def la_ngay_lam_viec(d, ngay_le=()):
    return d.weekday() < 5 and d not in ngay_le


def cong_ngay_lam_viec(tu_ngay, so_ngay, ngay_le=()):
    """Ngay lam viec thu `so_ngay` SAU `tu_ngay` (khong tinh chinh tu_ngay). so_ngay <= 0 ->
    tu_ngay neu la ngay lam viec, khong thi ngay lam viec ke tiep."""
    import datetime as _dt
    d = tu_ngay
    n = int(so_ngay or 0)
    if n <= 0:
        while not la_ngay_lam_viec(d, ngay_le):
            d += _dt.timedelta(days=1)
        return d
    while n > 0:
        d += _dt.timedelta(days=1)
        if la_ngay_lam_viec(d, ngay_le):
            n -= 1
    return d


def dem_ngay_lam_viec(tu_ngay, den_ngay, ngay_le=()):
    """So ngay lam viec d voi tu_ngay < d <= den_ngay (den_ngay <= tu_ngay -> 0)."""
    import datetime as _dt
    n, d = 0, tu_ngay
    while d < den_ngay:
        d += _dt.timedelta(days=1)
        if la_ngay_lam_viec(d, ngay_le):
            n += 1
    return n


def ngay_le_cong_ty(company=None):
    """Tap ngay le trong Holiday List mac dinh cua cong ty (rong neu chua cau hinh / loi tra cuu -
    loi thi ghi Error Log va coi nhu khong co ngay le: han tinh thieu ngay le con hon han khong tinh duoc)."""
    try:
        from frappe.utils import getdate
        from ecentric_workspace.approval_center.shared.workflow import holidays as _hol
        company = company or frappe.defaults.get_global_default("company") or frappe.db.get_single_value(
            "Global Defaults", "default_company")
        hl = _hol.resolve_holiday_list(company=company)
        return {getdate(x) for x in _hol.holiday_dates(hl)} if hl else set()
    except Exception:
        frappe.log_error(title="ngay_lam_viec.ngay_le_cong_ty", message=frappe.get_traceback())
        return set()
