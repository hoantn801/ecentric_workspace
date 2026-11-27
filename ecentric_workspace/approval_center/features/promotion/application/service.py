# Copyright (c) 2026, eCentric and contributors
"""Promotion orchestration over the shared engine. Direct Manager -> CnB -> HOF -> CEO
(User participants from process config; no fulfillment).

29/09/2026 (Hoan chot): chon THANG nhan su (chi nguoi minh xem duoc luong - employee_snapshot.py);
thong tin hien tai (vi tri, luong) lay tu ho so / SSA o SERVER, khong tin client; duyet xong tu
ghi chuc danh + tao SSA luong moi (apply_to_employee, nen sau commit). Governance: because a promotion
carries salary data, the Direct Manager approver is NEVER requester-chosen - it resolves
from Employee.reports_to. If it cannot be resolved, submit is blocked with a friendly
Vietnamese message (no silent bypass). No hardcoded runtime approvers.

27/11/2026 (Hoan chot "huong 2") - LEAD DE XUAT CHO NGUOI MINH QUAN LY:
  * nguoi lap duoc chon nhan su trong pham vi employee_snapshot.can_propose (xem duoc luong HOP cap
    duoi truc tiep + gian tiep) - kiem o server khi chon (snapshot), luu nhap (prepare_draft), gui;
  * nguoi lap KHONG xem duoc luong nhan su do: server bo moi gia tri current_salary / proposed_salary /
    incentives client gui (luu nhap: giu gia tri dang co trong DB; gui lan dau: xoa) va dat
    salary_pending=1. Nguoi duyet dau tien co quyen xem luong dien qua fill_salary (POST, phai la nguoi
    duyet Pending cua cap hien tai + can_view_salary) roi moi duyet duoc - approval_input_message chan
    o engine.approve. Nguoi duyet khong xem duoc luong (cap trung gian) duyet binh thuong; rieng cap
    CnB va cap cuoi cung thi KHONG cho qua khi chua co luong (luon co mot cap bat buoc dien);
  * nguoi lap xem duoc luong: nhu cu (nhap luong ngay, salary_pending=0)."""
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
#: Ten cap CnB trong PROMOTION_REQUEST-V1 - PHAI trung infrastructure/setup.py (validate_promotion_v1 kiem
#: "L2 is CnB Review"). Cap nay bat buoc co luong truoc khi duyet (27/11).
CNB_LEVEL_NAME = "CnB Review"
_REQ_LEVEL = "EC Approval Request Level"


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
    _fill_from_employee(doc, user)
    # 27/11: nguoi lap khong xem duoc luong nhan su nay (Lead de xuat cho cap duoi) -> khong nhan luong
    # tu client, nguoi duyet co quyen se dien. Phieu cu (khong chon nhan su) giu luat cu.
    pending = bool(doc.get("promoted_employee")) and not snap.can_view_salary(doc.promoted_employee, user=user)
    if pending:
        for f in snap.SALARY_FIELDS:
            doc.set(f, None)
    doc.salary_pending = 1 if pending else 0
    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if not pending:
        if not doc.current_salary:                # gross tu nhap (01/10) - 0 / trong deu la thieu
            missing.append("current_salary")
        if doc.proposed_salary is None:
            missing.append("proposed_salary")
    if missing:
        frappe.throw(_("Vui long nhap day du cac truong bat buoc truoc khi gui."))
    if not frappe.db.exists("Department", doc.department):
        frappe.throw(_("Phong ban khong hop le. Vui long chon phong ban tu danh sach."))
    for f in ([] if pending else _SALARY_FIELDS):
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


