# Copyright (c) 2026, eCentric and contributors
"""Khay - tro ly o goc moi trang ERP (28/09/2026, Hoan chot kieu A mac dinh, no thanh B).

Hai endpoint, va KHONG endpoint nao ghi gi:
  * `boot`   (GET)  - widget hoi truoc khi ve: co bat khong, nguoi nay lam duoc viec gi.
  * `intent` (POST) - doc mot cau -> MOT hanh dong (xem khay_intent). Tra ve de xuat.

Viec that do nhung endpoint CO SAN lam, widget goi thang toi chung - nen moi luat nghiep vu
van chi nam o mot cho:
  * nghi phep      -> `ec_hr_leave_apply` (Server Script, fixtures)
  * de nghi TT     -> `approval_center.api.ai_formfill.suggest` / `create_draft`
  * hoi dap        -> `gemini_chat` (platform/ai/chat.py, quyen A14)

Mo dan bang Role `EC Khay Pilot` (khong phai `if user == ...`). Tat khan: site_config
`ec_khay_disabled: 1`, hoac `ec_ai_disabled: 1` tat moi AI.
"""
import frappe

from ecentric_workspace.platform.ai import config, gateway, khay_intent as brain

ROLE = "EC Khay Pilot"
DISABLED_FLAG = "ec_khay_disabled"
FORMFILL_ROLE = "EC AI Formfill Pilot"
PAYMENT_CODE = "PAYMENT_REQUEST"
#: Giai doan 1 chi mot form, trung voi ROUTES cua ec_aifill.bundle.js - AI dien ho moi
#: nghiem thu xong tren form nay. Them form = them vao day SAU khi form do chay AI dien ho.
PAYMENT_ROUTE = "/approvals/payment-request"
#: Ten hien tren giao dien va trong loi dan. Doi ten = doi DUNG dong nay.
ASSISTANT_NAME = "eCentric AI"
#: Hoi thoai thi phai nhanh: moi lan thu toi da 15s (Kie lan 28/09 treo 60s moi bao loi),
#: tong 45s. Model treo bi danh dau sap 5 phut nen lan sau di thang toi model con song.
BUDGET = 45
ATTEMPT_TIMEOUT = 15
BUSY = "AI đang quá tải, bạn thử lại sau ít phút nhé."


def _flag(name):
    try:
        return bool(int(frappe.conf.get(name) or 0))
    except Exception:
        return False


def _roles(user):
    return set(frappe.get_roles(user))


def allowed(user=None):
    user = user or frappe.session.user
    if not user or user == "Guest" or _flag(DISABLED_FLAG) or config.disabled():
        return False
    roles = _roles(user)
    return ROLE in roles or "System Manager" in roles


def _employee(user):
    return frappe.db.get_value("Employee", {"user_id": user, "status": "Active"},
                               ["name", "employee_name"], as_dict=True)


def _can_payment(user):
    roles = _roles(user)
    return ((FORMFILL_ROLE in roles or "System Manager" in roles)
            and not _flag("ec_ai_formfill_disabled"))


def _labels(doctype, fields):
    meta = frappe.get_meta(doctype)
    out = {}
    for f in fields:
        df = meta.get_field(f)
        if df is not None:
            out[f] = frappe._(df.label or f)
    return out


@frappe.whitelist(methods=["GET"])
def boot():
    user = frappe.session.user
    if not allowed(user):
        return {"enabled": False}
    emp = _employee(user) or {}
    name = (emp.get("employee_name") or frappe.db.get_value("User", user, "first_name") or "")
    return {"enabled": True, "name": ASSISTANT_NAME, "first_name": str(name).split(" ")[-1],
            "can_leave": bool(emp), "can_payment": _can_payment(user),
            "payment_route": PAYMENT_ROUTE}


@frappe.whitelist(methods=["POST"])
def intent(message=None, history=None, page=None, files=None):
    user = frappe.session.user
    if not allowed(user):
        raise frappe.PermissionError
    message = str(message or "").strip()[:brain.MAX_MESSAGE]
    names = frappe.parse_json(files) if isinstance(files, str) and files else (files or [])
    names = [str(n) for n in names] if isinstance(names, list) else []
    if not message and not names:
        return {"action": brain.CLARIFY, "reply": "Bạn cần mình giúp gì?", "options": []}

    leave_types = [r.name for r in frappe.get_all("Leave Type", fields=["name"], order_by="name")]
    today = frappe.utils.getdate(frappe.utils.nowdate())
    res = gateway.generate(
        brain.build_prompt(message or "(khong go gi, chi tha tep)", today, leave_types,
                           page=page or "", file_names=names),
        system=brain.system(ASSISTANT_NAME), schema=brain.SCHEMA,
        history=brain.parse_history(history), purpose="khay", budget=BUDGET,
        attempt_timeout=ATTEMPT_TIMEOUT, opts={"temperature": 0})
    if not res["ok"]:
        return {"action": "error", "reply": BUSY, "options": []}
    out = brain.normalize(res["data"], leave_types, today, has_files=bool(names))
    return _enrich(out, user)


def _enrich(out, user):
    """Them nhung thu CHI server biet (quyen, nhan truong, duong dan). Model khong duoc dien."""
    if out["action"] == brain.LEAVE and not _employee(user):
        return {"action": "notice",
                "reply": "Tài khoản của bạn chưa gắn hồ sơ nhân viên nên chưa xin nghỉ được. "
                         "Bạn báo Nhân sự giúp mình nhé.", "options": []}
    if out["action"] == brain.PAYMENT:
        if not _can_payment(user):
            return {"action": "notice", "options": [],
                    "reply": "Bạn chưa được bật AI điền hộ cho đề nghị thanh toán. "
                             "Bạn vẫn tạo phiếu thủ công ở trang Phê duyệt được nhé."}
        from ecentric_workspace.approval_center.shared.registry import get_definition
        d = get_definition(PAYMENT_CODE)
        out.update({"approval_code": PAYMENT_CODE, "route": PAYMENT_ROUTE,
                    "labels": _labels(d.business_doctype, d.editable_fields)})
    return out
