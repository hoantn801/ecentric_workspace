# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC tren form 27: tinh tien luc luu, chot luc gui, khoi chi tiet.

Moi con so (gross, TNCN, VAT, so tien tra, tien coc, gia tri hop dong) do SERVER tinh tu
`domain.kol.compute_amounts` - form chi hien lai. Nguoi dung sua DOM cung khong doi duoc so
tien di vao hop dong va DNTT.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime, today

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.domain import kol
from ecentric_workspace.approval_center.shared.creators.repository import CreatorRepository

APPROVED = "Approved"


def creator_row(name):
    return CreatorRepository().get(name) if name else None


def prepare_draft(doc):
    """`draft_preparer` cua form 27: chi lam viec voi phieu KOL, nuot loi tinh tien (nhap do)."""
    if not kol.is_kol(doc):
        return
    creator = creator_row(doc.get("creator"))
    doc.creator_name = creator.get("supplier_name") if creator else None
    doc.creator_type = creator.get("ec_cr_type") if creator else None
    so = kol_lookup.sales_order_info(doc.get("sales_order")) if doc.get("sales_order") else None
    if so:
        doc.so_label = kol_lookup.so_label(so)
        doc.so_revenue = so.net_total
        if so.ec_brand:
            doc.brand = so.ec_brand
    else:
        doc.so_label = doc.so_revenue = None
    if not doc.get("payment_term_days"):
        doc.payment_term_days = kol.DEFAULT_PAYMENT_DAYS
    if not doc.get("contract_date"):
        doc.contract_date = today()
    if not (doc.get("justification") or "").strip():
        doc.justification = ("Hoa hồng affiliate" if doc.get("service_type") == "Hoa hồng affiliate"
                             else "Booking KOL/KOC")
    apply_amounts(doc, strict=False)
    if not (doc.get("request_details") or "").strip():
        doc.request_details = summary_text(doc)


def apply_amounts(doc, strict):
    try:
        amounts = kol.compute_amounts(doc.get("creator_type"), doc.get("amount_type"),
                                      doc.get("amount_input"), doc.get("pit_rate"), doc.get("vat_rate"))
        advance = kol.advance_amount(amounts["payable"], doc.get("payment_schedule"),
                                     doc.get("advance_percent"))
    except ValueError as e:
        if strict:
            frappe.throw(_(str(e)))
        doc.gross_amount = doc.pit_amount = doc.vat_amount = doc.payable_amount = None
        doc.advance_amount = None
        return
    doc.gross_amount, doc.pit_amount = amounts["gross"], amounts["pit"]
    doc.vat_amount, doc.payable_amount = amounts["vat"], amounts["payable"]
    doc.contract_value = amounts["contract_value"]
    doc.advance_amount = advance
    if doc.get("payment_schedule") != kol.PAY_ADVANCE:
        doc.advance_percent = None


def summary_text(doc):
    parts = [doc.get("service_type") or "", doc.get("platform") or "",
             ("%s buổi/video" % doc.quantity) if doc.get("quantity") else "",
             doc.get("duration") or "", doc.get("air_dates") or ""]
    return "Creator %s - %s" % (doc.get("creator_name") or "?", ", ".join(p for p in parts if p))


def validate_submit(doc):
    """Chot truoc khi vao luong duyet. Goi tu service.submit, chi voi phieu KOL."""
    creator = creator_row(doc.get("creator"))
    errors = kol.validate_kol(doc, creator and creator.get("ec_cr_type"))
    if not creator:
        errors.append("Creator không tồn tại hoặc không thuộc danh sách creator.")
    if doc.get("request_type") == kol.TEMPLATE_EC and not doc.get("contract_file"):
        errors.append("Bấm \"Tạo hợp đồng từ mẫu\" trước khi gửi.")
    if doc.get("request_type") == kol.TEMPLATE_PARTNER and not doc.get("request_attachment"):
        errors.append("Tải lên hợp đồng theo mẫu của creator trước khi gửi.")
    if doc.get("missing_placeholders"):
        errors.append("Mẫu còn trường chưa có dữ liệu: %s." % doc.missing_placeholders)
    if errors:
        frappe.throw(_(" ".join(errors)))
    prepare_draft(doc)
    apply_amounts(doc, strict=True)
    if not doc.get("contract_no"):
        assign_number(doc, creator)
    committed = kol_lookup.committed_on_so(doc.sales_order, exclude=doc.name)
    doc.revenue_warning = kol.revenue_warning(doc.so_revenue, committed, doc.contract_value) or None


def assign_number(doc, creator):
    existing = set(frappe.get_all(kol_lookup.CR_DT, filters={"contract_no": ["is", "set"]},
                                  pluck="contract_no", limit_page_length=0, ignore_permissions=True))
    try:
        doc.contract_no = kol.contract_number(doc.contract_date or today(),
                                              creator.get("ec_cr_party_code"),
                                              kol_lookup.brand_code(doc.get("brand")), existing)
    except ValueError as e:
        frappe.throw(_(str(e)))


def can_manage(doc, user):
    return doc.requested_by == user or kol_lookup.is_finance(user)


def approval_status(doc):
    if not doc.get("approval_request"):
        return None
    return frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_status")


def is_signed(doc):
    return doc.get("signing_status") == kol.SIGN_DONE


def mark_signed(name, signed_file, user):
    """Tam thoi (truoc giai doan 4 SCTS): ky tren cong roi tai ban da ky len, xac nhan ky du."""
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc) or not can_manage(doc, user):
        frappe.throw(_("Chỉ người tạo hợp đồng hoặc Kế toán được xác nhận ký."), frappe.PermissionError)
    if approval_status(doc) != APPROVED:
        frappe.throw(_("Hợp đồng phải được duyệt xong trước khi xác nhận đã ký."))
    if not (signed_file or "").lower().endswith(".pdf"):
        frappe.throw(_("Bản đã ký phải là tệp PDF."))
    from ecentric_workspace.approval_center.features.contract_review.application.kol_files import claim_upload
    doc.signed_file = claim_upload(doc, signed_file, user)
    doc.signing_status = kol.SIGN_DONE
    doc.signed_at = now_datetime()
    doc.signed_marked_by = user
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", _("Xác nhận hợp đồng đã ký đủ hai bên."))
    return {"signing_status": doc.signing_status}


def detail_extra(business, request):
    """`detail_extender`: khoi KOL tren trang chi tiet (khong co PII creator)."""
    if not kol.is_kol(business):
        return {}
    from ecentric_workspace.approval_center.features.contract_review.application import kol_acceptance
    user = frappe.session.user
    status = (request or {}).get("approval_status") if isinstance(request, dict) else getattr(request, "approval_status", None)
    return {"kol": {
        "can_manage": can_manage(business, user),
        "is_finance": kol_lookup.is_finance(user),
        "approved": status == APPROVED,
        "signed": is_signed(business),
        "acceptances": kol_acceptance.rows_view(business),
        "funding": kol_acceptance.funding_view(business),
    }}
