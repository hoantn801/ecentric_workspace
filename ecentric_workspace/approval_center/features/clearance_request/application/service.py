# Copyright (c) 2026, eCentric and contributors
"""Clearance Request - TU TAO khi Don nghi viec (Resignation) duyet xong (29/09/2026, Hoan).

Theo file "Chuyen Approvals Teams - ERP" (sheet Clearance Request): phieu tao DUOI TEN nhan vien
nghi viec, gui Line Manager / Operation / HR / HOF - moi ben kiem muc ban giao cua minh, SONG
SONG (cap "Each Group" cua engine, cung khuon New Staff Preparation). Cac nhom la cau hinh
process CLEARANCE_REQUEST-V1, khong viet cung o day.

Khoa tai khoan KHONG nam o day: job hang ngay cua module HR (hr/offboarding) doc
Employee.relieving_date - ngay do do Don nghi viec ghi luc duyet xong."""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Clearance Request"
APPROVAL_TYPE = "CLEARANCE_REQUEST"
RESIGNATION_DT = "EC Resignation Request"
GREETING = ("A handover clearance process has been initiated. Please help to carefully check out "
            "all related items to your departments respectively, before or on the last working day. "
            "Vui lòng hoàn tất danh sách clearance trước hoặc trong ngày làm việc cuối cùng.")
#: Muc ban giao theo tung nhom (hien tren phieu). Ten nhom khop group_label cua process.
CHECKLIST = {
    "Line Manager": ["Role handover: bàn giao công việc chuyên môn cho quản lý trực tiếp"],
    "HOF": ["Payable clearance: quyết toán các khoản phải trả cho công ty, tạm ứng, hoàn ứng, đề nghị thanh toán",
            "Last month's salary: quyết toán tháng lương cuối cùng"],
    "Operation": ["Asset return: trả tài sản đã cấp (laptop, màn hình...) qua Asset Request",
                  "Microsoft 365, Lark, license / tool khác: thu hồi tài khoản đã cấp"],
    "HR": ["Exit interview: phỏng vấn thôi việc",
           "Termination decision: quyết định thôi việc",
           "Thẻ văn phòng, thẻ thang máy, thẻ gửi xe, chìa khoá locker và tài sản HR cấp"],
}


def gen_title(doc):
    parts = [doc.get("employee_name") or doc.get("employee_email"), doc.get("last_working_day")]
    return ("Clearance - " + " - ".join(str(p) for p in parts if p))[:255]


def prepare_draft(document):
    """draft_preparer: KHONG cho tao tay. Phieu chi sinh ra tu Don nghi viec da duyet."""
    if document.is_new() and not frappe.flags.get("ec_clearance_from_resignation"):
        frappe.throw(_("Clearance được tạo tự động khi Đơn nghỉ việc duyệt xong - không tạo tay."))


def create_from_resignation(resignation_name, raise_errors=False):
    """Tao + gui Clearance cho mot Don nghi viec DA DUYET. Idempotent. Chay NEN sau commit;
    hong thi rollback phan cua minh, ghi Error Log, bao HR (nguoi xu ly Don) - khong im lang."""
    try:
        name = _create_and_submit(resignation_name)
        frappe.db.commit()
        return name
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="Clearance: khong tao duoc tu %s" % resignation_name,
                         message=frappe.get_traceback())
        if raise_errors:
            raise
        return None


def _employee_of(email):
    if not email:
        return None
    for f in ("user_id", "company_email", "personal_email"):
        emp = frappe.db.get_value("Employee", {f: email},
                                  ["name", "employee_name", "user_id", "department", "company",
                                   "reports_to"], as_dict=True)
        if emp:
            return emp
    return None


def _create_and_submit(resignation_name):
    frappe.db.get_value(RESIGNATION_DT, resignation_name, "name", for_update=True)
    res = frappe.get_doc(RESIGNATION_DT, resignation_name)
    st = res.approval_request and frappe.db.get_value(
        "EC Approval Request", res.approval_request, "approval_status")
    if st != "Approved":
        frappe.throw(_("Đơn nghỉ việc {0} chưa được duyệt xong.").format(resignation_name))
    name = frappe.db.get_value(BUSINESS_DT, {"resignation_request": resignation_name}, "name")
    if name and frappe.db.get_value(BUSINESS_DT, name, "approval_request"):
        return name                                      # da co va da gui
    emp = _employee_of(res.employee_email)
    if name:
        doc = frappe.get_doc(BUSINESS_DT, name)          # ban truoc tao duoc nhung gui hong
    else:
        doc = frappe.new_doc(BUSINESS_DT)
        doc.resignation_request = res.name
        doc.employee_email = res.employee_email
        doc.last_working_day = res.last_working_day
        doc.resignation_reason = res.resignation_reason
        if emp:
            doc.employee = emp.name
            doc.employee_name = emp.employee_name
            doc.department = emp.department
            doc.company = emp.company
            if emp.reports_to:
                doc.line_manager = frappe.db.get_value("Employee", emp.reports_to, "user_id")
        # Phieu mang TEN nhan vien nghi viec (file Excel); khong co tai khoan thi nguoi nop Don.
        doc.requested_by = (emp and emp.user_id) or res.requested_by
    doc.request_title = gen_title(doc)
    frappe.flags.ec_clearance_from_resignation = True
    try:
        doc.save(ignore_permissions=True)
    finally:
        frappe.flags.ec_clearance_from_resignation = False
    doc.submitted_at = now_datetime()
    doc.save(ignore_permissions=True)
    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, doc.requested_by)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return doc.name


def submit(name):
    """Gui lai mot phieu da tao nhung gui hong. Chi System Manager (phieu khong co nguoi gui that)."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Chỉ quản trị viên gửi lại được phiếu Clearance."), frappe.PermissionError)
    return create_from_resignation(doc.resignation_request, raise_errors=True)


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=False)
    return {"restarted": False}


def clearance_block(business, request):
    """Checklist tung nhom (ai da xac nhan, luc nao, ghi chu) + muc ban giao cua nhom."""
    groups = {}
    if request:
        for r in frappe.get_all("EC Approval Request Approver",
                                filters={"approval_request": request.name},
                                fields=["participant_group", "approver", "status", "decided_at",
                                        "comment"], order_by="creation asc"):
            key = r.participant_group or "—"
            g = groups.setdefault(key, {"group": key, "done": False, "by": None, "at": None,
                                        "note": None, "members": [],
                                        "items": CHECKLIST.get(key, [])})
            g["members"].append(r.approver)
            if r.status == "Approved" and not g["done"]:
                g.update(done=True, by=r.approver, at=r.decided_at, note=r.comment)
    return {"greeting": GREETING, "groups": list(groups.values()),
            "resignation_route": "/approvals/resignation?id=%s" % business.get("resignation_request")}


def on_final_approval(name):
    """Du cac nhom da ban giao -> bao line manager (nguoi gui da duoc engine bao)."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.line_manager and doc.line_manager != doc.requested_by:
        engine.notify([doc.line_manager],
                      _("Đã hoàn tất bàn giao nghỉ việc: {0}").format(
                          engine.request_label(BUSINESS_DT, name)), BUSINESS_DT, name)
