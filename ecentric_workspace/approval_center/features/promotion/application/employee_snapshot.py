# Copyright (c) 2026, eCentric and contributors
"""Promotion Request chon THANG nhan su + tu cap nhat sau duyet (29/09/2026, Hoan chot;
sua theo review chat Phan quyen cung ngay - P1..P3).

QUYEN XEM LUONG - KHONG tu dat luat o day. "U xem duoc luong cua E" = U co quyen READ tren
Salary Structure Assignment MOI NHAT cua E (frappe.has_permission tren DUNG ban ghi do - DocPerm
+ pham vi luong cua chat Phan quyen). Khong dung get_list(employee=E): pham vi dang dua tren
SSA.department (chup luc tao), nguoi chuyen phong con SSA cu thi truong phong cu van "thay" -
chi SSA moi nhat moi phan anh phong hien tai.

Dung o ba cho, cung mot ham `can_view_salary`:
  * danh sach nhan su duoc de xuat (nguoi dang nhap);
  * nguoi duyet buoc 1 = nguoi DAU TIEN tren chuoi reports_to cua nhan su do xem duoc luong
    (khong ai / trung nguoi gui -> bo buoc 1);
  * an current_salary / proposed_salary / incentives o man hinh chi tiet voi nguoi xem khong
    qua duoc (Lead duyet ho, nguoi duoc chia se...) - `redact`.

Sau khi duyet xong (nen, sau commit - apply_promotion):
  * Employee.designation = vi tri de xuat (neu la mot Designation co that; khong thi bao C&B)
  * luong: KHONG tu tao / sua Salary Structure Assignment (01/10/2026, Hoan chot). Luong tren
    phieu la GROSS (gom thuong hieu suat...), con SSA.base chi la luong co ban - ghi gross vao
    base la sai. Gross thay doi -> bao C&B tu tach base / thuong va tao bang luong tu ngay
    hieu luc. (Ban 29/09 tao SSA Draft voi base = luong de xuat: da bo.)
  * Luong hien tai (gross) do nguoi de xuat TU NHAP; base cua SSA moi nhat chi hien de tham
    khao (`base_salary`), khong dien vao phieu.
Khong ghi so tien vao ket qua / nhat ky duyet (ai co dong duyet cung doc duoc nhat ky)."""
import frappe
from frappe import _
from frappe.utils import getdate, nowdate

SSA = "Salary Structure Assignment"
EMPLOYEE = "Employee"
SALARY_FIELDS = ("current_salary", "proposed_salary", "incentives")
_MAX_CHAIN = 15


def latest_ssa(employee, as_of=None):
    """Ten SSA da submit dang hieu luc (moi nhat <= as_of; khong co thi moi nhat bat ky)."""
    day = str(getdate(as_of or nowdate()))
    rows = frappe.get_all(SSA, filters={"employee": employee, "docstatus": 1, "from_date": ["<=", day]},
                          pluck="name", order_by="from_date desc", limit_page_length=1) \
        or frappe.get_all(SSA, filters={"employee": employee, "docstatus": 1},
                          pluck="name", order_by="from_date desc", limit_page_length=1)
    return rows[0] if rows else None


def can_view_salary(employee, user=None):
    """user (mac dinh nguoi dang nhap) co quyen doc SSA moi nhat cua employee khong."""
    if not employee:
        return False
    name = latest_ssa(employee)
    if not name:
        return False
    try:
        return bool(frappe.has_permission(SSA, "read", doc=name, user=user or frappe.session.user))
    except Exception:
        return False


def candidates():
    """Nhan su nguoi dang nhap duoc de xuat thang chuc = nguoi ho xem duoc luong (tru chinh minh)."""
    me = frappe.db.get_value(EMPLOYEE, {"user_id": frappe.session.user}, "name")
    ids = sorted(set(frappe.get_all(SSA, filters={"docstatus": 1}, pluck="employee",
                                    limit_page_length=0)) - {me, None})
    if not ids:
        return []
    rows = frappe.get_all(EMPLOYEE, filters={"name": ["in", ids], "status": "Active"},
                          fields=["name", "employee_name", "department", "designation"],
                          order_by="employee_name asc", limit_page_length=0)
    return [r for r in rows if can_view_salary(r.name)]


