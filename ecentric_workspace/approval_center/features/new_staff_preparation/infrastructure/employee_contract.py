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


# --------------------------------------------------------------------------- 24/11/2026
#: Mac dinh thoi gian thu viec khi Offer chua ghi ngay ket thuc: BLLD 2019 Dieu 25 - toi da 60 ngay
#: cho cong viec can trinh do cao dang tro len (phan lon vi tri van phong). C&B sua tren ho so neu
#: vi tri can it hon (30 ngay / 6 ngay) hoac la quan ly (180 ngay). Thuc tap: KHONG tu dat (can ngay
#: ket thuc that tu Offer).
THU_VIEC_MAC_DINH_NGAY = 60


def ngay_ket_thuc_mac_dinh(loai, tu_ngay):
    """-> (date | None, ghi_chu). Chi tinh cho "Thu viec"."""
    from frappe.utils import add_days
    if loai != "Thử việc" or not tu_ngay:
        return None, None
    return getdate(add_days(getdate(tu_ngay), THU_VIEC_MAC_DINH_NGAY - 1)), (
        "mặc định %d ngày theo Đ25 BLLĐ (Offer chưa ghi ngày kết thúc) - C&B sửa nếu khác" % THU_VIEC_MAC_DINH_NGAY)


def dien_ho_so(employee, tu_ngay, den_ngay, nguon):
    """Dien date_of_joining / final_confirmation_date cua Employee NEU DANG TRONG (khong ghi de).
    Co ghi vet (Comment tren Employee). -> chuoi ket qua."""
    if not employee:
        return "khong co ho so"
    cur = frappe.db.get_value("Employee", employee, ["date_of_joining", "final_confirmation_date"],
                              as_dict=True) or {}
    upd = {}
    if tu_ngay and not cur.get("date_of_joining"):
        upd["date_of_joining"] = getdate(tu_ngay)
    if den_ngay and not cur.get("final_confirmation_date"):
        upd["final_confirmation_date"] = getdate(den_ngay)
    if not upd:
        return "ho so da co ngay vao lam / ngay het thu viec - giu nguyen"
    frappe.db.set_value("Employee", employee, upd)
    try:
        frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Employee",
                        "reference_name": employee,
                        "content": "Tự điền từ %s: %s" % (nguon, ", ".join(
                            "%s = %s" % (k, v) for k, v in sorted(upd.items())))}).insert(ignore_permissions=True)
    except Exception:
        pass
    return "da dien %s" % ", ".join(sorted(upd))
