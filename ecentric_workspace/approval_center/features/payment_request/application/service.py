"""Business rules owned by the payment_request module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate
from ecentric_workspace.approval_center.features.payment_request.application import funding


def payment_title(doc):
    """User-entered title wins; auto-generated 'Payment Request - payee - amount' only when
    the title is left blank (2026-08-23: the form now has an explicit title field, which also
    feeds eContract docTitle via the profile's title_source)."""
    manual = (doc.get("request_title") or "").strip()
    if manual:
        return manual[:180]
    amount = doc.get("payment_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return ("Payment Request - %s - %s" % (doc.get("payee_full_name") or "?", amount))[:180]

def normalize_payment(doc):
    doc.details_and_attachments_correct = ("Yes" if doc.details_and_attachments_correct is True
        or str(doc.details_and_attachments_correct or "").strip().lower() in ("yes", "1", "true") else "No")
    _sync_funding_aliases(doc)


def _sync_funding_aliases(doc):
    """Keep the legacy `purchase_request` field and the generic funding pair in step.

    `purchase_request` predates the generic pair and is still read by older code paths and by
    historical records, so we dual-write instead of dropping it. The generic pair is canonical;
    the legacy field mirrors it only when the source IS an EC Purchase Request.
    """
    src_dt = (doc.get("funding_source_doctype") or "").strip()
    src_name = (doc.get("funding_source_name") or "").strip()
    legacy = (doc.get("purchase_request") or "").strip()
    if src_dt and src_name:
        doc.purchase_request = src_name if src_dt == "EC Purchase Request" else None
    elif legacy:
        # Older client (or historical draft) only set the legacy field -> promote it.
        doc.funding_source_doctype = "EC Purchase Request"
        doc.funding_source_name = legacy

def validate_payment(doc):
    required = ("reason", "payment_date", "payee_full_name", "account_bank", "bank_account_number",
                "has_purchase_request", "is_cost_valid", "request_attachment")
    if any(not str(doc.get(f) or "").strip() for f in required) or doc.payment_amount is None:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    try:
        if float(doc.payment_amount) <= 0: frappe.throw(_("Số tiền thanh toán phải lớn hơn 0."))
    except (TypeError, ValueError): frappe.throw(_("Số tiền thanh toán phải là số."))
    normalize_payment(doc)
    if doc.details_and_attachments_correct != "Yes": frappe.throw(_("Vui lòng tích xác nhận thông tin và tệp đính kèm là chính xác trước khi gửi."))
    if doc.has_purchase_request == "Yes":
        if not (doc.get("funding_source_doctype") or "").strip() or not (doc.get("funding_source_name") or "").strip():
            frappe.throw(_("Vui lòng chọn chứng từ nguồn (ĐNMH hoặc PO) cho khoản thanh toán này."))
    elif doc.has_purchase_request == "No":
        if not (doc.no_purchase_request_reason or "").strip():
            frappe.throw(_("Vui lòng nhập lý do không có Purchase Request khi chọn 'No'."))
        # "No" must not smuggle a source through a stale draft value.
        doc.funding_source_doctype = None
        doc.funding_source_name = None
        doc.purchase_request = None
    # Single guard for every source type: exists + approved + does not exceed the remainder.
    funding.validate_funding(doc)


# --------------------------------------------------------------------------- #
# Buoc 6 - Finance xu ly UNC (07/09, Hoan). Engine fulfillment dung chung: sau cap duyet
# cuoi, engine.complete_approval goi on_final_approval (dang ky o transitions._FULFILLMENT_
# HANDLERS). Ca phong Finance (Fulfiller = Role EC Finance tren process) nhan ToDo; ai ranh
# bam "Nhan xu ly"; hoan tat = dinh kem file UNC. Han xu ly = NGAY THANH TOAN cua phieu
# (khong phai SLA gio), nhac tu D-3 (reminders.remind_unc_due).
# --------------------------------------------------------------------------- #
BUSINESS_DT = "EC Payment Request"
APPROVAL_TYPE = "PAYMENT_REQUEST"
#: Gio "het ngay lam viec" dung lam han xu ly UNC trong ngay thanh toan.
UNC_DUE_HOUR = 17


def _engine():
    from ecentric_workspace.approval_center.shared.workflow import transitions
    return transitions


def unc_due_at(payment_date):
    """Han xu ly UNC = 17:00 ngay thanh toan. Khong co ngay -> None (khong bia han)."""
    if not payment_date:
        return None
    from datetime import datetime, time
    return datetime.combine(getdate(payment_date), time(UNC_DUE_HOUR, 0))


def on_final_approval(name):
    engine = _engine()
    doc = frappe.get_doc(BUSINESS_DT, name)
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    proc = frappe.get_doc("EC Approval Process", proc_name)
    fulfillers = [u for u, _lbl in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]
    due = unc_due_at(doc.payment_date)
    frappe.db.set_value(BUSINESS_DT, name, {
        "fulfillment_status": "Assigned",
        "fulfillment_owner": None,
        "fulfillment_due_at": due,
    })
    if fulfillers:
        # ToDo.date = ngay thanh toan -> Nhac viec xep vao "sap toi / hom nay / qua han".
        engine.assign(BUSINESS_DT, name, fulfillers, _("Finance xử lý UNC"),
                      date=getdate(doc.payment_date) if doc.payment_date else None,
                      fulfillment=True)
    else:
        # Khong co ai trong nhom Finance: phieu van Assigned (hub SM thay), ghi log de sua config.
        frappe.log_error("Payment Request %s: process %s khong co Fulfiller nao" % (name, proc_name),
                         "payment_request.on_final_approval")
    engine.notify([doc.requested_by] + fulfillers,
                  _("Đã duyệt xong — chuyển Finance xử lý UNC (hạn {0}): {1}").format(
                      frappe.utils.formatdate(doc.payment_date) if doc.payment_date else "—",
                      engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)


def claim_fulfillment(name, user=None):
    engine = _engine()
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and not engine.is_active_process_fulfiller(APPROVAL_TYPE, user) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Bạn không thuộc nhóm Finance xử lý UNC."), frappe.PermissionError)
    # UPDATE co dieu kien: hai nguoi bam cung luc thi chi mot nguoi thang.
    frappe.db.sql(
        """update `tabEC Payment Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC Payment Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Phiếu này đã có người khác nhận xử lý."))
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Finance xử lý UNC"),
                            date=getdate(doc.payment_date) if doc.payment_date else None)
    engine.log_action(doc.approval_request, "Started", user, comment=_("Finance nhận xử lý UNC"),
                      new_status="In Progress")
    engine.notify([doc.requested_by],
                  _("{0} đã nhận xử lý UNC: {1}").format(user, engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"owner": user}


def complete_fulfillment(name, user=None, payload=None):
    engine = _engine()
    from ecentric_workspace.approval_center.shared.requests.command_service import attach_extra_files
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_status not in ("Assigned", "In Progress"):
        frappe.throw(_("Phiếu không ở bước Finance xử lý UNC."))
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chỉ người đã nhận xử lý hoặc System Manager mới được hoàn tất."),
                     frappe.PermissionError)
    url = str(data.get("completed_attachment") or doc.completed_attachment or "").strip()
    if not url.startswith(("/files", "/private/files")):
        frappe.throw(_("Vui lòng đính kèm file UNC trước khi hoàn tất."))
    doc.completed_attachment = url
    doc.fulfillment_summary = str(data.get("fulfillment_summary") or "").strip()[:500] or None
    # File UNC duoc tai len KHONG kem doctype/docname (nhan vien thuong khong co DocPerm
    # chuan) -> la File mo coi; gan vao phieu TRUOC khi save de hook attach_files cua Frappe
    # thay da co, khong tao dong thu hai.
    attach_extra_files(doc, [url])
    doc.fulfillment_status = "Completed"
    doc.fulfillment_owner = doc.fulfillment_owner or user
    doc.completed_by = user
    doc.completed_at = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    engine.close_fulfillment_todos(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Completed", user,
                      comment=_("Đã xử lý UNC") + (": " + doc.fulfillment_summary if doc.fulfillment_summary else ""),
                      new_status="Completed")
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Đã thanh toán (UNC): {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"completed": True}

