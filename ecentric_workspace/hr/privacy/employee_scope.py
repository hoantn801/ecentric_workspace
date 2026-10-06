# Copyright (c) 2026, eCentric and contributors
"""permission_query_conditions cho Employee: nguoi ngoai HR chi thay CHINH MINH trong
list / report / search / Link.

VI SAO (VA_BAO_MAT_2026-09-25.md muc 2)
    Frappe v16 KHONG chan filter tren field permlevel cao. Nhan vien goi
    /api/resource/Employee?filters=[["bank_ac_no","like","9%"]] van biet duoc dong nao khop,
    tuc la do ra so tai khoan / CCCD / phu cap cua nguoi khac tung ky tu mot.

    Ban dau la Server Script `ec_employee_list_scope` (chat Phan quyen, 28/09). Day la ban
    trong code, cung luat. Sau khi deploy, DISABLE script do (khong xoa) - hai dieu kien giong
    het nhau duoc Frappe AND lai nen de ca hai cung khong sai, chi thua.

KHONG CHAN: mo form qua link (van thay field L0), va code cua app dung frappe.get_all
(bo qua quyen) - portal /ec-hr, luong duyet, Team Pulse khong bi anh huong.

O CHON NHAN VIEN (Link Employee) - 03/10/2026, Phan quyen dong y
    Dieu kien "chi chinh minh" ap ca cho o Link: dong.diep mo Asset, o Custodian chi ra
    chinh ban ay. Rieng request `frappe.desk.search.search_link` / `search_widget` tren
    Employee nay tra ve moi ho so Active (+ chinh minh). An toan vi:
      * filter_guard (auth_hooks) da chan loc / sap xep / searchfield theo field L1/L2 tren
        ca hai duong nay -> khong do duoc so TK / CCCD qua o tim kiem;
      * search_fields va title_field cua Employee deu la employee_name -> o Link chi tra ma
        nhan vien + ho ten.
    List / report / get_list / get_count / /api/resource van chi chinh minh.
"""
import frappe

FULL_ACCESS_ROLES = frozenset({"System Manager", "HR Manager", "HR User", "EC CnB"})
LINK_SEARCH_METHODS = frozenset({"frappe.desk.search.search_link", "frappe.desk.search.search_widget"})
METHOD_PREFIXES = ("/api/method/", "/api/v2/method/")


def _request_cmd():
    """Ten method cua request hien tai ('' neu khong phai /api/method hay khong co request)."""
    path = ""
    try:
        req = getattr(frappe, "request", None)
        path = (getattr(req, "path", "") or "") if req is not None else ""
    except Exception:
        path = ""
    for prefix in METHOD_PREFIXES:
        if path.startswith(prefix):
            return path[len(prefix):].strip("/")
    try:
        return (getattr(frappe, "form_dict", None) or {}).get("cmd") or ""
    except Exception:
        return ""


def _is_employee_link_search():
    """O Link / o tim kiem dang hoi chinh DocType Employee. Loi bat ngo -> False (giu luat hep)."""
    try:
        if _request_cmd() not in LINK_SEARCH_METHODS:
            return False
        return ((getattr(frappe, "form_dict", None) or {}).get("doctype") or "") == "Employee"
    except Exception:
        return False


def employee_query_conditions(user=None, doctype=None, **kwargs):
    user = user or frappe.session.user
    if user == "Administrator" or FULL_ACCESS_ROLES.intersection(frappe.get_roles(user)):
        return ""
    me = "`tabEmployee`.`user_id` = {}".format(frappe.db.escape(user))
    if _is_employee_link_search():
        return "(`tabEmployee`.`status` = 'Active' or {})".format(me)
    return me
