# Copyright (c) 2026, eCentric and contributors
"""Doc / ghi DB cho Danh gia nhan su - service nhan module nay qua tham so `repo` (test thay gia).

Mot ngoai le co chu y: `khoi_phuc_cap_bi_bo` sua hai bang snapshot cua engine (EC Approval
Request Level / Approver) NGAY SAU khi engine.submit dung luong, truoc khi cap 1 duoc kich hoat.
Ly do: luat gop nguoi trung cap cua engine (`_skip_earlier_duplicate_levels`) bo cap Line
Manager khi LM cung la CEO - ma o form nay cap LM la buoc NHAP nhan xet bat buoc (Hoan chot
22/11: "LM = CEO thi giu cap"). Khong sua engine dung chung (Agent A dang lam engine); viec
khoi phuc chi cham dung phieu nay, co ghi nhat ky (EC Approval Action "Commented")."""
import json

import frappe
from frappe.utils import getdate, now_datetime, nowdate

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Employee Review"
SETTINGS_DT = "EC Employee Review Settings"
TEMPLATE_DT = "EC Employee Review Template"
REQ = "EC Approval Request"
LEVEL = "EC Approval Request Level"
APPROVER = "EC Approval Request Approver"
OPEN = ("Pending", "Information Required")


def today():
    return getdate(nowdate())


def now():
    return now_datetime()


def ngay_le():
    from ecentric_workspace.approval_center.shared.workflow import ngay_lam_viec
    return ngay_lam_viec.ngay_le_cong_ty()


def settings():
    out = {"tat_tu_dong": 0, "nguoi_gui_mac_dinh": None, "tran_mac_dinh": 60, "quy_tac": []}
    if not frappe.db.exists("DocType", SETTINGS_DT):
        return out
    doc = frappe.get_single(SETTINGS_DT)
    out.update(tat_tu_dong=int(doc.get("tat_tu_dong") or 0),
               nguoi_gui_mac_dinh=doc.get("nguoi_gui_mac_dinh") or None,
               tran_mac_dinh=int(doc.get("tran_thu_viec_mac_dinh") or 60),
               quy_tac=[{"ap_dung": r.ap_dung, "gia_tri": r.gia_tri, "tran_ngay": r.tran_ngay}
                        for r in doc.get("quy_tac_tran") or []])
    return out


def users_with_roles(roles):
    users = set(frappe.get_all("Has Role", filters={"role": ["in", list(roles)], "parenttype": "User"},
                               pluck="parent", limit_page_length=0) or [])
    users -= {"Administrator", "Guest", None}
    if not users:
        return []
    return sorted(frappe.get_all("User", filters={"name": ["in", list(users)], "enabled": 1,
                                                  "user_type": "System User"},
                                 pluck="name", limit_page_length=0) or [])


def roles_of(user):
    return frappe.get_roles(user)


def nguoi_gui_mac_dinh(cfg):
    """Nguoi gui cua nhap tu tao: cau hinh, khong thi nguoi dau tien (theo email) giu role EC CnB.
    Khong hardcode ai trong code."""
    u = cfg.get("nguoi_gui_mac_dinh")
    if u and frappe.db.get_value("User", u, "enabled"):
        return u
    pool = users_with_roles(("EC CnB",))
    return pool[0] if pool else None


def mau_tieu_chi(review_type):
    """(ten mau, [tieu chi]) - mau dang dung khop loai, khong thi mau 'Tat ca'. Khong co -> (None, [])."""
    if not frappe.db.exists("DocType", TEMPLATE_DT):
        return None, []
    for ap in (review_type, "Tất cả"):
        rows = frappe.get_all(TEMPLATE_DT, filters={"ap_dung_cho": ap, "dang_dung": 1},
                              pluck="name", order_by="modified desc", limit_page_length=1)
        if rows:
            return rows[0], tieu_chi_cua_mau(rows[0])
    return None, []


def tieu_chi_cua_mau(name):
    if not name or not frappe.db.exists(TEMPLATE_DT, name):
        return []
    doc = frappe.get_doc(TEMPLATE_DT, name)
    return [{"tieu_chi": r.tieu_chi, "mo_ta": r.mo_ta or "", "trong_so": int(r.trong_so or 1)}
            for r in doc.get("tieu_chi") or []]


def review_by_key(key):
    return frappe.db.get_value(BUSINESS_DT, {"dedupe_key": key}, "name")


def insert_review(fields):
    frappe.flags.ec_employee_review_auto = True
    try:
        doc = frappe.get_doc(dict(fields, doctype=BUSINESS_DT))
        doc.insert(ignore_permissions=True)
    finally:
        frappe.flags.ec_employee_review_auto = False
    return doc.name


def get_review(name, for_update=False):
    if for_update:
        frappe.db.get_value(BUSINESS_DT, name, "name", for_update=True)
    return frappe.get_doc(BUSINESS_DT, name)


def save(doc):
    doc.save(ignore_permissions=True)


