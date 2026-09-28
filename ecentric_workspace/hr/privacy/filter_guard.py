# Copyright (c) 2026, eCentric and contributors
"""before_request: TU CHOI moi list / count / search / export tren Employee (va bang con cua no)
ma filters / or_filters / fields / order_by / group_by... nhac toi field nguoi goi KHONG doc duoc.

VI SAO (VA_BAO_MAT_2026-09-25.md, "rui ro con lai" cua muc 2 - Hoan chot 28/09: CHAN)
    Frappe v16 bo cot khong doc duoc ra khoi SELECT, nhung KHONG kiem WHERE / ORDER BY. Ai loc
    duoc thi do duoc: `bank_ac_no like '9%'` tra ve dong nao -> biet ky tu dau, lap lai la ra ca
    so. `employee_scope` da khoa nhan vien thuong vao dung dong cua ho; con HR User (khong co L1)
    thi van thay het danh sach -> van do duoc. Hook nay dong cho do cho MOI nguoi thieu quyen.

"KHONG DOC DUOC" = khong co trong permlevels.readable_fields: lech permlevel, hoac bi mask.
Nguoi doc duoc het (HR Manager, EC CnB, Administrator) -> thoat ngay, khong ton gi.

DUONG VAO DUOC CHAN (danh sach Hoan giao):
    /api/resource/<dt>, /api/v2/document/<dt>, /api/v2/doctype/<dt>/count
    frappe.client.get_list / get_count / get_value
    frappe.desk.reportview.get / get_list / get_count / export_query / get_stats
    frappe.desk.search.search_link / search_widget
    frappe.desk.listview.get_group_by_count
Code server cua app (frappe.get_all, API rieng) KHONG di qua day - hook chi doc tham so HTTP.
Loi bat ngo khi phan tich -> tu choi (dong cua); ghi Error Log de biet.
"""
import frappe
from frappe import _

from ecentric_workspace.hr.privacy import permlevels
from ecentric_workspace.hr.privacy.filter_refs import referenced_fields, violations

GUARDED_DOCTYPE = "Employee"
GUARDED_METHODS = frozenset({
    "frappe.client.get_list", "frappe.client.get_count", "frappe.client.get_value",
    "frappe.desk.reportview.get", "frappe.desk.reportview.get_list",
    "frappe.desk.reportview.get_count", "frappe.desk.reportview.export_query",
    "frappe.desk.reportview.get_stats",
    "frappe.desk.search.search_link", "frappe.desk.search.search_widget",
    "frappe.desk.listview.get_group_by_count",
})
METHOD_PREFIXES = ("/api/method/", "/api/v2/method/")
RESOURCE_PREFIXES = ("/api/resource/", "/api/v2/document/", "/api/v2/doctype/")


def guard_employee_filters():
    """Hook `before_request`. Khong lam gi voi request khong lien quan Employee."""
    try:
        doctype = _target_doctype()
    except Exception:
        # Hook nay chay cho MOI request: khong nhan dien duoc thi de yen, dung lam sap ca site.
        return
    if not doctype or frappe.session.user == "Administrator":
        return
    base = _base_doctype(doctype)
    if not base:
        return
    try:
        restricted, table_to_child = permlevels.restricted_fields(GUARDED_DOCTYPE)
        if not any(restricted.values()):
            return
        refs = referenced_fields(frappe.form_dict, doctype, table_to_child)
        bad = violations(refs, restricted)
    except Exception:
        frappe.log_error(title="EC: filter_guard khong phan tich duoc request Employee")
        bad = ["?"]
    if bad:
        frappe.throw(_("Bạn không có quyền lọc, sắp xếp hoặc chọn theo trường này của hồ sơ "
                       "nhân sự: {0}").format(", ".join(bad)), frappe.PermissionError)


def _target_doctype():
    """DocType ma request nham toi, hoac None neu khong phai mot duong vao can chan."""
    path = (frappe.request.path if getattr(frappe, "request", None) else "") or ""
    for prefix in RESOURCE_PREFIXES:
        if path.startswith(prefix):
            rest = path[len(prefix):].strip("/").split("/")
            is_list = len(rest) == 1 or (prefix == "/api/v2/doctype/" and rest[1:] == ["count"])
            return rest[0] if is_list and frappe.request.method == "GET" else None
    cmd = ""
    for prefix in METHOD_PREFIXES:
        if path.startswith(prefix):
            cmd = path[len(prefix):].strip("/")
            break
    cmd = cmd or frappe.form_dict.get("cmd") or ""
    if cmd in GUARDED_METHODS:
        return frappe.form_dict.get("doctype")
    return None


def _base_doctype(doctype):
    """Employee -> Employee. Bang con cua Employee (vd EC Employee Contract) -> Employee, CHI khi
    request neu ro parent la Employee (bang con dung chung voi DocType khac thi khong dung vao)."""
    if doctype == GUARDED_DOCTYPE:
        return GUARDED_DOCTYPE
    if frappe.form_dict.get("parent") == GUARDED_DOCTYPE and \
            doctype in permlevels.child_doctypes(GUARDED_DOCTYPE):
        return GUARDED_DOCTYPE
    return None
