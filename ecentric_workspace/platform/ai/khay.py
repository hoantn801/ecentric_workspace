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
import re

import frappe

from ecentric_workspace.platform.ai import config, gateway, guard_log, khay_intent as brain, knowledge

ROLE = "EC Khay Pilot"
DISABLED_FLAG = "ec_khay_disabled"
FORMFILL_ROLE = "EC AI Formfill Pilot"
PAYMENT_CODE = "PAYMENT_REQUEST"
PAYMENT_ROUTE = "/approvals/payment-request"
#: Form xin nghi cua Approval Center khong dung (0 phieu/30 ngay) - xin nghi di Leave
#: Application goc qua ec_hr_leave_apply.
SKIP_CODES = ("LEAVE_REQUEST",)
#: Ten hien tren giao dien va trong loi dan. Doi ten = doi DUNG dong nay.
ASSISTANT_NAME = "eC Mate"   # Hoan chot ten 28/09
#: Hoi thoai thi phai nhanh: moi lan thu toi da 15s (Kie lan 28/09 treo 60s moi bao loi),
#: tong 45s. Model treo bi danh dau sap 5 phut nen lan sau di thang toi model con song.
#: Che do nhanh (gateway fast=True): 2 ban Gemini OpenAI + Grok goi song song, lay ben xong
#: truoc. Do 28-29/09: Gemini OpenAI tat suy nghi 5-12s (treo 2/8), Grok 9-25s (song 8/8).
BUDGET = 40
ATTEMPT_TIMEOUT = 10
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


def _can_formfill(user):
    roles = _roles(user)
    return ((FORMFILL_ROLE in roles or "System Manager" in roles)
            and not _flag("ec_ai_formfill_disabled"))


def _route(r):
    r = str(r or "").strip()
    return ("/" + r.lstrip("/")) if r else ""


def forms_for(user):
    """Form Approval Center NGUOI NAY duoc tao, dung danh sach trang Phe duyet cua ho.

    Lay tu catalog_api.list_catalog (chay DUOI QUYEN nguoi dang goi): the phai Active, co
    route, nguoi do thay duoc theo visibility (vai tro / phong ban). Chi giu ma co trong
    registry (co may AI dien ho chay duoc). Loi -> [] (eC Mate khong tao phieu, van chat).
    """
    try:
        from ecentric_workspace.approval_center.shared import catalog_api
        from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS
        cards = catalog_api.list_catalog().get("types") or []
    except Exception:
        frappe.log_error(title="ec_khay forms_for")
        return []
    out = []
    for c in cards:
        code = c.get("approval_code")
        if (c.get("card_status") == "Active" and c.get("route") and code in APPROVAL_DEFINITIONS
                and code not in SKIP_CODES):
            out.append({"code": code, "title": c.get("approval_title") or code,
                        "description": c.get("description") or "", "route": _route(c["route"])})
    return out


def _labels(doctype, fields):
    meta = frappe.get_meta(doctype)
    out = {}
    for f in fields:
        df = meta.get_field(f)
        if df is not None:
            out[f] = frappe._(df.label or f)
    return out


def _file_names(files):
    """Ten tep client gui (chi de dua vao prompt). Chuoi khong phai JSON / khong phai danh
    sach -> [] thay vi de parse_json nem loi 500."""
    if isinstance(files, str):
        try:
            files = frappe.parse_json(files) if files else []
        except Exception:
            files = []
    return [str(n) for n in files] if isinstance(files, list) else []


@frappe.whitelist(methods=["GET"])
def boot():
    user = frappe.session.user
    if not allowed(user):
        return {"enabled": False}
    emp = _employee(user) or {}
    name = (emp.get("employee_name") or frappe.db.get_value("User", user, "first_name") or "")
    return {"enabled": True, "name": ASSISTANT_NAME, "first_name": str(name).split(" ")[-1],
            "can_leave": bool(emp), "can_payment": _can_formfill(user),
            "payment_route": PAYMENT_ROUTE}


