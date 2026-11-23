# Copyright (c) 2026, eCentric and contributors
"""Ghi dong Thu viec / Thuc tap vao Employee.ec_contracts tu New Staff Preparation (23/11/2026).

Day la GOC du lieu cho danh gia thu viec / khao sat moc (Dot 2): ngay ket thuc thu viec da co tren
Offer (`probation_end_date`), khong bat C&B nhap tay lai. Idempotent: da co dong cung loai + cung
tu_ngay thi khong ghi them. Khong ghi de dong nao co san."""
import frappe
from frappe.utils import getdate

CONTRACT_DT = "EC Employee Contract"
#: Hiring.employment_type -> EC Employee Contract.loai_hop_dong. Loai khac (Freelancer) -> khong ghi.
LOAI_THEO_HINH_THUC = {"Full-time": "Thử việc", "Intern": "Thực tập"}


def loai_hop_dong(employment_type):
    return LOAI_THEO_HINH_THUC.get((employment_type or "").strip())


def ghi_dong_dau(employee, loai, tu_ngay, den_ngay, ghi_chu=None):
    """-> chuoi ket qua. Nem loi khi ho so khong ton tai."""
    if not loai:
        return "khong ghi (hinh thuc khong co thu viec/thuc tap)"
    if not (tu_ngay and den_ngay):
        return "khong ghi (thieu ngay onboard / ngay ket thuc)"
    emp = frappe.get_doc("Employee", employee)
    for r in emp.get("ec_contracts") or []:
        if r.loai_hop_dong == loai and r.tu_ngay and getdate(r.tu_ngay) == getdate(tu_ngay):
            return "da co dong %s tu %s" % (loai, tu_ngay)
    emp.append("ec_contracts", {"loai_hop_dong": loai, "tu_ngay": getdate(tu_ngay),
                                "den_ngay": getdate(den_ngay), "khong_thoi_han": 0,
                                "ghi_chu": (ghi_chu or "")[:500] or None})
    emp.flags.ec_contract_source = ghi_chu
    emp.save(ignore_permissions=True)
    return "da ghi %s %s -> %s vao %s" % (loai, tu_ngay, den_ngay, employee)
