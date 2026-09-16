# Copyright (c) 2026, eCentric and contributors
"""Hom do nguoi ta co VANG CO PHEP khong?

Nguon: `Leave Application` cua hrms, trang thai `Approved`. Chu so huu da chot
20/08: lay tu hr/leave, `EC Leave Request` da bo.

Hai luat da chot 16/09, va ca hai deu quan trong hon ve mat CON NGUOI hon la ve
mat ky thuat:

  1. Nghi phep duyet HOI TO van duoc ghi nhan dung. Nguoi ta nghi that, don ve
     sau. Tru diem vi HR duyet cham la tru diem sai nguoi.
  2. Nhung hoi to chi TU DONG khi ky CHUA CHOT. Ky da chot roi thi phai di qua
     `EC SLA Adjustment` - co ly do, co nguoi chiu trach nhiem, co dau vet. Neu
     khong, mot bang diem da cong bo co the tu doi phia sau lung nguoi doc, va
     mot bang diem tu doi thi khong con la ban ghi.

Fail-safe theo huong KHONG MIEN TRU: loi tra cuu -> tra ve False (khong coi la
nghi phep). Sai huong nay tao ra mot khieu nai cua mot nguoi; sai huong kia tao
ra mot thang khong ai bi tru gi va khong ai nhan ra.
"""
import frappe

_LEAVE_DOCTYPE = "Leave Application"
_APPROVED = "Approved"


def _leave_available():
    try:
        return bool(frappe.db.exists("DocType", _LEAVE_DOCTYPE))
    except Exception:
        return False


def approved_leave_days(employee, from_date, to_date):
    """set() cac ngay (date) nguoi do nghi co phep trong khoang [from_date, to_date].

    Mot don nghi trai dai nhieu ngay duoc bung ra thanh tung ngay: don vi cham
    diem cua nhom cham cong la NGAY, nen mien tru cung phai theo ngay.
    """
    if not employee or not _leave_available():
        return set()
    try:
        rows = frappe.get_all(_LEAVE_DOCTYPE, filters={
            "employee": employee, "status": _APPROVED, "docstatus": 1,
            "from_date": ("<=", to_date), "to_date": (">=", from_date),
        }, fields=["from_date", "to_date"])
    except Exception:
        frappe.log_error(title="sla.approved_leave_days", message=frappe.get_traceback())
        return set()

    from datetime import timedelta
    from frappe.utils import getdate
    lo, hi = getdate(from_date), getdate(to_date)
    days = set()
    for r in rows:
        d, end = max(getdate(r["from_date"]), lo), min(getdate(r["to_date"]), hi)
        while d <= end:
            days.add(d)
            d += timedelta(days=1)
    return days


def is_on_approved_leave(employee, on_date):
    return bool(approved_leave_days(employee, on_date, on_date))


def holiday_days(employee=None, company=None, from_date=None, to_date=None):
    """Ngay nghi le/cuoi tuan theo Holiday List. Dung de KHONG MO nghia vu cham
    cong vao nhung ngay khong phai ngay lam viec - re hon nhieu so voi mo roi
    loai tru, va khong lam phinh cot 'khong tinh diem' bang rac.

    Tra ve `None` khi KHONG TRA CUU DUOC - khac han voi `set()` nghia la "khong
    co ngay nghi nao". Phan biet nay bat buoc: neu loi tra ve `set()` thi mot
    truc trac Holiday List se lam he thong mo nghia vu cham cong vao ngay Tet,
    va ca cong ty bi cham `Missed` cho mot ngay nghi le. Ben goi PHAI dung lai
    khi nhan `None`, dung mo nghia vu voi gia dinh "hom nay la ngay lam viec".
    """
    try:
        from ecentric_workspace.approval_center.shared.workflow import holidays as hol
        hl = hol.resolve_holiday_list(employee=employee, company=company)
        if not hl:
            return None
        days = hol.holiday_dates(hl)
    except Exception:
        frappe.log_error(title="sla.holiday_days", message=frappe.get_traceback())
        return None
    if from_date and to_date:
        from frappe.utils import getdate
        lo, hi = getdate(from_date), getdate(to_date)
        return {d for d in days if lo <= d <= hi}
    return days
