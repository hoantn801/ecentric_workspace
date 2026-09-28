# Copyright (c) 2026, eCentric and contributors
"""Pham vi doc cua `Weekly Team Update`.

VI SAO TON TAI: truoc ban nay, Custom DocPerm cho role Employee la
read=1, if_owner=0 va KHONG co `permission_query_conditions`. Nghia la moi nhan
vien doc duoc moi bao cao tuan cua moi nguoi -- ca danh sach lan tung ban ghi.
Bao cao cua nhom Management nam trong so do.

Luat duoi day port nguyen tu Server Script tam `ec_wtu_list_scope`
(Permission Query, dang disabled=1 luc chup 28/09). Port NGUYEN, khong "cai
tien" nhan the: luat tam da duoc Hoan duyet, moi khac biet giua hai ban la mot
cho co the ro ri ma khong ai nhin lai.

MOT DIEU PHAI NHO: `frappe.db.get_value` va `frappe.db.sql` KHONG di qua lop
quyen nao het -- khong qua `permission_query_conditions`, khong qua
`has_permission`. File nay chi bit duong Desk, REST `/api/resource`, va report
native. Cho nao trong app tu doc DocType bang db.* thi phai tu goi
`assert_can_read()`; xem `can_read()` o cuoi file.
"""

import frappe

#: Phong ban duoc xem TAT CA, va dong thoi la phong ban KHONG ai ngoai duoc xem.
MANAGEMENT_DEPARTMENT = "Management - EC"

DOCTYPE = "Weekly Team Update"

#: SQL hop le nhung khong khop ban ghi nao. Dung khi phai chan sach.
_MATCH_NOTHING = "`tabWeekly Team Update`.name = '__ec_none__'"


def _employee_of(user):
    """-> {name, department} cua nhan vien DANG LAM VIEC, hoac None.

    Loc `status = Active` la co chu dinh: nguoi da nghi thi khong con suy ra
    duoc pham vi phong ban nua, va roi ve "chi thay bao cao minh nop". Fail
    dong, khong fail mo.
    """
    try:
        return frappe.db.get_value(
            "Employee", {"user_id": user, "status": "Active"},
            ["name", "department"], as_dict=True,
        )
    except Exception:
        return None


def _viewer_rows(user):
    """Cac dong `EC Viewer Permission` cua user. -> [(scope, custom_department)].

    Khoa dinh danh o DocType nay la `user_email`, KHONG phai `name`.
    """
    try:
        rows = frappe.get_all(
            "EC Viewer Permission", filters={"user_email": user},
            fields=["scope", "custom_department"], limit_page_length=0,
            ignore_permissions=True,
        )
    except Exception:
        return []
    return [(r.get("scope"), r.get("custom_department")) for r in rows]


def _in_management(emp):
    """Thuoc Management theo phong ban chinh HOAC theo bang kiem nhiem."""
    if not emp:
        return False
    if emp.get("department") == MANAGEMENT_DEPARTMENT:
        return True
    try:
        return bool(frappe.get_all(
            "Employee Department Membership",
            filters={"parent": emp.get("name"),
                     "department": MANAGEMENT_DEPARTMENT},
            fields=["name"], limit=1, ignore_permissions=True,
        ))
    except Exception:
        # Bang kiem nhiem la duong PHU. Thieu no thi mat quyen xem rong, chu
        # khong duoc mo quyen ra.
        return False


def compute_scope(user=None):
    """-> {"full": bool, "employee": str|None, "departments": [str]}.

    `full`  : xem duoc tat ca.
    `employee`  : ma nhan vien, de khop cot `employee`.
    `departments`: phong ban duoc xem qua `EC Viewer Permission` scope=dept,
                   DA loai Management -- mot dong tro vao Management bi bo qua
                   co chu dinh, vi nhom do chi nguoi trong nhom moi duoc xem.
    """
    user = user or frappe.session.user
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return {"full": True, "employee": None, "departments": []}

    emp = _employee_of(user)
    rows = _viewer_rows(user)

    if _in_management(emp):
        return {"full": True, "employee": (emp or {}).get("name"), "departments": []}
    for scope, _dept in rows:
        if scope == "all":
            return {"full": True, "employee": (emp or {}).get("name"), "departments": []}

    depts = []
    for scope, dept in rows:
        if scope == "dept" and dept and dept != MANAGEMENT_DEPARTMENT and dept not in depts:
            depts.append(dept)
    return {"full": False, "employee": (emp or {}).get("name"), "departments": depts}


