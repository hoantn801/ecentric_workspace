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
Khong ghi so tien vao ket qua / nhat ky duyet (ai co dong duyet cung doc duoc nhat ky).

27/11/2026 (Hoan chot "huong 2"): LEAD DE XUAT CHO NGUOI MINH QUAN LY.
  * Pham vi de xuat cua U = (a) nhan su U xem duoc luong (luat cu) HOP (b) cap duoi cua U theo
    chuoi reports_to - CA TRUC TIEP LAN GIAN TIEP (Hoan chon "truc tiep + gian tiep"). Duyet cay
    tren MOI nhan su (ke ca nguoi da nghi o giua chuoi - reports_to cua cap duoi van tro qua ho),
    chi TRA nhan su Active, tru chinh U. Moi dong mang co `salary_visible` (= can_view_salary).
  * U khong xem duoc luong nhan su do (nhanh b): U KHONG thay, KHONG nhap luong o bat ky buoc nao;
    service bo moi gia tri luong client gui va dat `salary_pending=1`. Nguoi duyet dau tien co
    quyen xem luong dien luong khi duyet (service.fill_salary) - chua dien thi khong duyet duoc
    (service.approval_input_message, engine goi qua ApprovalDefinition.approval_input_check).
  * Quyen xem luong VAN la mot luat duy nhat (can_view_salary) - pham vi (b) chi mo quyen LAP
    PHIEU, khong mo quyen xem so."""
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


def _virtual_ssa(employee):
    """SSA "ao" (KHONG luu) cho nhan su chua co SSA nao: chi employee + phong + cong ty hien tai, de hoi
    ERP "user co duoc doc mot SSA cua nguoi nay khong" bang CHINH luat dang ap cho SSA (DocPerm + User
    Permission Department). get_doc(dict) - khong new_doc: new_doc dien mac dinh tu User Permission cua
    NGUOI DANG NHAP (vd phong cua ho) vao doc. owner = Administrator: quyen "if_owner" cua nguoi dang nhap
    khong duoc mo cua. -> (doc, department) | (None, None)."""
    emp = frappe.db.get_value(EMPLOYEE, employee, ["department", "company"], as_dict=True)
    if not emp:
        return None, None
    doc = frappe.get_doc({"doctype": SSA, "employee": employee, "department": emp.department or None,
                          "company": emp.company or None, "docstatus": 0, "owner": "Administrator"})
    return doc, emp.department


def _dept_scoped(user):
    """user bi gioi han theo phong (User Permission Department ap cho SSA hoac moi doctype)? Loi -> True
    (fail-closed). Can vi Frappe (khong strict) cho qua link TRONG: nhan su khong co phong thi truong phong
    cung "doc duoc" SSA ao - chi nguoi xem tat ca moi duoc."""
    try:
        from frappe.permissions import get_user_permissions
        rows = (get_user_permissions(user) or {}).get("Department") or []
    except Exception:
        return True
    for r in rows:
        applicable = r.get("applicable_for") if hasattr(r, "get") else getattr(r, "applicable_for", None)
        if not applicable or applicable == SSA:
            return True
    return False


def can_view_salary(employee, user=None):
    """user (mac dinh nguoi dang nhap) co quyen doc SSA moi nhat cua employee khong.

    Nhan su CHUA CO SSA nao (thu viec, intern... - 18/11/2026, Phan quyen Tin 12): kiem tren SSA ao cung
    phong -> C&B, CEO / HOF (Payroll Viewer All) va truong phong cua phong do (Payroll Viewer Dept) qua;
    Lead / nhan vien thuong khong. Nhan su khong co phong: chi nguoi xem tat ca. Mot luat duy nhat - khong
    hardcode role."""
    if not employee:
        return False
    user = user or frappe.session.user
    try:
        name = latest_ssa(employee)
        if name:
            return bool(frappe.has_permission(SSA, "read", doc=name, user=user))
        doc, dept = _virtual_ssa(employee)
        if doc is None or not frappe.has_permission(SSA, "read", doc=doc, user=user):
            return False
        return bool(dept) or not _dept_scoped(user)
    except Exception:
        return False


def employee_of(user):
    return frappe.db.get_value(EMPLOYEE, {"user_id": user}, "name") if user else None


def subordinates(manager):
    """Tap ma nhan su la cap duoi TRUC TIEP + GIAN TIEP cua `manager` theo reports_to (27/11/2026,
    Hoan chon truc tiep + gian tiep). Mot truy van, duyet cay trong bo nho; chong vong lap (reports_to
    tro vong) va gioi han do sau _MAX_CHAIN. Gom ca nhan su da nghi o giua chuoi de khong lam dut
    nhanh; loc Active la viec cua nguoi goi. Khong gom chinh `manager`."""
    if not manager:
        return set()
    rows = frappe.get_all(EMPLOYEE, filters={"reports_to": ["is", "set"]}, fields=["name", "reports_to"],
                          limit_page_length=0)
    children = {}
    for r in rows:
        children.setdefault(r.get("reports_to"), []).append(r.get("name"))
    out, frontier, depth = set(), [manager], 0
    while frontier and depth < _MAX_CHAIN:
        nxt = []
        for m in frontier:
            for c in children.get(m, ()):
                if c and c != manager and c not in out:
                    out.add(c)
                    nxt.append(c)
        frontier, depth = nxt, depth + 1
    return out


def can_propose(employee, user=None):
    """user (mac dinh nguoi dang nhap) duoc LAP PHIEU cho employee khong: nhan su Active, khong phai
    chinh minh, va (xem duoc luong HOAC la cap duoi truc tiep/gian tiep). Kiem o server moi lan chon /
    luu / gui - khong tin danh sach client dang giu."""
    if not employee:
        return False
    user = user or frappe.session.user
    me = employee_of(user)
    if employee == me or frappe.db.get_value(EMPLOYEE, employee, "status") != "Active":
        return False
    return employee in subordinates(me) or can_view_salary(employee, user=user)


def candidates():
    """Nhan su nguoi dang nhap duoc de xuat thang chuc = (a) nguoi ho xem duoc luong HOP (b) cap duoi
    truc tiep + gian tiep cua ho (27/11), tru chinh minh, chi Active. Gom ca nhan su Active CHUA CO SSA
    (18/11) - (a) loc qua cung can_view_salary. Moi dong co `salary_visible`."""
    me = employee_of(frappe.session.user)
    ids = sorted(set(frappe.get_all(EMPLOYEE, filters={"status": "Active"}, pluck="name",
                                    limit_page_length=0)) - {me, None})
    if not ids:
        return []
    rows = frappe.get_all(EMPLOYEE, filters={"name": ["in", ids], "status": "Active"},
                          fields=["name", "employee_name", "department", "designation"],
                          order_by="employee_name asc", limit_page_length=0)
    subs = subordinates(me)
    out = []
    for r in rows:
        visible = can_view_salary(r.name)
        if visible or r.name in subs:
            r["salary_visible"] = 1 if visible else 0
            out.append(r)
    return out


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


def snapshot(employee, user=None):
    """Thong tin hien tai cua mot nhan su de dien san form. Nem PermissionError neu user (mac dinh
    nguoi dang nhap) khong duoc de xuat cho nguoi do (can_propose). Luong tham khao (base cua SSA) chi
    tra cho nguoi XEM DUOC luong; Lead de xuat cho cap duoi thi khong co so nao (`salary_visible=0`)."""
    user = user or frappe.session.user
    if not employee or not can_propose(employee, user=user):
        frappe.throw(_("Bạn không được đề xuất cho nhân sự này (chỉ người bạn quản lý hoặc được xem lương)."),
                     frappe.PermissionError)
    emp = frappe.db.get_value(EMPLOYEE, employee,
                              ["name", "employee_name", "department", "designation", "grade",
                               "employment_type", "date_of_joining", "company", "user_id"], as_dict=True)
    if not emp:
        frappe.throw(_("Không tìm thấy nhân sự."))
    visible = can_view_salary(employee, user=user)
    name = latest_ssa(employee) if visible else None
    ssa = name and frappe.db.get_value(SSA, name, ["base", "from_date", "salary_structure"], as_dict=True)
    return {"employee": emp.name, "full_name": emp.employee_name, "department": emp.department,
            "current_position": emp.designation or "", "grade": emp.grade or "",
            "employment_type": emp.employment_type or "", "date_of_joining": emp.date_of_joining,
            "company": emp.company,
            "salary_visible": 1 if visible else 0,
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
    if doc.get("salary_pending"):
        # 27/11: chi xay ra khi duyet thay (System Manager) bo qua buoc dien luong - khong doan so.
        ok = False
        notes.append(_("Phiếu chưa có lương do người duyệt có quyền điền - C&B bổ sung theo phiếu"))
    elif new is not None and float(new) != float(cur or 0):
        ok = False                                    # luon can C&B: luong la gross, khong ghi SSA
        notes.append(_("Lương gross thay đổi từ {0} - C&B cập nhật bảng lương (tách base / thưởng) theo phiếu").format(
            doc.effective_date_of_promotion))
        if frappe.db.exists("Salary Slip", {"employee": emp.name, "docstatus": 1,
                                            "end_date": [">=", str(getdate(doc.effective_date_of_promotion))]}):
            notes.append(_("CHÚ Ý: đã có phiếu lương đã chốt từ ngày hiệu lực trở đi - C&B xử lý chênh lệch"))
    if not notes:
        notes.append(_("Không có thay đổi nào cần ghi"))
    return ok, notes