def _fill_from_employee(doc, user=None):
    """Nhan su chon tu danh sach -> ghi de ho ten / phong ban / vi tri bang du lieu server (pham vi
    de xuat - can_propose cua NGUOI LAP - kiem lai o day). Luong hien tai la GROSS do nguoi de xuat
    (hoac nguoi duyet co quyen, 27/11) nhap - KHONG ghi de (01/10). Phieu cu (khong chon nhan su) giu
    nhu truoc."""
    if not doc.get("promoted_employee"):
        if frappe.db.get_value(BUSINESS_DT, doc.name, "approval_request"):
            return
        frappe.throw(_("Vui lòng chọn nhân sự được đề xuất."))
    s = snap.snapshot(doc.promoted_employee, user=user or doc.get("requested_by") or frappe.session.user)
    doc.full_name = s["full_name"]
    doc.department = s["department"]
    doc.current_position = s["current_position"] or doc.current_position


def prepare_draft(doc):
    """ApprovalDefinition.draft_preparer - chay o MOI lan luu nhap / luu de gui lai (27/11).
    1. promoted_employee phai thuoc pham vi de xuat cua nguoi lap (khong tin danh sach client).
    2. Nguoi lap khong xem duoc luong nhan su do: bo gia tri luong client gui - giu dung gia tri dang
       co trong DB (luong nguoi duyet da dien khi phieu bi tra lai); phieu moi -> trong."""
    user = doc.get("requested_by") or frappe.session.user
    emp = doc.get("promoted_employee")
    if not emp:
        return
    if not snap.can_propose(emp, user=user):
        frappe.throw(_("Bạn không được đề xuất cho nhân sự này (chỉ người bạn quản lý hoặc được xem lương)."),
                     frappe.PermissionError)
    if snap.can_view_salary(emp, user=user):
        return
    saved = (frappe.db.get_value(BUSINESS_DT, doc.name, list(snap.SALARY_FIELDS), as_dict=True)
             if doc.get("name") and frappe.db.exists(BUSINESS_DT, doc.name) else None) or {}
    for f in snap.SALARY_FIELDS:
        doc.set(f, saved.get(f))


def _level_rows(request_name):
    return frappe.get_all(_REQ_LEVEL, filters={"approval_request": request_name},
                          fields=["level_no", "level_name", "level_status"], order_by="level_no asc",
                          limit_page_length=0)


def _salary_gate_level(request):
    """Cap hien tai la cap BAT BUOC co luong: cap CnB, hoac cap cuoi cung con lai (khong con cap nao
    phia sau chua bi bo qua). Nho vay phieu khong bao gio duyet xong ma thieu luong."""
    cur = request.get("current_level") if request else None
    if not cur:
        return False
    rows = _level_rows(request.get("name"))
    here = next((r for r in rows if r.get("level_no") == cur), None)
    if here and here.get("level_name") == CNB_LEVEL_NAME:
        return True
    return not any(r.get("level_no") > cur and r.get("level_status") != "Skipped" for r in rows)


def approval_input_message(business, request, actor):
    """ApprovalDefinition.approval_input_check (27/11). "" = duyet duoc; con lai la cau chan.
    - Phieu khong cho luong (salary_pending=0): "".
    - Nguoi duyet xem duoc luong nhan su: phai dien luong truoc.
    - Nguoi duyet khong xem duoc luong: cap trung gian -> duyet binh thuong; cap CnB / cap cuoi -> chan
      (bao lien he C&B / quan tri), vi qua cap nay la khong con ai dien."""
    if not business.get("salary_pending") or not business.get("promoted_employee"):
        return ""
    if snap.can_view_salary(business.get("promoted_employee"), user=actor):
        return _("Vui lòng điền Lương hiện tại – gross và Lương đề xuất – gross trước khi duyệt "
                 "(người lập phiếu không có quyền xem lương nhân sự này). Mở phiếu ở trang Thăng chức / "
                 "điều chỉnh lương để điền.")
    if _salary_gate_level(request):
        return _("Phiếu chưa có lương hiện tại / đề xuất và bước này bắt buộc phải có lương trước khi duyệt, "
                 "nhưng bạn không có quyền xem lương nhân sự này. Vui lòng liên hệ C&B hoặc quản trị hệ thống.")
    return ""


def _money(v):
    """So tien tu form (so, hoac chuoi "12.000.000" kieu Viet Nam) -> float | None."""
    if v is None or v == "":
        return None
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v).strip().replace(" ", "").replace(".", "").replace(",", "")
    try:
        return float(t)
    except ValueError:
        return None


