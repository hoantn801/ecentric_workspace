# Copyright (c) 2026, eCentric and contributors
"""Doc / ghi bang hop dong tren ho so nhan su. CHO DUY NHAT cham DB cua hr/hop_dong.

`ec_contracts` nam o permlevel 2 cua Employee (chi HR Manager / HR User / EC CnB doc duoc qua
Desk). Ham o day doc thang DB (khong ap quyen) - nen CHI duoc goi tu job he thong hoac tu
service da kiem quyen o tang tren. Khong tra nguyen du lieu nay ra trinh duyet."""
import frappe

EMPLOYEE = "Employee"
CONTRACT = "EC Employee Contract"
CONTRACT_FIELDS = ["name", "parent", "idx", "loai_hop_dong", "so_hop_dong", "tu_ngay", "den_ngay",
                   "khong_thoi_han"]
EMP_FIELDS = ["name", "employee_name", "user_id", "employment_type", "date_of_joining",
              "reports_to", "department", "designation", "grade", "company", "status",
              "relieving_date"]


def nhan_vien_dang_lam(names=None):
    filters = {"status": "Active"}
    if names:
        filters["name"] = ["in", list(names)]
    return [dict(r) for r in frappe.get_all(EMPLOYEE, filters=filters, fields=EMP_FIELDS,
                                            limit_page_length=0)]


def nhan_vien(name):
    row = frappe.db.get_value(EMPLOYEE, name, EMP_FIELDS, as_dict=True)
    return dict(row) if row else None


def nhan_vien_theo_user(user):
    if not user:
        return None
    row = frappe.db.get_value(EMPLOYEE, {"user_id": user}, EMP_FIELDS, as_dict=True)
    return dict(row) if row else None


def hop_dong_cua(employees):
    """{employee: [dong hop dong]} - mot truy van cho ca danh sach."""
    names = [e for e in employees or [] if e]
    out = {n: [] for n in names}
    if not names:
        return out
    for r in frappe.get_all(CONTRACT, filters={"parenttype": EMPLOYEE, "parentfield": "ec_contracts",
                                               "parent": ["in", names]},
                            fields=CONTRACT_FIELDS, order_by="idx asc", limit_page_length=0):
        out.setdefault(r.parent, []).append(dict(r))
    return out


def user_cua_nhan_vien(employee):
    if not employee:
        return None
    return frappe.db.get_value(EMPLOYEE, employee, "user_id")


def user_dang_hoat_dong(user):
    if not user or user in ("Guest", "Administrator"):
        return False
    row = frappe.db.get_value("User", user, ["enabled", "user_type"], as_dict=True)
    return bool(row and row.enabled and row.user_type == "System User")


def quan_ly_truc_tiep(employee):
    """User cua quan ly truc tiep (reports_to -> user_id) neu con hoat dong, khong thi None."""
    rt = employee and frappe.db.get_value(EMPLOYEE, employee, "reports_to")
    user = rt and frappe.db.get_value(EMPLOYEE, rt, "user_id")
    return user if user_dang_hoat_dong(user) else None


def cap_dong_hop_dong(employee, values=None, sua_dong=None, employment_type=None):
    """Ghi ho so QUA doc.save (de lai Version - ai doi gi luc nao tra lai duoc).

    values   : dict dong moi (them dong) - bo qua neu None
    sua_dong : (ten_dong, {truong: gia_tri}) - sua mot dong co san
    employment_type : doi loai nhan su (None = giu nguyen)."""
    doc = frappe.get_doc(EMPLOYEE, employee)
    if sua_dong:
        ten, thay = sua_dong
        row = next((r for r in doc.get("ec_contracts") or [] if r.name == ten), None)
        if not row:
            frappe.throw("Không tìm thấy dòng hợp đồng %s trên hồ sơ %s." % (ten, employee))
        for k, v in thay.items():
            row.set(k, v)
    if values:
        doc.append("ec_contracts", values)
    if employment_type:
        doc.employment_type = employment_type
    doc.flags.ignore_permissions = True
    doc.save(ignore_permissions=True)
    return doc.name
