# Copyright (c) 2026, eCentric and contributors
"""Promotion orchestration over the shared engine. Direct Manager -> CnB -> HOF -> CEO
(User participants from process config; no fulfillment).

29/09/2026 (Hoan chot): chon THANG nhan su (chi nguoi minh xem duoc luong - employee_snapshot.py);
thong tin hien tai (vi tri, luong) lay tu ho so / SSA o SERVER, khong tin client; duyet xong tu
ghi chuc danh + tao SSA luong moi (apply_to_employee, nen sau commit). Governance: because a promotion
carries salary data, the Direct Manager approver is NEVER requester-chosen - it resolves
from Employee.reports_to. If it cannot be resolved, submit is blocked with a friendly
Vietnamese message (no silent bypass). No hardcoded runtime approvers."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine
from ecentric_workspace.approval_center.features.promotion.application import employee_snapshot as snap

BUSINESS_DT = "EC Promotion Request"
APPROVAL_TYPE = "PROMOTION_REQUEST"

MATERIAL_FIELDS = ["promoted_employee", "full_name", "department", "current_position", "proposed_position",
                   "justification", "current_salary", "proposed_salary", "incentives",
                   "effective_date_of_promotion"]
REQUIRED_AT_SUBMIT = ["request_title", "full_name", "department", "current_position",
                      "proposed_position", "justification", "effective_date_of_promotion"]
_SALARY_FIELDS = ["current_salary", "proposed_salary"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _ctx(user):
    return frappe.db.get_value("Employee", {"user_id": user}, ["name", "department", "company"], as_dict=True)


@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yeu cau nay da duoc gui."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Ban chi co the gui yeu cau cua chinh minh."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _ctx(user)
    if emp:
        doc.employee = emp.name
        doc.company = doc.company or emp.company
    _fill_from_employee(doc)
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if not doc.current_salary:                    # gross tu nhap (01/10) - 0 / trong deu la thieu
        missing.append("current_salary")
    if doc.proposed_salary is None:
        missing.append("proposed_salary")
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if not frappe.db.exists("Department", doc.department):
        frappe.throw(_("Phong ban khong hop le. Vui long chon phong ban tu danh sach."))
    for f in _SALARY_FIELDS:
        try:
            if float(doc.get(f)) < 0:
                frappe.throw(_("Muc luong khong the la so am."))
        except (TypeError, ValueError):
            frappe.throw(_("Muc luong phai la so."))
    # Buoc 1 (review Phan quyen P1, 29/09): nguoi dau tien tren chuoi reports_to cua NHAN SU
    # DUOC DE XUAT xem duoc luong nguoi do. Khong co / trung nguoi gui -> bo buoc 1 (co ghi audit).
    doc.salary_reviewer = snap.salary_reviewer(doc.promoted_employee, user) if doc.get("promoted_employee") else None
    skip = None if doc.salary_reviewer else (1,)
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user, skip_level_nos=skip,
                             skip_reason=_("Không có quản lý nào trên chuỗi báo cáo (khác người gửi) "
                                           "xem được lương nhân sự này") if skip else None)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


def _fill_from_employee(doc):
    """Nhan su chon tu danh sach -> ghi de ho ten / phong ban / vi tri bang du lieu server (quyen
    xem luong kiem lai o day). Luong hien tai la GROSS do nguoi de xuat tu nhap - KHONG ghi de
    (01/10). Phieu cu (khong chon nhan su) giu nhu truoc."""
    if not doc.get("promoted_employee"):
        if frappe.db.get_value(BUSINESS_DT, doc.name, "approval_request"):
            return
        frappe.throw(_("Vui lòng chọn nhân sự được đề xuất."))
    s = snap.snapshot(doc.promoted_employee)
    doc.full_name = s["full_name"]
    doc.department = s["department"]
    doc.current_position = s["current_position"] or doc.current_position


def form_options():
    from ecentric_workspace.approval_center.shared.definition_support import DepartmentOptions
    out = DepartmentOptions()()
    out["designations"] = snap.designations()
    return out


def on_final_approval(name):
    frappe.enqueue("ecentric_workspace.approval_center.features.promotion.application.service."
                   "apply_to_employee", queue="short", enqueue_after_commit=True, name=name)


def apply_to_employee(name):
    """Idempotent. Moi thay doi trong MOT giao dich: loi giua chung thi rollback het."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.get("applied_at") or not doc.get("promoted_employee"):
        return {"skipped": True}
    try:
        ok, notes = snap.apply_promotion(doc)
        msg = "; ".join(notes)
        frappe.db.set_value(BUSINESS_DT, name, {"applied_at": frappe.utils.now_datetime(),
                                                "apply_result": msg[:500]}, update_modified=False)
        engine.log_action(doc.approval_request, "Commented", "Administrator", comment=msg)
        frappe.db.commit()
        if not ok:
            _notify_manual(doc, msg)
        return {"applied": True, "ok": ok}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Promotion: khong cap nhat duoc ho so %s" % name, message=frappe.get_traceback())
        frappe.db.set_value(BUSINESS_DT, name, "apply_result",
                            _("LỖI khi cập nhật hồ sơ / lương - C&B cập nhật tay (xem Error Log)."),
                            update_modified=False)
        frappe.db.commit()
        _notify_manual(doc, _("lỗi hệ thống"))
        return {"applied": False}


def _notify_manual(doc, why):
    try:
        who = frappe.get_all("EC Approval Request Approver",
                             filters={"approval_request": doc.approval_request, "status": "Approved"},
                             pluck="approver")
        engine.notify(sorted(set(who + [doc.requested_by])),
                      _("Promotion {0}: cần C&B xử lý ({1}).").format(doc.name, why),
                      BUSINESS_DT, doc.name)
        frappe.db.commit()
    except Exception:
        pass


def redact_business(business, request=None):
    return snap.redact(business, request)


def promotion_block(business, request):
    return {"applied_at": business.get("applied_at"), "apply_result": business.get("apply_result"),
            "auto_apply": bool(business.get("promoted_employee"))}


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yeu cau chua duoc gui."))
    if doc.get("promoted_employee"):
        _fill_from_employee(doc)
        frappe.db.set_value(BUSINESS_DT, doc.name, {"full_name": doc.full_name, "department": doc.department,
                                                    "current_position": doc.current_position})
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}