def _cached_scope(user):
    """Nho ket qua trong pham vi MOT request.

    `permission_query_conditions` bi goi lai o moi truy van danh sach; khong nho
    thi moi lan lai 3-4 luot DB. Nho o `frappe.local` chu khong o cache lien
    request: quyen doi giua chung phai co hieu luc ngay, khong doi het TTL.
    """
    try:
        store = frappe.local.ec_wtu_scope
    except AttributeError:
        store = {}
        frappe.local.ec_wtu_scope = store
    if user not in store:
        store[user] = compute_scope(user)
    return store[user]


def wtu_query_conditions(user=None):
    """Menh de WHERE cho danh sach `Weekly Team Update`. "" = khong han che."""
    user = user or frappe.session.user
    scope = _cached_scope(user)
    if scope["full"]:
        return ""
    parts = ["`tabWeekly Team Update`.`submitter` = " + frappe.db.escape(user)]
    if scope["employee"]:
        parts.append("`tabWeekly Team Update`.`employee` = "
                     + frappe.db.escape(scope["employee"]))
    if scope["departments"]:
        joined = ", ".join(frappe.db.escape(d) for d in scope["departments"])
        parts.append("`tabWeekly Team Update`.`department` in (%s)" % joined)
    return "(" + " or ".join(parts) + ")"


def can_read(doc, user=None):
    """Mot ban ghi co duoc doc khong. `doc` la dict/Document, hoac ten ban ghi.

    Day la ban don-ban-ghi cua `wtu_query_conditions`. Hai ham PHAI cung mot
    luat: lech nhau thi danh sach giau ban ghi con trang chi tiet van mo duoc
    -- va ten ban ghi (`WTU-2026-W39-NV00162`) thi doan duoc, khong phai bi mat.
    """
    user = user or frappe.session.user
    scope = _cached_scope(user)
    if scope["full"]:
        return True

    if isinstance(doc, str):
        doc = frappe.db.get_value(
            DOCTYPE, doc, ["submitter", "employee", "department"], as_dict=True
        ) or {}
    get = doc.get if hasattr(doc, "get") else (lambda k: getattr(doc, k, None))

    if get("submitter") == user:
        return True
    if scope["employee"] and get("employee") == scope["employee"]:
        return True
    if get("department") and get("department") in scope["departments"]:
        return True
    return False


def assert_can_read(doc, user=None):
    """Dung cho MOI duong tu doc DocType bang `frappe.db.*` (Web Page, app
    method, Server Script). Cac ham hook o duoi KHONG che duoc nhung duong do.
    """
    if not can_read(doc, user):
        frappe.throw("Ban khong co quyen xem bao cao nay.", frappe.PermissionError)


def can_view_weekly_record(name):
    """Ban cho Jinja goi tu Web Page. -> True/False, KHONG BAO GIO nem loi.

    Trang /weekly-update doc ban ghi bang `frappe.db.get_value` ngay trong
    template, ke ca khi ten ban ghi den tu `?view=` do nguoi dung go. Duong do
    khong di qua `has_permission`, nen hai hook o tren khong che duoc no; day la
    cho duy nhat bit duoc.

    Khong nem loi vi mot ngoai le trong Jinja lam VO CA TRANG, ke ca phan nop
    bao cao cua chinh nguoi do. Tu choi thi tra False de template hien thong bao
    -- chan phai la chan mot muc, khong phai hong ca trang.

    Dang ky trong hooks.py duoi `jinja.methods` de template goi bang ten ngan.
    """
    try:
        if not name:
            return False
        return bool(can_read(name))
    except Exception:
        # Hong thi coi nhu KHONG duoc xem. Fail dong.
        frappe.log_error(
            message=frappe.get_traceback(),
            title="wtu can_view_weekly_record",
        )
        return False


def wtu_has_permission(doc, ptype=None, user=None):
    """Chot don-ban-ghi cho REST `/api/resource` va form Desk.

    CHI siet READ. Moi ptype khac tra True de nhuong cho DocPerm: luong nop bao
    cao dang ghi qua duong rieng, siet them o day thi gay hong nop -- mot loi
    nang hon loi dang sua.
    """
    if ptype not in ("read", None):
        return True
    return can_read(doc, user)
