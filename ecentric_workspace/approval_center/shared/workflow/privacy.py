# Copyright (c) 2026, eCentric and contributors
"""Phieu RIENG TU + NGUOI THEO DOI + quyen doc qua GAN PHIEU - MOT luat cho moi duong doc
(Dot 0 quy trinh nhan su, Hoan chot 22-23/11/2026).

Ai xem duoc mot phieu RIENG TU:
  * nguoi gui; nguoi co dong duyet trong snapshot (EC Approval Request Approver);
  * nguoi theo doi (EC Approval Request Watcher, chot luc gui tu participant_purpose="Notify");
  * nguoi xu ly cua phieu (fulfillment_owner / Fulfiller duoc cau hinh / ToDo tren chinh phieu);
  * nguoi duoc cap quyen doc qua GAN PHIEU (EC Approval Link Grant, chi dung phieu do);
  * System Manager - mo duoc nhung LUON de lai EC Approval Access Log.
KHONG xem duoc: truong phong (requester_department), Approval Admin, tab "Tat ca", thong ke,
export - du ho thay moi phieu thuong.

Phieu rieng tu khi nao: ApprovalDefinition.private = True (code) HOAC EC Approval Type.private
= 1 (cau hinh). Hai nguon OR voi nhau - them co o cau hinh khong can deploy, nhung khong ai
tat duoc co cua code tu man hinh.

Cac ham deu FAIL-CLOSED theo huong an toan cho du lieu: khong doc duoc danh sach loai rieng tu
thi coi la "khong co loai nao" CHI cho cac duong khong lien quan; rieng `scope_sql` neu loi thi
tra ve dieu kien chan het phieu rieng tu cua nguoi khac (khong bao gio mo rong pham vi).
Khong ten nguoi, khong ten role nao viet cung trong file nay.
"""
import frappe
from frappe.utils import now_datetime, add_to_date

WATCHER_DT = "EC Approval Request Watcher"
ACCESS_DT = "EC Approval Access Log"
GRANT_DT = "EC Approval Link Grant"
_APPROVER_DT = "EC Approval Request Approver"
#: Mot nguoi mo lai cung mot phieu trong khoang nay (F5, mo lai popup) thi khong ghi them dong.
ACCESS_THROTTLE_MINUTES = 5


# --------------------------------------------------------------------------- #
# Loai phieu rieng tu
# --------------------------------------------------------------------------- #
def _code_private_types():
    try:
        from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS
        return {code for code, d in APPROVAL_DEFINITIONS.items() if getattr(d, "private", False)}
    except Exception:
        return set()


def _config_private_types():
    try:
        if not frappe.db.has_column("EC Approval Type", "private"):
            return set()
        return set(frappe.get_all("EC Approval Type", filters={"private": 1}, pluck="name") or [])
    except Exception:
        return set()


def private_types():
    """Tap ma loai phieu rieng tu (code + cau hinh). Nho trong frappe.local cho mot request."""
    cache = getattr(frappe.local, "_ec_private_types", None)
    if cache is None:
        cache = frozenset(_code_private_types() | _config_private_types())
        try:
            frappe.local._ec_private_types = cache
        except Exception:
            pass
    return cache


def is_private_type(approval_type):
    return bool(approval_type) and approval_type in private_types()


def is_private_request(request_name):
    if not request_name:
        return False
    try:
        atype = frappe.db.get_value("EC Approval Request", request_name, "approval_type")
    except Exception:
        return False
    return is_private_type(atype)


# --------------------------------------------------------------------------- #
# Nguoi theo doi
# --------------------------------------------------------------------------- #
def watchers_of(request_name):
    if not request_name:
        return []
    try:
        return list(dict.fromkeys(frappe.get_all(
            WATCHER_DT, filters={"approval_request": request_name}, pluck="watcher") or []))
    except Exception:
        return []


def is_watcher(request_name, user):
    if not (request_name and user):
        return False
    try:
        return bool(frappe.db.exists(WATCHER_DT, {"approval_request": request_name,
                                                  "watcher": user}))
    except Exception:
        return False


def is_approver(request_name, user):
    if not (request_name and user):
        return False
    return bool(frappe.db.exists(_APPROVER_DT, {"approval_request": request_name,
                                                "approver": user}))


def has_link_grant(request_name, user):
    """Quyen doc qua GAN PHIEU: dong grant con hieu luc cho DUNG phieu nay."""
    if not (request_name and user):
        return False
    try:
        return bool(frappe.db.exists(GRANT_DT, {"target_request": request_name, "user": user,
                                                "active": 1}))
    except Exception:
        return False


def is_in_flow(request_name, user, requested_by=None, fulfillment_owner=None):
    """Nguoi "trong luong" cua phieu: gui / duyet / theo doi / chu viec xu ly."""
    if not user:
        return False
    if requested_by and requested_by == user:
        return True
    if fulfillment_owner and fulfillment_owner == user:
        return True
    return is_approver(request_name, user) or is_watcher(request_name, user)