def _salary_fill_state(business, request, user):
    """-> (can_fill, ly do khong dien duoc). can_fill = phieu dang Pending, user la nguoi duyet Pending
    cua cap hien tai VA xem duoc luong nhan su do."""
    from ecentric_workspace.approval_center.shared.workflow import permissions as perm
    if not request or not business.get("promoted_employee"):
        return False, _("Phiếu chưa gửi hoặc chưa chọn nhân sự.")
    if request.get("approval_status") != "Pending" or not perm.is_actionable(
            request.get("name"), request.get("current_level"), user, request.get("approval_status")):
        return False, _("Chỉ người duyệt đang chờ ở bước hiện tại mới điền được lương.")
    if not snap.can_view_salary(business.get("promoted_employee"), user=user):
        return False, _("Bạn không có quyền xem lương nhân sự này nên không điền được lương.")
    return True, ""


def fill_salary(name, current_salary=None, proposed_salary=None, incentives=None):
    """Nguoi duyet co quyen xem luong dien luong cho phieu do Lead lap (27/11). Nguoi goi = session
    user (KHONG nhan actor tu ngoai - F15). Ghi vet vao nhat ky duyet KHONG kem so tien."""
    user = frappe.session.user
    doc = frappe.get_doc(BUSINESS_DT, name)
    request = (frappe.db.get_value("EC Approval Request", doc.approval_request,
                                   ["name", "approval_status", "current_level"], as_dict=True)
               if doc.get("approval_request") else None)
    ok, why = _salary_fill_state(doc, request, user)
    if not ok:
        frappe.throw(why, frappe.PermissionError)
    cur, new = _money(current_salary), _money(proposed_salary)
    if cur is None or cur <= 0:
        frappe.throw(_("Vui lòng nhập Lương hiện tại – gross (số dương)."))
    if new is None or new < 0:
        frappe.throw(_("Vui lòng nhập Lương đề xuất – gross (số không âm)."))
    vals = {"current_salary": cur, "proposed_salary": new, "salary_pending": 0,
            "salary_filled_by": user, "salary_filled_at": now_datetime()}
    if incentives is not None:
        vals["incentives"] = (str(incentives).strip() or None)
    frappe.db.get_value(BUSINESS_DT, name, "name", for_update=True)
    doc.update(vals)
    # Chu ky noi dung cap nhat theo luong moi: Lead gui lai ma khong doi gi thi KHONG bi tinh la
    # "doi noi dung" (khong duyet lai tu dau chi vi nguoi duyet da dien luong).
    vals["material_signature"] = _signature(doc)
    frappe.db.set_value(BUSINESS_DT, name, vals)
    engine.log_action(request.name, "Commented", user, request.current_level,
                      comment=_("Đã điền lương hiện tại / đề xuất (gross). Số tiền chỉ người có quyền "
                                "xem lương nhân sự này thấy."))
    return {"saved": True}


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
    user = frappe.session.user
    can_fill = False
    try:
        can_fill = _salary_fill_state(business, request, user)[0]
    except Exception:
        can_fill = False
    pending = bool(business.get("salary_pending"))
    # Chi CO, khong kem so: so luong (neu nguoi xem co quyen) da nam trong business sau redact.
    return {"applied_at": business.get("applied_at"), "apply_result": business.get("apply_result"),
            "auto_apply": bool(business.get("promoted_employee")),
            "salary_input": {"pending": pending, "can_fill": bool(can_fill),
                             "required": bool(pending and can_fill)}}


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
    # 27/11: Lead (khong xem duoc luong) sua noi dung -> duyet lai tu dau VA nguoi duyet co quyen phai
    # xac nhan lai luong (gia tri cu van giu de dien san).
    if material_changed and doc.get("promoted_employee") and not snap.can_view_salary(
            doc.promoted_employee, user=doc.requested_by or actor or frappe.session.user):
        frappe.db.set_value(BUSINESS_DT, doc.name, "salary_pending", 1)
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}
