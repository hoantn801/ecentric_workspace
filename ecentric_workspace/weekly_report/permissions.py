# Copyright (c) 2026, eCentric and contributors
"""Pham vi doc cua `Weekly Team Update`.

VI SAO TON TAI: truoc ban nay, Custom DocPerm cho role Employee la
read=1, if_owner=0 va KHONG co `permission_query_conditions`. Nghia la moi nhan
vien doc duoc moi bao cao tuan cua moi nguoi -- ca danh sach lan tung ban ghi.
Bao cao cua nhom Management nam trong so do.

Luat duoi day port tu Server Script tam `ec_wtu_list_scope` (Permission Query,
disabled=1 luc chup 28/09), CONG chuoi quan ly.

Ban dau port nguyen, khong them bot. Sau khi deploy moi thay `ec_wtu_list_scope`
va `/team-pulse` von da KHAC nhau: `team_pulse_data` (PERMISSION-V2, 20/07/2026)
cho nguoi thuong xem ban than + toan bo cap duoi theo `Employee.reports_to`, con
`ec_wtu_list_scope` khong he biet den chuoi quan ly. Bat luat moi len la 4 quan
ly nhin thay tom tat cua 10 cap duoi tren /team-pulse nhung bam vao thi
/weekly-update?view= tra "khong co quyen".

Nen o day lay HOP cua hai ban, de mot du lieu chi co mot luat. Chuoi quan ly
KHONG bao gio di xuyen qua `Management - EC`: nhom do van kin, ke ca khi
`reports_to` co tro vao trong do.

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


#: Chan vong lap `reports_to` tro nguoc. `team_pulse_data` dung 15; giu bang de
#: hai ben khong bao gio le nhau o mot cay sau bat thuong.
CHAIN_MAX_DEPTH = 15


def _subordinates(emp_name):
    """Toan bo cap duoi cua mot nhan vien, de quy. -> [ma nhan vien].

    Duyet theo tang (BFS) chu khong de quy: `reports_to` la du lieu nguoi nhap,
    va mot vong tro nguoc se lam de quy chay den het stack. Bien dem chan them
    mot lan nua.

    `Management - EC` bi loai CA khoi ket qua LAN khoi duong duyet. Loai khoi
    ket qua thoi la chua du: neu mot nguoi ngoai co ai do trong Management nam
    duoi minh, duyet xuyen qua se keo ve ca nhung nguoi duoi nguoi do.
    """
    if not emp_name:
        return []
    try:
        rows = frappe.get_all(
            "Employee", filters={"status": "Active"},
            fields=["name", "reports_to", "department"],
            limit_page_length=0, ignore_permissions=True,
        )
    except Exception:
        return []

    kids = {}
    for r in rows:
        if r.get("department") == MANAGEMENT_DEPARTMENT:
            continue                      # khong duyet xuyen qua Management
        parent = r.get("reports_to")
        if parent:
            kids.setdefault(parent, []).append(r["name"])

    out, frontier, depth = [], [emp_name], 0
    while frontier and depth < CHAIN_MAX_DEPTH:
        depth += 1
        nxt = []
        for p in frontier:
            for c in kids.get(p, []):
                if c not in out and c != emp_name:
                    out.append(c)
                    nxt.append(c)
        frontier = nxt
    return out


def compute_scope(user=None):
    """-> {"full", "employee", "departments", "subordinates"}.

    `full`      : xem duoc tat ca.
    `employee`  : ma nhan vien, de khop cot `employee`.
    `departments`: phong ban duoc xem qua `EC Viewer Permission` scope=dept,
                   DA loai Management -- mot dong tro vao Management bi bo qua
                   co chu dinh, vi nhom do chi nguoi trong nhom moi duoc xem.
    `subordinates`: cap duoi theo `reports_to`, de quy, KHONG xuyen Management.
                   Co de khop voi /team-pulse; xem chu thich dau file.
    """
    user = user or frappe.session.user
    full = {"full": True, "employee": None, "departments": [], "subordinates": []}
    if user == "Administrator" or "System Manager" in frappe.get_roles(user):
        return full

    emp = _employee_of(user)
    rows = _viewer_rows(user)
    emp_name = (emp or {}).get("name")

    if _in_management(emp):
        full["employee"] = emp_name
        return full
    for scope, _dept in rows:
        if scope == "all":
            full["employee"] = emp_name
            return full

    depts = []
    for scope, dept in rows:
        if scope == "dept" and dept and dept != MANAGEMENT_DEPARTMENT and dept not in depts:
            depts.append(dept)
    return {"full": False, "employee": emp_name, "departments": depts,
            "subordinates": _subordinates(emp_name)}


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
    if scope["subordinates"]:
        joined = ", ".join(frappe.db.escape(e) for e in scope["subordinates"])
        parts.append("`tabWeekly Team Update`.`employee` in (%s)" % joined)
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
    if get("employee") and get("employee") in scope["subordinates"]:
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