@frappe.whitelist(methods=["POST"])
def intent(message=None, history=None, page=None, files=None):
    user = frappe.session.user
    if not allowed(user):
        raise frappe.PermissionError
    message = str(message or "").strip()[:brain.MAX_MESSAGE]
    names = _file_names(files)
    if not message and not names:
        return {"action": brain.CLARIFY, "reply": "Bạn cần mình giúp gì?", "options": []}

    # QC 27/11: ten tep va `page` do client gui cung di vao loi dan -> xet nhu cau hoi.
    bad = [n for n in names if knowledge.guard(n)]
    if bad or (page and not _PAGE.match(str(page))):
        guard_log.note("param", CHANNEL, "trang=%s | tep=%s | cau=%s" % (str(page)[:120], bad, message))
    names = [n if n not in bad else "tep-dinh-kem" for n in names]
    page = page if _PAGE.match(str(page or "")) else ""
    kind, blocked = knowledge.guard_kind(message, creating_ok=True)
    if blocked:
        # Luong / thuong / PnL / doanh thu cua bat ky ai: khong goi AI, khong tra cuu (Hoan 10/11
        # + 27/11). Cau TAO phieu co chu "doanh thu" van di tiep (creating_ok) - chi ra nhap.
        guard_log.note(kind, CHANNEL, message)
        return {"action": brain.ANSWER, "reply": blocked, "options": [],
                "needs_data": False, "model": ""}
    turns = brain.parse_history(history)
    if guard_log.forged(turns, knowledge.fold):
        guard_log.note("history", CHANNEL, " | ".join(h["text"] for h in guard_log.forged(turns, knowledge.fold)))

    quick = brain.quick_reply(message, ASSISTANT_NAME, has_files=bool(names))
    if quick:
        quick["model"] = ""           # khong co AI nao tra loi -> khong hien "Tra loi boi"
        return quick

    leave_types = [r.name for r in frappe.get_all("Leave Type", fields=["name"], order_by="name")]
    forms = forms_for(user)
    today = frappe.utils.getdate(frappe.utils.nowdate())
    res = gateway.generate(
        brain.build_prompt(message or "(khong go gi, chi tha tep)", today, leave_types,
                           page=page or "", file_names=names, forms=forms),
        system=brain.system(ASSISTANT_NAME), schema=brain.SCHEMA,
        history=knowledge.safe_history(turns), purpose="khay", budget=BUDGET,
        attempt_timeout=ATTEMPT_TIMEOUT, fast=True, opts={"temperature": 0, "effort": "none"})
    if not res["ok"]:
        return {"action": "error", "reply": BUSY, "options": []}
    out = brain.normalize(res["data"], leave_types, today, has_files=bool(names), forms=forms)
    out = lookup_override(out, message, has_files=bool(names))
    out = pnl_create_only(out, message, forms)
    out = _enrich(out, user, forms)
    if out.get("reply") and not knowledge.advisory(message):
        safe = knowledge.safe_reply(out["reply"])
        if safe != out["reply"]:
            guard_log.note("output", CHANNEL, message)
        out["reply"] = safe
    out["options"] = [o for o in out.get("options") or [] if not knowledge.leaks(o)]
    out["model"] = res["model"]      # dong "Tra loi boi ..." duoi cau tra loi (Hoan 28/09)
    return out


CHANNEL = "khay"
_PAGE = re.compile(r"^/[A-Za-z0-9_\-/.]{0,119}$")


def pnl_create_only(out, message, forms=()):
    """PURE. Cau co chu doanh thu / chi phi duoc di tiep CHI de tao phieu (creating_ok). Router
    tra hanh dong khac -> khong dua cau tu do cua model ra: answer -> cau co dinh PnL; clarify
    -> cau hoi co dinh + lua chon la TEN FORM (khong phai chu cua model)."""
    if (not knowledge.pnl_question(message) or knowledge.advisory(message)
            or out.get("action") == brain.APPROVAL):
        return out
    if out.get("action") == brain.CLARIFY and forms:
        return {"action": brain.CLARIFY, "reply": "Bạn muốn tạo loại phiếu nào?",
                "options": [f.get("title") or f["code"] for f in forms][:brain.MAX_OPTIONS]}
    return {"action": brain.ANSWER, "reply": knowledge.PNL_REPLY, "options": [],
            "needs_data": False}


def lookup_override(out, message, has_files=False):
    """PURE. Cau hoi ve khao sat / tin noi bo / tai lieu / phep con / viec cua minh ma model lai
    doi tao phieu hoac hoi "AI Topup hay System Request?" (10/11, anh cua Hoan) -> di tra cuu.
    Khong dung khi co tep (tha tep la de tao phieu) hay khi cau la XIN nghi.

    27/11: model tra loi THANG (needs_data=false) mot cau ve ERP / cong viec -> van di tra cuu,
    vi buoc route khong co du lieu: cau tra loi do la doan (Hoan: "nhieu cau no chua tra loi")."""
    if (out.get("action") == brain.ANSWER and not out.get("needs_data")
            and knowledge.about_work(message)):
        return {"action": brain.ANSWER, "reply": "", "options": [], "needs_data": True}
    if has_files or out.get("action") not in (brain.APPROVAL, brain.CLARIFY):
        return out
    folded = knowledge.fold(message)
    if "xin" in folded and ("nghi" in folded or "phep" in folded):
        return out
    if not knowledge.is_lookup(message):
        return out
    return {"action": brain.ANSWER, "reply": "", "options": [], "needs_data": True}


def _enrich(out, user, forms=()):
    """Them nhung thu CHI server biet (quyen, nhan truong, duong dan). Model khong duoc dien."""
    if out["action"] == brain.LEAVE and not _employee(user):
        return {"action": "notice",
                "reply": "Tài khoản của bạn chưa gắn hồ sơ nhân viên nên chưa xin nghỉ được. "
                         "Bạn báo Nhân sự giúp mình nhé.", "options": []}
    if out["action"] == brain.APPROVAL:
        form = next((f for f in forms if f["code"] == out.get("approval_code")), None)
        if not _can_formfill(user) or not form:
            return {"action": "notice", "options": [],
                    "reply": "Bạn chưa được bật AI điền hộ phiếu phê duyệt. "
                             "Bạn vẫn tạo phiếu thủ công ở trang Phê duyệt được nhé."}
        from ecentric_workspace.approval_center.shared.registry import get_definition
        d = get_definition(form["code"])
        out.update({"approval_title": form["title"], "route": form["route"],
                    "labels": _labels(d.business_doctype, d.editable_fields)})
    return out