def watcher_only(user, request_name, requested_by=None, fulfillment_owner=None):
    """True khi `user` CHI la nguoi theo doi - khong gui, khong duyet, khong xu ly, khong SM.
    Dung de an `watcher_hidden_fields` (vd luong offer)."""
    if not is_watcher(request_name, user):
        return False
    if requested_by == user or fulfillment_owner == user or is_approver(request_name, user):
        return False
    try:
        return "System Manager" not in frappe.get_roles(user)
    except Exception:
        return True


def redact_for_watcher(business_dict, definition, user, request_name):
    """Xoa `definition.watcher_hidden_fields` khoi ban chi tiet neu `user` chi la nguoi theo doi.
    Fail-closed: loi -> xoa."""
    fields = tuple(getattr(definition, "watcher_hidden_fields", ()) or ())
    if not fields or not request_name:
        return business_dict
    try:
        hide = watcher_only(user, request_name, business_dict.get("requested_by"),
                            business_dict.get("fulfillment_owner"))
    except Exception:
        hide = True
    if hide:
        for f in fields:
            if f in business_dict:
                business_dict[f] = None
    return business_dict


# --------------------------------------------------------------------------- #
# Nhat ky truy cap phieu rieng tu
# --------------------------------------------------------------------------- #
def _via(user, request_name):
    if has_link_grant(request_name, user):
        return "Gắn phiếu"
    try:
        if "System Manager" in frappe.get_roles(user):
            return "System Manager"
    except Exception:
        pass
    return "Người xử lý"


def note_access(user, request_name, approval_type=None, requested_by=None,
                fulfillment_owner=None, note=None):
    """Mo chi tiet mot phieu RIENG TU ma khong o trong luong -> ghi EC Approval Access Log.
    Goi SAU khi da qua cong can_view. Khong bao gio nem: thieu mot dong nhat ky khong duoc lam
    hong man hinh (loi duoc ghi Error Log de sua)."""
    try:
        if not request_name or not user or user == "Guest":
            return None
        atype = approval_type or frappe.db.get_value("EC Approval Request", request_name,
                                                     "approval_type")
        if not is_private_type(atype):
            return None
        if is_in_flow(request_name, user, requested_by, fulfillment_owner):
            return None
        via = _via(user, request_name)
        since = add_to_date(now_datetime(), minutes=-ACCESS_THROTTLE_MINUTES)
        if frappe.db.exists(ACCESS_DT, {"approval_request": request_name, "user": user,
                                        "via": via, "accessed_at": [">", since]}):
            return None
        row = frappe.get_doc({"doctype": ACCESS_DT, "approval_request": request_name,
                              "user": user, "via": via, "accessed_at": now_datetime(),
                              "note": note}).insert(ignore_permissions=True)
        return getattr(row, "name", None)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "privacy.note_access %s" % request_name)
        return None


def access_log(request_name, limit=30):
    try:
        return frappe.get_all(ACCESS_DT, filters={"approval_request": request_name},
                              fields=["user", "via", "accessed_at", "note"],
                              order_by="accessed_at desc", limit_page_length=limit) or []
    except Exception:
        return []


# --------------------------------------------------------------------------- #
# Pham vi danh sach (reporting.scope)
# --------------------------------------------------------------------------- #
def scope_sql(user, fulfil_types=None):
    """(manh SQL, params) loai phieu RIENG TU cua nguoi khac khoi moi truy van danh sach /
    thong ke / export (alias `r` = EC Approval Request). None khi khong co loai rieng tu nao.

    Ap cho MOI tang pham vi, ke ca admin (System Manager / Approval Admin): System Manager mo
    duoc phieu rieng tu bang duong dan (co nhat ky), nhung phieu khong nam trong danh sach."""
    types = sorted(private_types())
    if not types:
        return None
    params = {"priv_user": user or ""}
    keys = []
    for i, t in enumerate(types):
        k = "priv_t_%d" % i
        params[k] = t
        keys.append("%%(%s)s" % k)
    inlist = ", ".join(keys)
    parts = [
        "r.requested_by = %(priv_user)s",
        "EXISTS (SELECT 1 FROM `tabEC Approval Request Approver` pa "
        "WHERE pa.approval_request = r.name AND pa.approver = %(priv_user)s)",
        "EXISTS (SELECT 1 FROM `tabEC Approval Request Watcher` pw "
        "WHERE pw.approval_request = r.name AND pw.watcher = %(priv_user)s)",
    ]
    ft = [t for t in (fulfil_types or []) if t in types]
    for i, t in enumerate(ft):
        k = "priv_ft_%d" % i
        params[k] = t
        parts.append("r.approval_type = %%(%s)s" % k)
    sql = "(r.approval_type IS NULL OR r.approval_type NOT IN (%s) OR %s)" % (
        inlist, " OR ".join(parts))
    return sql, params
