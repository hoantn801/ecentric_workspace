"""Immutable command adapters and validation for the four legacy finance forms."""
from dataclasses import dataclass
from importlib import import_module


class _LazyFrappe:
    def __getattr__(self, name):
        return getattr(import_module("frappe"), name)


frappe = _LazyFrappe()


def _(message):
    return frappe._(message)


def getdate(value):
    return import_module("frappe.utils").getdate(value)


def now_datetime():
    return import_module("frappe.utils").now_datetime()


def _employee(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "company"], as_dict=True)


def _manager(user):
    employee = frappe.db.get_value("Employee", {"user_id": user},
                                   ["name", "reports_to"], as_dict=True)
    manager = employee and employee.reports_to and frappe.db.get_value(
        "Employee", employee.reports_to, "user_id")
    row = manager and frappe.db.get_value("User", manager, ["enabled", "user_type"], as_dict=True)
    return manager if row and row.enabled and row.user_type == "System User" else None


@dataclass(frozen=True, slots=True)
class Submitter:
    doctype: str
    code: str
    validator: object
    title_builder: object
    manager_required: bool = False
    requester_esign: bool = False

    def __call__(self, name):
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        user = frappe.session.user
        document = frappe.get_doc(self.doctype, name)
        if document.approval_request:
            frappe.throw(_("Yêu cầu này đã được gửi."))
        if (document.requested_by and document.requested_by != user
                and "System Manager" not in frappe.get_roles(user)):
            frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."), frappe.PermissionError)
        document.requested_by = document.requested_by or user
        employee = _employee(document.requested_by)
        if employee:
            document.employee = employee.name
            document.company = document.company or employee.company
        self.validator(document)
        if self.manager_required and not _manager(document.requested_by):
            frappe.throw(_("Không xác định được Quản lý trực tiếp của bạn. Vui lòng liên hệ HR/Admin "
                           "để cập nhật 'Báo cáo cho' (reports_to) trong hồ sơ nhân sự trước khi gửi yêu cầu."))
        document.request_title = self.title_builder(document)
        signature_required = False
        if self.requester_esign:
            from ecentric_workspace.platform.esign import guard
            signature_required = guard.requester_signature_required(self.doctype, self.code)
        if signature_required:
            # Tu choi TRUOC khi ghi bat cu thu gi. Xem assert_ready_to_submit: chan sau khi
            # engine.submit() chay thi mot lan commit o bat cu dau trong duong do se bien loi
            # tu choi thanh mot phieu "da gui" vinh vien khong ai ky duoc.
            from ecentric_workspace.platform.esign import requester as esign_requester
            esign_requester.assert_ready_to_submit(self.doctype, document.name)
        document.submitted_at = now_datetime()
        document.save(ignore_permissions=True)
        previous = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            request_name = engine.submit(
                self.doctype, document.name, self.code, document.requested_by,
                **({"activate_first_level": not signature_required} if self.requester_esign else {}))
        finally:
            frappe.flags.mute_messages = previous
        frappe.db.set_value(self.doctype, document.name, "approval_request", request_name)
        if signature_required:
            frappe.db.set_value("EC Approval Request", request_name,
                                "requester_signature_status", "Pending")
            # Chuan bi + khoa goi + ky, ngay tai day. Truoc do nguoi de nghi phai lam BA hanh
            # dong nua sau khi gui - deu la trang thai noi bo cua may, khong ai ngoai module
            # ky so can biet chung ton tai. Va trong hai ngay 27-28/08 chung con KHONG BAM
            # DUOC, nen luong dung lai o do hai lan.
            #
            # Nem loi khi chua dat du vi tri ky: mot yeu cau di ra voi goi ky khong dung duoc
            # con te hon mot yeu cau bi tu choi gui - loi tu choi thi thay ngay, con goi hong
            # thi khong.
            from ecentric_workspace.platform.esign import requester as esign_requester
            esign_requester.sign_on_submit(self.doctype, document.name)
        frappe.local.message_log = []
        return request_name


@dataclass(frozen=True, slots=True)
class Resubmitter:
    doctype: str
    title_builder: object

    def __call__(self, name, actor=None):
        from ecentric_workspace.approval_center.shared.workflow import transitions as engine
        document = frappe.get_doc(self.doctype, name)
        if not document.approval_request:
            frappe.throw(_("Yêu cầu này chưa được gửi."))
        frappe.db.set_value(self.doctype, name, "request_title", self.title_builder(document))
        previous = frappe.flags.mute_messages
        frappe.flags.mute_messages = True
        try:
            outcome = engine.resubmit(document.approval_request,
                                      actor=actor or frappe.session.user) or {}
        finally:
            frappe.flags.mute_messages = previous
        esign = outcome.get("esign") or {}
        # Goi ky vua duoc tao PHIEN BAN MOI -> phai chuan bi + khoa + ky lai, ngay tai day.
        #
        # Lan gui dau, Submitter lam ba viec do (sign_on_submit) va panel cua nguoi de nghi
        # da bo het nut bam vi chung la trang thai noi bo cua may. Duong GUI LAI khong lam,
        # nen sau khi bi tra lai va goi ky duoc lam moi thi: goi moi o trang thai Draft,
        # requester_signature_status ve "Pending", va KHONG CO NUT NAO de di tiep. Yeu cau
        # ket o do - khong bao gio ky duoc, cung khong bao gio duyet xong.
        #
        # Nem loi khi thieu vi tri ky la co y: chung tu vua dinh kem them cung la tep CAN KY
        # (xem requester._add_requester_pdf_files), nen no can o ky moi. Bao ngay con hon de
        # yeu cau di tiep voi mot goi ky khong dung duoc.
        if esign.get("revised"):
            from ecentric_workspace.platform.esign import requester as esign_requester
            esign_requester.sign_on_submit(self.doctype, name)
        return {"restarted": True, "esign": esign}

