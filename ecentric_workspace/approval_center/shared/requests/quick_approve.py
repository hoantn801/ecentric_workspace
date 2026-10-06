# Copyright (c) 2026, eCentric and contributors
"""Duyet nhanh "Cho toi duyet" tren dien thoai (06/10/2026, Hoan).

Mot nguoi duyet mo "Viec cua toi" -> "Cho toi duyet" thay MOI phieu dang cho chinh ho, xem tom
tat va bam Duyet / Tu choi / Yeu cau bo sung ngay tai cho.

HOP DONG API (HR - nghi phep, giai trinh, chot cong, phan bo cong viec - se noi vao sau theo
dung hop dong nay; moi dong la mot dict):
    request        ten EC Approval Request (khoa de goi quick_decide)
    approval_type  ma loai phieu;   type_label  ten loai de nhom tren man hinh
    reference_doctype / reference_name   chung tu nghiep vu
    title          tieu de phieu;   requested_by / requester_name;   submitted_at
    due_at         han cua cap hien tai (co the None)
    level_no / level_name   cap hien tai
    detail_url     trang chi tiet cua form ("/<route>?id=<ten>")
    summary        [{"label", "value"}] 0-5 cap, gia tri DA dinh dang kieu Viet Nam
    capabilities   {can_approve, can_reject, can_request_info, needs_input,
                    needs_input_reason, comment_required, sign_required}
    sign_files     [{"dsf", "file_name"}] tai lieu SE KY cua cap nay (khi sign_required) - man
                   hinh mo qua platform.esign.api.get_package_file (co kiem quyen), khong lo
                   duong dan /private/files.

NGUON SU THAT: dong approver `Pending` DUNG cap hien tai (`current_level`) cua phieu dang
`Pending`, cap do dang `In Progress`. KHONG suy tu cay to chuc, khong suy tu ToDo.

KY SO (07/10/2026, Hoan chot "vao thang B"): cap bat buoc ky -> action "approve_sign" goi
DUNG chuc nang ky chinh thuc platform.esign.api.approve_and_sign (cung duong popup trang
"Tat ca yeu cau" va form dang dung). Nut "Duyet" thuong bi chan o cap nay. Tu choi / yeu cau bo
sung o cap ky van di controller cua form (y nhu trang form lam).

QUYET DINH (quick_decide) di qua DUNG controller cua loai phieu
(features.<feature>.controllers.api.approve / reject / request_information) - duong ma trang
form goi - de moi kiem tra nghiep vu rieng cua form van chay. KHONG goi engine thang. Loai nao
luc duyet phai nhap/chinh them (ky so, chinh so tien duyet, ngay du kien cua Operation) thi
needs_input=true: man hinh chi mo trang chi tiet, va quick_decide tu choi.
Loi -> rollback ve savepoint, bao ro ly do. Thieu quyen bao bang loi nghiep vu (417) chu khong
phai 403, de man hinh khong hieu nham la het phien dang nhap.
"""
import importlib
import inspect

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.registry import feature_of, get_definition
from ecentric_workspace.approval_center.shared.requests import capabilities as _caps
from ecentric_workspace.approval_center.shared.workflow import permissions as _perm

_REQ = "EC Approval Request"
_APPROVER = "EC Approval Request Approver"
_LEVEL = "EC Approval Request Level"
MAX_SUMMARY = 5
#: Truong luong ca nhan KHONG BAO GIO len the duyet nhanh, ke ca khi ai do khai nham vao
#: quick_summary. Chot thu hai sau test khai bao.
_SALARY_MARKERS = ("salary", "luong", "incentive", "total_bonus", "gross", "base_pay")
ACTIONS = {"approve": "approve", "approve_sign": "approve_sign", "reject": "reject",
           "request_information": "request_information", "request_info": "request_information"}


class QuickDecideError(frappe.ValidationError):
    """Loi nghiep vu cua duyet nhanh (HTTP 417) - man hinh hien nguyen van cau nay."""


def _is_salary_field(fieldname):
    f = (fieldname or "").lower()
    return any(m in f for m in _SALARY_MARKERS)