def set_review(name, values):
    frappe.db.set_value(BUSINESS_DT, name, values)


def drafts_due(hom_nay):
    rows = frappe.get_all(BUSINESS_DT, filters={"auto_draft": 1, "da_huy_nhap": 0,
                                                "auto_submit_on": ["<=", hom_nay]},
                          fields=["name", "approval_request"], limit_page_length=0)
    return [r.name for r in rows if not r.approval_request]


def reviews(filters=None, fields=None, limit=2000):
    return [dict(r) for r in frappe.get_all(
        BUSINESS_DT, filters=filters or {}, limit_page_length=limit, order_by="hd_den_ngay asc",
        fields=fields or ["name", "request_title", "review_type", "nhan_vien", "ten_nhan_vien",
                          "employee_user", "hd_den_ngay", "auto_submit_on", "approval_request",
                          "requested_by", "da_huy_nhap", "auto_draft", "line_manager"])]


def request_info(req_name):
    if not req_name:
        return None
    row = frappe.db.get_value(REQ, req_name, ["name", "approval_status", "current_level",
                                              "requested_by"], as_dict=True)
    return dict(row) if row else None


def request_statuses(req_names):
    names = [n for n in req_names or [] if n]
    if not names:
        return {}
    return {r.name: dict(r) for r in frappe.get_all(REQ, filters={"name": ["in", names]},
                                                     fields=["name", "approval_status", "current_level"],
                                                     limit_page_length=0)}


def level_names(req_names):
    names = [n for n in req_names or [] if n]
    if not names:
        return {}
    out = {}
    for r in frappe.get_all(LEVEL, filters={"approval_request": ["in", names]},
                            fields=["approval_request", "level_no", "level_name", "due_at", "level_status"],
                            limit_page_length=0):
        out[(r.approval_request, r.level_no)] = dict(r)
    return out


def cap_dang_cho_toi(req_name, user):
    """So cap hien tai neu `user` co dong Pending o DUNG cap hien tai cua phieu dang Pending."""
    info = request_info(req_name)
    if not info or info["approval_status"] != "Pending" or not info["current_level"]:
        return None
    if frappe.db.exists(APPROVER, {"approval_request": req_name, "level_no": info["current_level"],
                                   "approver": user, "status": "Pending"}):
        return info["current_level"]
    return None


def la_nguoi_duyet_tu_cap(req_name, user, level_no):
    return bool(req_name and frappe.db.exists(
        APPROVER, {"approval_request": req_name, "approver": user, "level_no": [">=", level_no]}))


def level_status(req_name, level_no):
    return frappe.db.get_value(LEVEL, {"approval_request": req_name, "level_no": level_no},
                               "level_status")


def khoi_phuc_cap_bi_bo(req_name, level_nos, ly_do):
    """Dua cap bi luat gop-trung-nguoi danh Skipped luc dung luong ve Pending (xem docstring module).
    CHI goi giua engine.submit(activate_first_level=False) va kich hoat cap 1."""
    restored = []
    for n in level_nos:
        lv = frappe.db.get_value(LEVEL, {"approval_request": req_name, "level_no": n},
                                 ["name", "level_status", "level_name"], as_dict=True)
        if not lv or lv.level_status != "Skipped":
            continue
        frappe.db.set_value(LEVEL, lv.name, {"level_status": "Pending", "activated_at": None,
                                             "completed_at": None})
        for ap in frappe.get_all(APPROVER, filters={"approval_request": req_name, "level_no": n,
                                                    "status": "Skipped"}, pluck="name"):
            frappe.db.set_value(APPROVER, ap, {"status": "Pending", "decided_at": None})
        engine.log_action(req_name, "Commented", "Administrator", n, level_name=lv.level_name,
                          comment=ly_do, previous_status="Skipped", new_status="Pending")
        restored.append(n)
    return restored


def kich_hoat_cap_dau(req_name):
    req = frappe.get_doc(REQ, req_name)
    first = frappe.get_all(LEVEL, filters={"approval_request": req_name}, pluck="level_no",
                           order_by="level_no asc", limit_page_length=1)
    # Duong kich hoat DUY NHAT cua engine (cung cach platform/esign/requester.py goi).
    engine._activate_level(req, first[0] if first else 1)


def dat_cap_tra_lai(req_name, level_no):
    frappe.db.set_value(REQ, req_name, "information_requested_from_level", int(level_no))


def da_gia_han_thu_viec(nhan_vien):
    """Nhan vien da tung co danh gia thu viec ket qua Gia han (CEO da duyet) chua."""
    return bool(frappe.db.exists(BUSINESS_DT, {"nhan_vien": nhan_vien, "review_type": "Thử việc",
                                               "ket_qua": "Gia hạn"}))


def json_load(s, default):
    try:
        v = json.loads(s) if s else default
        return v if isinstance(v, type(default)) else default
    except (TypeError, ValueError):
        return default
