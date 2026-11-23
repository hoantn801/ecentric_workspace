# Copyright (c) 2026, eCentric and contributors
"""Phieu CEO ky quyet dinh ky luat - ban chup cua EC Discipline Case luc HR trinh.

Cong khai bao cho module hr/ky_luat (goi qua frappe.get_attr, xem hr/ky_luat/infrastructure/
gateways.py): tao_tu_ho_so(case, actor), gui_lai_tu_ho_so(case, actor). Nguoc lai, khi CEO duyet
xong engine goi on_final_approval -> hr.ky_luat.controllers.api.on_decision_approved(case).
CEO tu choi / yeu cau bo sung: engine doi trang thai bang set_value (khong hook) - hr/ky_luat
tu dong bo (reconcile) ngay sau thao tac tren trang quyet dinh + job hang ngay.
Nguoi duyet KHONG hardcode: process DISCIPLINE_DECISION-V1 (setup.py, role tu Settings)."""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Discipline Decision Request"
APPROVAL_TYPE = "DISCIPLINE_DECISION"
CASE_DT = "EC Discipline Case"
HR_CALLBACK = "ecentric_workspace.hr.ky_luat.controllers.api.on_decision_approved"
GROUND_LABELS = "ecentric_workspace.hr.ky_luat.constants.DISMISS_GROUNDS"
_FLAG = "ec_discipline_from_case"
SNAPSHOT = ("employee", "employee_name", "department", "card", "penalty", "extend_months",
            "rule_title", "violation_date", "meeting_date", "effective_date", "termination_date",
            "limitation_effective_end", "decision_draft")


def gen_title(doc):
    """"Quyet dinh ky luat - <hinh thuc> - <ten NV> - <tieu de ho so>" (Hoan chot 23/11), cat 255.
    `case_title` = tieu de ho so luc trinh (ho so cu: tieu de du phong do hr/ky_luat sinh)."""
    parts = [doc.get("penalty"), doc.get("employee_name") or doc.get("employee"), doc.get("case_title")]
    return ("Quyết định kỷ luật - " + " - ".join(str(p).strip() for p in parts if p and str(p).strip()))[:255]


def prepare_draft(document):
    if document.is_new() and not frappe.flags.get(_FLAG):
        frappe.throw(_("Phiếu quyết định kỷ luật được tạo tự động khi HR trình CEO từ hồ sơ kỷ luật."))


def _fill(doc, case):
    for f in SNAPSHOT:
        doc.set(f, case.get(f))
    doc.discipline_case = case["name"]
    doc.case_title = (case.get("case_title") or case.get("title") or "")[:140] or None
    g = str(case.get("dismissal_ground") or "")
    doc.dismissal_ground = ("(%s) %s" % (g, dict(frappe.get_attr(GROUND_LABELS)).get(g, ""))) if g else None
    doc.summary = "%s\nĐiều khoản: %s" % (case.get("description") or "", case.get("rule_title") or "")
    doc.meeting_summary = "%s\n%s" % (case.get("employee_present") or "", case.get("employee_statement") or "")
    doc.request_title = gen_title(doc)


def tao_tu_ho_so(case, actor):
    """Tao + gui phieu cho mot ho so (dict) da hop xong. Idempotent theo ho so: con phieu dang
    cho (Pending / Information Required) thi tra lai phieu do."""
    open_ = frappe.get_all(BUSINESS_DT, filters={"discipline_case": case["name"],
                                                 "approval_request": ["is", "set"]},
                           fields=["name", "approval_request"], order_by="creation desc", limit_page_length=1)
    if open_:
        st = frappe.db.get_value("EC Approval Request", open_[0].approval_request, "approval_status")
        if st in ("Pending", "Information Required"):
            return open_[0].name
    doc = frappe.new_doc(BUSINESS_DT)
    _fill(doc, case)
    doc.approval_type = APPROVAL_TYPE
    doc.requested_by = actor
    doc.company = frappe.db.get_value("Employee", case.get("employee"), "company")
    frappe.flags[_FLAG] = True
    try:
        doc.insert(ignore_permissions=True)
    finally:
        frappe.flags[_FLAG] = False
    doc.db_set("submitted_at", now_datetime())
    req = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, actor)
    doc.db_set("approval_request", req)
    return doc.name


def gui_lai_tu_ho_so(case, actor):
    """CEO yeu cau bo sung -> HR sua ho so -> chep lai ban chup + gui lai (giu lich su)."""
    name = case.get("decision_request")
    doc = frappe.get_doc(BUSINESS_DT, name)
    _fill(doc, case)
    doc.save(ignore_permissions=True)
    frappe.flags.ec_discipline_resubmit = True
    try:
        engine.resubmit(doc.approval_request, actor=actor, restart=False)
    finally:
        frappe.flags.ec_discipline_resubmit = False
    return name


def doi_tieu_de_tu_ho_so(case):
    """HR sua tieu de ho so khi phieu dang cho CEO -> cap nhat ban chup tieu de + request_title
    (engine lay nhan phieu tu title_field). db_set: khong dong vao trang thai duyet / ban chup khac.
    Phieu da ket thuc (khong con Pending / Information Required) thi giu nguyen - lich su."""
    name = case.get("decision_request")
    if not name or not frappe.db.exists(BUSINESS_DT, name):
        return None
    doc = frappe.get_doc(BUSINESS_DT, name)
    st = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_status") \
        if doc.approval_request else None
    if st not in ("Pending", "Information Required"):
        return None
    doc.case_title = (case.get("case_title") or case.get("title") or "")[:140] or None
    doc.db_set({"case_title": doc.case_title, "request_title": gen_title(doc)})
    return name


def submit(name):
    frappe.throw(_("Phiếu quyết định kỷ luật chỉ được gửi từ hồ sơ kỷ luật (/ky-luat)."))


def resubmit(name, actor=None):
    """Duong chung (api_adapter.resubmit) bi chan: gui lai PHAI qua hr/ky_luat de chep lai ban
    chup tu ho so (gui_lai_tu_ho_so)."""
    if not frappe.flags.get("ec_discipline_resubmit"):
        frappe.throw(_("Gửi lại từ trang hồ sơ kỷ luật (/ky-luat) để cập nhật nội dung trình CEO."))
    return {"restarted": False}


def decision_block(business, request):
    """Khoi phu cho man hinh chi tiet: duong dan ho so + nhac phap ly."""
    from ecentric_workspace.hr.ky_luat import constants as KC
    return {"case_route": "%s?tab=ho-so&ma=%s" % (KC.ROUTE, business.get("discipline_case")),
            "legal_note": KC.LEGAL_NOTE}


def on_final_approval(name):
    case = frappe.db.get_value(BUSINESS_DT, name, "discipline_case")
    if case:
        frappe.get_attr(HR_CALLBACK)(case)