# ----------------------------------------------------------------------------- helpers
def _controller(definition):
    feature = feature_of(definition.code)
    if not feature:
        return None
    try:
        return importlib.import_module(
            "ecentric_workspace.approval_center.features.%s.controllers.api" % feature)
    except ImportError:
        return None


def _capabilities(definition, user, biz, req):
    """Dung ham capability RIENG cua form neu co (AI Topup co co chinh so tien), khong thi
    ham chung. Ca hai deu la ham trang form dang dung."""
    mod = _controller(definition)
    fn = getattr(mod, "_capabilities", None) if mod else None
    try:
        return (fn(user, biz, req) if callable(fn) else _caps.derive(user, biz, req)) or {}
    except Exception:
        frappe.log_error(frappe.get_traceback(), "quick_approve.capabilities %s" % req.name)
        return {}


def _needs_input(definition, caps, level_name, biz):
    """-> (bool, ly do). Loai nao duyet phai nhap them thi khong duyet nhanh duoc."""
    if caps.get("can_adjust_approved_amount"):
        return True, _("Cần xác nhận số tiền được duyệt - mở trang chi tiết.")
    mod = _controller(definition)
    approve = getattr(mod, "approve", None) if mod else None
    if approve is not None and level_name == "Operation Review":
        try:
            params = inspect.signature(approve).parameters
        except (TypeError, ValueError):
            params = {}
        if "operation_expected_completion_date" in params \
                and not biz.get("operation_expected_completion_date"):
            return True, _("Cần nhập ngày dự kiến hoàn thành (Operation) - mở trang chi tiết.")
    return False, ""


def _sign_files(business_doctype, business_name):
    """Tep SE KY cua goi ky hien hanh (khong bi thay the). Loi -> [] (the van hien, chi thieu
    link xem tai lieu)."""
    try:
        pk = frappe.get_all("EC Digital Signature Package",
                            filters={"business_doctype": business_doctype,
                                     "business_name": business_name},
                            fields=["name", "superseded_by", "status"],
                            order_by="creation desc", limit_page_length=5) or []
        pk = [p for p in pk if not p.get("superseded_by") and p.get("status") != "Cancelled"]
        if not pk:
            return []
        rows = frappe.get_all("EC Digital Signature File",
                              filters={"package": pk[0].name, "requires_signature": 1},
                              fields=["name", "file_name"], order_by="idx_order asc") or []
        return [{"dsf": r.name, "file_name": r.file_name} for r in rows]
    except Exception:
        frappe.log_error(frappe.get_traceback(), "quick_approve.sign_files %s" % business_name)
        return []


def _fmt(value, fieldtype):
    if value in (None, ""):
        return ""
    try:
        if fieldtype in ("Currency", "Int") or (fieldtype == "Float" and float(value).is_integer()):
            n = float(value)
            if n.is_integer():
                return "{:,.0f}".format(n).replace(",", ".")
            return "{:,.2f}".format(n).replace(",", "X").replace(".", ",").replace("X", ".")
        if fieldtype == "Float":
            return ("%g" % float(value)).replace(".", ",")
        if fieldtype == "Percent":
            return ("%g%%" % float(value)).replace(".", ",")
        if fieldtype == "Check":
            return _("Có") if int(value) else _("Không")
        if fieldtype == "Date":
            from frappe.utils import getdate
            d = getdate(value)
            return "%02d/%02d/%04d" % (d.day, d.month, d.year)
        if fieldtype == "Datetime":
            from frappe.utils import get_datetime
            d = get_datetime(value)
            return "%02d/%02d/%04d %02d:%02d" % (d.day, d.month, d.year, d.hour, d.minute)
    except Exception:
        pass
    return str(value)


def build_summary(definition, biz_dict, request=None):
    """3-5 cap (nhan, gia tri) cua loai phieu. Ap redactor cua form (an luong) TRUOC khi lay."""
    if getattr(definition, "business_redactor", None):
        definition.business_redactor(biz_dict, request)
    try:
        meta = frappe.get_meta(definition.business_doctype)
        types = {df.fieldname: df.fieldtype for df in meta.fields}
    except Exception:
        types = {}
    out = []
    for label, field in (definition.quick_summary or ())[:MAX_SUMMARY]:
        if _is_salary_field(field):
            continue
        value = _fmt(biz_dict.get(field), types.get(field))
        if value:
            out.append({"label": label, "value": value})
    return out