def salary_reviewer(employee, requester):
    """Nguoi duyet buoc 1: nguoi dau tien tren chuoi reports_to (tu quan ly cua nhan su di len)
    xem duoc luong nhan su do. Trung nguoi gui hoac khong co ai -> None (bo buoc 1)."""
    seen = set()
    cur = frappe.db.get_value(EMPLOYEE, employee, "reports_to")
    while cur and cur not in seen and len(seen) < _MAX_CHAIN:
        seen.add(cur)
        row = frappe.db.get_value(EMPLOYEE, cur, ["user_id", "reports_to", "status"], as_dict=True)
        if not row:
            break
        u = row.user_id
        if u and row.status == "Active" and frappe.db.get_value("User", u, "enabled") \
                and can_view_salary(employee, user=u):
            return None if u == requester else u
        cur = row.reports_to
    return None


def redact(business, request=None):
    """An so luong voi nguoi xem khong xem duoc luong nhan su do. Loi -> AN (fail-closed)."""
    try:
        emp = business.get("promoted_employee")
        user = frappe.session.user
        if emp:
            ok = can_view_salary(emp)
        else:
            # Phieu cu (chua chon nhan su): nguoi gui, hoac ai co quyen doc SSA noi chung.
            ok = business.get("requested_by") == user or bool(frappe.has_permission(SSA, "read", user=user))
    except Exception:
        ok = False
    if not ok:
        for f in SALARY_FIELDS:
            business[f] = None
        business["salary_hidden"] = 1
    return business


def snapshot(employee):
    """Thong tin hien tai cua mot nhan su de dien san form. Nem PermissionError neu nguoi dang
    nhap khong xem duoc luong nguoi do."""
    if not employee or not can_view_salary(employee):
        frappe.throw(_("Bạn không có quyền xem thông tin lương của nhân sự này."), frappe.PermissionError)
    emp = frappe.db.get_value(EMPLOYEE, employee,
                              ["name", "employee_name", "department", "designation", "grade",
                               "employment_type", "date_of_joining", "company", "user_id"], as_dict=True)
    if not emp:
        frappe.throw(_("Không tìm thấy nhân sự."))
    name = latest_ssa(employee)
    ssa = name and frappe.db.get_value(SSA, name, ["base", "from_date", "salary_structure"], as_dict=True)
    return {"employee": emp.name, "full_name": emp.employee_name, "department": emp.department,
            "current_position": emp.designation or "", "grade": emp.grade or "",
            "employment_type": emp.employment_type or "", "date_of_joining": emp.date_of_joining,
            "company": emp.company,
            # THAM KHAO: base (chua gom thuong hieu suat) - phieu dung GROSS do nguoi de xuat nhap.
            "base_salary": ssa.base if ssa else None,
            "salary_from": ssa.from_date if ssa else None,
            "salary_structure": ssa.salary_structure if ssa else None}


def designations():
    return frappe.get_all("Designation", pluck="name", order_by="name asc", limit_page_length=0)


def apply_promotion(doc):
    """Ghi thang chuc vao ho so + luong moi. -> (applied_ok: bool, [ket qua tung phan])."""
    notes, ok = [], True
    emp = frappe.get_doc(EMPLOYEE, doc.promoted_employee)
    new_pos = (doc.proposed_position or "").strip()
    if new_pos and new_pos != (emp.designation or ""):
        if frappe.db.exists("Designation", new_pos):
            emp.designation = new_pos
            emp.flags.ec_promotion_request = doc.name
            emp.save(ignore_permissions=True)
            notes.append(_("Chức danh → {0}").format(new_pos))
        else:
            ok = False
            notes.append(_("Chức danh \"{0}\" chưa có trong danh mục - C&B cập nhật tay").format(new_pos))
    cur, new = doc.current_salary, doc.proposed_salary
    if new is not None and float(new) != float(cur or 0):
        ok = False                                    # luon can C&B: luong la gross, khong ghi SSA
        notes.append(_("Lương gross thay đổi từ {0} - C&B cập nhật bảng lương (tách base / thưởng) theo phiếu").format(
            doc.effective_date_of_promotion))
        if frappe.db.exists("Salary Slip", {"employee": emp.name, "docstatus": 1,
                                            "end_date": [">=", str(getdate(doc.effective_date_of_promotion))]}):
            notes.append(_("CHÚ Ý: đã có phiếu lương đã chốt từ ngày hiệu lực trở đi - C&B xử lý chênh lệch"))
    if not notes:
        notes.append(_("Không có thay đổi nào cần ghi"))
    return ok, notes
