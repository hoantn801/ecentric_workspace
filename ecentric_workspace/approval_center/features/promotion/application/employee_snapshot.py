# Copyright (c) 2026, eCentric and contributors
"""Promotion Request chon THANG nhan su + tu cap nhat sau duyet (29/09/2026, Hoan chot).

QUYEN XEM LUONG - KHONG tu dat luat o day. Nguoi dung chi thay (va chi chon duoc) nhan su ma
CHINH HO doc duoc Salary Structure Assignment (frappe.get_list chay voi quyen cua nguoi dang
nhap: DocPerm + dieu kien pham vi luong cua chat Phan quyen). Khong doc duoc SSA nao cua mot
nguoi = khong thay nguoi do, khong thay luong nguoi do. Mot nguon su that cho "ai xem luong ai".

Sau khi duyet xong (nen, sau commit - apply_promotion):
  * Employee.designation = vi tri de xuat (neu la mot Designation co that; khong thi bo qua, bao C&B)
  * luong de xuat khac luong hien tai -> TAO Salary Structure Assignment MOI (chep cau truc /
    cong ty / cac truong cua SSA dang hieu luc, base = luong de xuat, from_date = ngay hieu luc)
    va submit. KHONG sua de SSA cu (lich su luong giu nguyen).
Loi o buoc nao thi ghi lai ket qua tren phieu + Error Log + bao C&B / nguoi gui cap nhat tay."""
import frappe
from frappe import _
from frappe.utils import getdate, nowdate

SSA = "Salary Structure Assignment"
EMPLOYEE = "Employee"
#: Truong cua SSA KHONG chep sang SSA moi (dinh danh / trang thai / cai minh dat lai).
_SSA_SKIP = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
             "amended_from", "from_date", "base", "doctype", "_user_tags", "_comments",
             "_assign", "_liked_by", "_seen"}


def _latest_ssa(employee, as_of=None, fields=("name", "base", "from_date", "salary_structure")):
    """SSA dang hieu luc ma NGUOI DANG NHAP doc duoc. [] neu khong co quyen / khong co."""
    try:
        rows = frappe.get_list(SSA, filters={"employee": employee, "docstatus": 1,
                                             "from_date": ["<=", str(getdate(as_of or nowdate()))]},
                               fields=list(fields), order_by="from_date desc", limit_page_length=1)
    except frappe.PermissionError:
        return None
    return rows[0] if rows else None


def can_view_salary(employee):
    try:
        return bool(frappe.get_list(SSA, filters={"employee": employee}, pluck="name",
                                    limit_page_length=1))
    except frappe.PermissionError:
        return False


def candidates():
    """Nhan su nguoi dang nhap duoc de xuat thang chuc = nguoi ho xem duoc luong (tru chinh minh)."""
    try:
        emps = frappe.get_list(SSA, filters={"docstatus": 1}, pluck="employee", distinct=True,
                               limit_page_length=0)
    except frappe.PermissionError:
        return []
    me = frappe.db.get_value(EMPLOYEE, {"user_id": frappe.session.user}, "name")
    ids = sorted({e for e in emps if e and e != me})
    if not ids:
        return []
    return frappe.get_all(EMPLOYEE, filters={"name": ["in", ids], "status": "Active"},
                          fields=["name", "employee_name", "department", "designation"],
                          order_by="employee_name asc", limit_page_length=0)


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
    ssa = _latest_ssa(employee)
    return {"employee": emp.name, "full_name": emp.employee_name, "department": emp.department,
            "current_position": emp.designation or "", "grade": emp.grade or "",
            "employment_type": emp.employment_type or "", "date_of_joining": emp.date_of_joining,
            "company": emp.company, "current_salary": ssa.base if ssa else None,
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
    cur = frappe.get_all(SSA, filters={"employee": emp.name, "docstatus": 1,
                                       "from_date": ["<=", str(getdate(doc.effective_date_of_promotion))]},
                         pluck="name", order_by="from_date desc", limit_page_length=1)
    new_base = doc.proposed_salary
    if new_base is not None and float(new_base) != float(doc.current_salary or 0):
        if not cur:
            ok = False
            notes.append(_("Chưa có bảng lương (SSA) để chép - C&B tạo tay"))
        else:
            old = frappe.get_doc(SSA, cur[0])
            new = frappe.new_doc(SSA)
            for k, v in old.as_dict().items():
                if k not in _SSA_SKIP and not isinstance(v, list):
                    new.set(k, v)
            new.from_date = doc.effective_date_of_promotion
            new.base = new_base
            new.flags.ec_promotion_request = doc.name
            # Job nen chay duoi ten nguoi duyet cuoi (CEO) - khong nhat thiet co quyen submit SSA.
            new.flags.ignore_permissions = True
            new.insert(ignore_permissions=True)
            new.submit()
            notes.append(_("Lương mới từ {0}: {1} ({2})").format(doc.effective_date_of_promotion,
                                                                 new_base, new.name))
    if not notes:
        notes.append(_("Không có thay đổi nào cần ghi"))
    return ok, notes