_TYPE_CACHE = {}


def _type_meta(approval_type):
    if approval_type not in _TYPE_CACHE:
        t = frappe.db.get_value("EC Approval Type", approval_type,
                                ["approval_title", "route"], as_dict=True) or {}
        _TYPE_CACHE[approval_type] = (t.get("approval_title") or approval_type,
                                      (t.get("route") or "").strip())
    return _TYPE_CACHE[approval_type]


# ------------------------------------------------------------------------------ list
def _pending_requests(user):
    """[(request_doc_dict, level_dict)] - phieu dang Pending ma user co dong Pending o
    DUNG cap hien tai, cap do dang In Progress."""
    mine = frappe.get_all(_APPROVER, filters={"approver": user, "status": "Pending"},
                          fields=["approval_request", "level_no"], limit_page_length=0) or []
    if not mine:
        return []
    levels_by_req = {}
    for r in mine:
        levels_by_req.setdefault(r.approval_request, set()).add(r.level_no)
    reqs = frappe.get_all(_REQ, filters={"name": ["in", sorted(levels_by_req)],
                                         "approval_status": "Pending"},
                          fields=["name", "approval_type", "reference_doctype", "reference_name",
                                  "requested_by", "submitted_at", "current_level"],
                          limit_page_length=0) or []
    out = []
    for req in reqs:
        if not req.current_level or req.current_level not in levels_by_req.get(req.name, ()):
            continue
        lv = frappe.db.get_value(_LEVEL, {"approval_request": req.name,
                                          "level_no": req.current_level},
                                 ["level_name", "level_status", "due_at"], as_dict=True)
        if not lv or lv.level_status != "In Progress":
            continue
        out.append((req, lv))
    return out


def list_my_pending(user=None):
    user = user or frappe.session.user
    rows, names_cache = [], {}
    for req, lv in _pending_requests(user):
        try:
            definition = get_definition(req.approval_type)
        except KeyError:
            continue                      # loai chua dang ky (HR noi vao sau)
        try:
            biz = frappe.get_doc(definition.business_doctype, req.reference_name)
        except frappe.DoesNotExistError:
            continue
        if not _perm.can_view_request(req.name, user, definition.business_doctype,
                                      biz.get("requested_by"), biz.get("fulfillment_owner"),
                                      req.approval_type, req.reference_name):
            continue
        req_doc = frappe.get_doc(_REQ, req.name)
        caps = _capabilities(definition, user, biz, req_doc)
        need, why = _needs_input(definition, caps, lv.level_name, biz)
        label, route = _type_meta(req.approval_type)
        who = req.requested_by
        if who not in names_cache:
            names_cache[who] = frappe.db.get_value("User", who, "full_name") or who
        rows.append({
            "request": req.name,
            "approval_type": req.approval_type,
            "type_label": label,
            "reference_doctype": definition.business_doctype,
            "reference_name": req.reference_name,
            "title": biz.get("request_title") or req.reference_name,
            "requested_by": who,
            "requester_name": names_cache[who],
            "submitted_at": str(req.submitted_at) if req.submitted_at else None,
            "due_at": str(lv.due_at) if lv.due_at else None,
            "level_no": req.current_level,
            "level_name": lv.level_name,
            "detail_url": ("/" + route.lstrip("/") + "?id=" + req.reference_name) if route else None,
            "summary": build_summary(definition, biz.as_dict(), req_doc),
            "capabilities": {
                "can_approve": bool(caps.get("can_approve")),
                "can_reject": bool(caps.get("can_reject")),
                "can_request_info": bool(caps.get("can_request_information")),
                "needs_input": need,
                "needs_input_reason": why,
                "comment_required": bool(definition.quick_comment_required),
                "sign_required": bool(caps.get("requires_signature")),
            },
            "sign_files": (_sign_files(definition.business_doctype, req.reference_name)
                           if caps.get("requires_signature") else []),
        })
    rows.sort(key=lambda r: (r["due_at"] is None, r["due_at"] or "", r["submitted_at"] or ""))
    return {"rows": rows, "count": len(rows)}


