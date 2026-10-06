# Copyright (c) 2026, eCentric and contributors
"""EC Employee Information Update Request orchestration over the shared approval engine. Fixed-participant single
level (HR Review); approvers come from EC Approval Process config, never hardcoded here.

29/09/2026 (Hoan chot): truong can sua lay tu HO SO NHAN VIEN (application/profile_fields.py,
tru tro cap / luong), duyet xong GHI THANG gia tri moi vao Employee - chay nen SAU commit, ghi
ket qua len phieu (applied_at / apply_result) va nhat ky duyet. "Other" va nhan cu khong con
trong danh sach thi KHONG ghi tu dong: C&B cap nhat tay."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine
from ecentric_workspace.approval_center.features.employee_info_update.application import (
    profile_fields as pf)

BUSINESS_DT = "EC Employee Information Update Request"
APPROVAL_TYPE = "EMPLOYEE_INFO_UPDATE"

MATERIAL_FIELDS = ["employee_email", "field_to_update", "field_to_update_other", "current_value", "new_value"]
REQUIRED_AT_SUBMIT = ["employee_email", "field_to_update", "new_value"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


def gen_title(doc):
    a = (doc.get("employee_email") or "?")
    b = (doc.get("field_to_update") or "?")
    return ("Employee Info Update - %s - %s" % (a, b))[:180]


def _validate_business(doc, user=None):
    """Form-specific submit-time validation (friendly Vietnamese)."""
    user = user or frappe.session.user
    email = (doc.get("employee_email") or "").strip()
    if not email:
        frappe.throw(_("Vui lòng nhập email nhân viên cần cập nhật."))
    emp = pf.resolve_employee(email)
    if not emp:
        frappe.throw(_("Không tìm thấy nhân viên với email này. Kiểm tra lại email hoặc liên hệ HR."))
    # Tu ghi vao ho so => chi sua ho so CUA CHINH MINH (tranh doi so tai khoan nguoi khac
    # sang tai khoan minh roi cho duyet). Sua ho ho so nguoi khac la viec cua C&B.
    if not pf.is_cnb(user) and frappe.db.get_value("Employee", emp, "user_id") != user:
        frappe.throw(_("Bạn chỉ gửi được yêu cầu cập nhật hồ sơ của chính mình. "
                       "Cập nhật cho người khác do C&B thực hiện."))
    doc.target_employee = emp
    label = doc.get("field_to_update")
    if label == pf.OTHER:
        if not (doc.get("field_to_update_other") or "").strip():
            frappe.throw(_("Vui lòng nhập tên trường khi chọn Other."))
        return
    sp = pf.spec(label)
    if not sp or label not in pf.options(user)["fields_to_update"]:
        frappe.throw(_("Vui lòng chọn trường thông tin cần cập nhật hợp lệ."))
    doc.new_value = pf.coerce(label, doc.get("new_value"))


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
    emp = _requester_context(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    _validate_business(doc, user)
    doc.request_title = gen_title(doc)
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yeu cau chua duoc gui."))
    _validate_business(doc, doc.requested_by)
    frappe.db.set_value(BUSINESS_DT, doc.name, {"target_employee": doc.target_employee,
                                                "new_value": doc.new_value})
    new_sig = _signature(doc)
    changed = new_sig != (doc.material_signature or "")
    frappe.db.set_value(BUSINESS_DT, doc.name, "request_title", gen_title(doc))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": changed}


# --------------------------------------------------------------------------- #
# 29/09/2026 - Ho so nhan vien: danh sach truong, gia tri hien tai, ghi sau duyet
# --------------------------------------------------------------------------- #
def form_options():
    return pf.options()


def current_value_of(employee_email, field_to_update):
    return pf.current_value(frappe.session.user, employee_email, field_to_update)


def eiu_block(business, request):
    sp = pf.spec(business.get("field_to_update"))
    return {"auto_apply": bool(sp), "applied_at": business.get("applied_at"),
            "apply_result": business.get("apply_result")}


def on_final_approval(name):
    """Duyet xong -> ghi vao ho so O NEN, sau khi giao dich duyet commit: loi ghi ho so
    (vd truong da bi doi kieu) khong bao gio lam hong luot duyet."""
    frappe.enqueue("ecentric_workspace.approval_center.features.employee_info_update."
                   "application.service.apply_to_employee",
                   queue="short", enqueue_after_commit=True, name=name)


def apply_to_employee(name):
    """Ghi new_value vao Employee. Idempotent (da ghi thi thoi). Khong nem loi ra ngoai."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.applied_at:
        return {"skipped": "applied"}
    label = doc.field_to_update
    sp = pf.spec(label)
    if not sp:
        _mark(doc, None, _("Không ghi tự động (\"{0}\"): C&B cập nhật tay vào hồ sơ.").format(label))
        return {"skipped": "manual"}
    fieldname = sp[0]
    try:
        emp_name = doc.get("target_employee") or pf.resolve_employee(doc.employee_email)
        if not emp_name:
            frappe.throw(_("Không tìm thấy hồ sơ nhân viên."))
        emp = frappe.get_doc(pf.EMPLOYEE, emp_name)
        new = pf.coerce(label, doc.new_value)
        before = emp.get(fieldname)
        note = ""
        if (doc.current_value or "").strip() and str(before or "").strip() != (doc.current_value or "").strip():
            note = _(" (hồ sơ lúc ghi khác giá trị hiện tại trên phiếu)")
        emp.set(fieldname, new)
        emp.flags.ec_eiu_request = name
        emp.save(ignore_permissions=True)
        _mark(doc, frappe.utils.now_datetime(),
              _("Đã ghi vào hồ sơ {0}: {1}{2}").format(emp_name, label, note))
        frappe.db.commit()
        return {"applied": True}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Employee Info Update: khong ghi duoc %s" % name,
                         message=frappe.get_traceback())
        _mark(doc, None, _("LỖI khi ghi vào hồ sơ - C&B kiểm tra và cập nhật tay (xem Error Log)."))
        try:
            approvers = frappe.get_all("EC Approval Request Approver",
                                       filters={"approval_request": doc.approval_request,
                                                "status": "Approved"}, pluck="approver")
            engine.notify(sorted(set(approvers + [doc.requested_by])),
                          _("Chưa ghi được vào hồ sơ nhân viên: {0} - cần cập nhật tay.").format(name),
                          BUSINESS_DT, name)
        except Exception:
            pass
        frappe.db.commit()
        return {"applied": False}


def _mark(doc, applied_at, result):
    frappe.db.set_value(BUSINESS_DT, doc.name, {"applied_at": applied_at, "apply_result": result[:500]},
                        update_modified=False)
    if doc.approval_request:
        engine.log_action(doc.approval_request, "Commented", "Administrator", comment=result)