def count_my_pending(user=None):
    return len(_pending_requests(user or frappe.session.user))


# ------------------------------------------------------------------------------ decide
def quick_decide(request_name, action, comment=None, user=None):
    user = user or frappe.session.user
    method = ACTIONS.get((action or "").strip())
    if not method:
        raise QuickDecideError(_("Thao tác không hợp lệ."))
    req = frappe.db.get_value(_REQ, request_name,
                              ["name", "approval_type", "reference_name", "approval_status",
                               "current_level"], as_dict=True)
    if not req:
        raise QuickDecideError(_("Không tìm thấy phiếu {0}.").format(request_name))
    try:
        definition = get_definition(req.approval_type)
    except KeyError:
        raise QuickDecideError(_("Loại phiếu này chưa hỗ trợ duyệt nhanh - mở trang chi tiết."))
    if not _perm.is_actionable(req.name, req.current_level, user, req.approval_status):
        raise QuickDecideError(_("Bạn không còn là người duyệt của bước hiện tại - phiếu có thể "
                                 "đã được người khác xử lý, đã bị trả lại hoặc đã đổi bước."))
    comment = (comment or "").strip()
    if method in ("reject", "request_information") and not comment:
        raise QuickDecideError(_("Cần ghi lý do."))
    if method in ("approve", "approve_sign") and definition.quick_comment_required and not comment:
        raise QuickDecideError(_("Loại phiếu này bắt buộc nhập nhận xét khi duyệt."))
    biz = frappe.get_doc(definition.business_doctype, req.reference_name)
    lv_name = frappe.db.get_value(_LEVEL, {"approval_request": req.name,
                                           "level_no": req.current_level}, "level_name")
    caps = _capabilities(definition, user, biz, frappe.get_doc(_REQ, req.name))
    need, why = _needs_input(definition, caps, lv_name, biz)
    if need and method in ("approve", "approve_sign"):
        raise QuickDecideError(why)
    sign = bool(caps.get("requires_signature"))
    if method == "approve" and sign:
        raise QuickDecideError(_("Bước này bắt buộc ký số - dùng nút \"Duyệt & Ký\"."))
    if method == "approve_sign":
        if not sign:
            raise QuickDecideError(_("Bước này không yêu cầu ký số - dùng nút \"Duyệt\"."))
        from ecentric_workspace.platform.esign import api as esign_api

        def fn(name, comment=None):
            return esign_api.approve_and_sign(definition.business_doctype, name, comment=comment)
    else:
        mod = _controller(definition)
        fn = getattr(mod, method, None) if mod else None
    if not callable(fn):
        raise QuickDecideError(_("Loại phiếu này chưa hỗ trợ duyệt nhanh - mở trang chi tiết."))
    sp = "ec_quick_decide"
    frappe.db.savepoint(sp)
    try:
        fn(req.reference_name, comment=comment or None)
    except Exception as e:
        frappe.db.rollback(save_point=sp)
        msg = _extract(e)
        if isinstance(e, frappe.PermissionError):
            raise QuickDecideError(_("Không đủ quyền thực hiện: {0}").format(msg))
        if isinstance(e, frappe.ValidationError):
            raise QuickDecideError(msg)
        frappe.log_error(frappe.get_traceback(), "quick_decide %s %s" % (method, request_name))
        raise QuickDecideError(_("Không thực hiện được ({0}). Đã hoàn tác, thử lại sau.").format(msg))
    return {"ok": True, "request": req.name, "action": method,
            "remaining": count_my_pending(user)}


def _extract(e):
    msg = str(e) or e.__class__.__name__
    try:
        import json
        logs = getattr(frappe.local, "message_log", None) or []
        if logs:
            last = logs[-1]
            last = json.loads(last) if isinstance(last, str) else last
            msg = (last.get("message") if isinstance(last, dict) else None) or msg
    except Exception:
        pass
    return msg
