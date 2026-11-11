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
    so = None
    if doc.get("sales_order"):
        # Kiem lai SO tren server: bo chon tren trang loc theo team, nhung save_draft nhan
        # thang ten SO - khong kiem thi doc duoc doanh thu SO cua team khac (QC 11/11).
        so, err = kol_lookup.so_allowed(frappe.session.user, doc.sales_order)
        if err:
            frappe.throw(_(err), frappe.PermissionError)
    if so:
        doc.so_label = kol_lookup.so_label(so)
        doc.so_revenue = so.net_total
        if so.ec_brand:
            doc.brand = so.ec_brand
    else:
        doc.so_label = doc.so_revenue = None
    if doc.get("payment_term_days") in (None, ""):
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
        kol.payment_days(doc.get("payment_term_days"))
    except ValueError as e:
        if strict:
            frappe.throw(_(str(e)))
        # Nhap do: xoa HET so da tinh, ke ca gia tri hop dong - khong de lai so cu lech voi tien.
        doc.gross_amount = doc.pit_amount = doc.vat_amount = doc.payable_amount = None
        doc.advance_amount = doc.contract_value = None
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
    """Chot truoc khi vao luong duyet - goi tu service.submit VA service.resubmit (phieu KOL).

    Mau EC: sinh lai hop dong neu du lieu da doi tu lan tao tep (dau van tay lech), de van ban
    gui ky luon khop so tien / creator / SO dang duyet."""
    creator = creator_row(doc.get("creator"))
    errors = kol.validate_kol(doc, creator and creator.get("ec_cr_type"))
    if not creator:
        errors.append("Creator không tồn tại hoặc không thuộc danh sách creator.")
    if doc.get("request_type") == kol.TEMPLATE_PARTNER and not doc.get("request_attachment"):
        errors.append("Tải lên hợp đồng theo mẫu của creator trước khi gửi.")
    if errors:
        frappe.throw(_(" ".join(errors)))
    prepare_draft(doc)
    apply_amounts(doc, strict=True)
    if doc.get("request_type") == kol.TEMPLATE_EC:
        from ecentric_workspace.approval_center.features.contract_review.application import kol_files
        kol_files.build_contract(doc)
    else:
        assign_number(doc, creator)
    if doc.get("missing_placeholders"):
        frappe.throw(_("Hợp đồng còn thiếu thông tin: {0}. Bổ sung (thường là thông tin creator) "
                       "rồi gửi lại.").format(doc.missing_placeholders))
    committed = kol_lookup.committed_on_so(doc.sales_order, exclude=doc.name)
    doc.revenue_warning = kol.revenue_warning(doc.so_revenue, committed, doc.contract_value) or None


def assign_number(doc, creator):
    """Cap / cap lai so hop dong. So dang co ma khong con khop ngay ky / ma doi tac / ma brand
    (doi creator, brand, ngay sau lan tao dau) thi cap lai - so sai di vao van ban phap ly."""
    try:
        base = kol.number_base(doc.contract_date or today(), creator.get("ec_cr_party_code"),
                               kol_lookup.brand_code(doc.get("brand")))
    except ValueError as e:
        frappe.throw(_(str(e)))
    if kol.number_fits(doc.get("contract_no"), base):
        return
    existing = set(frappe.get_all(kol_lookup.CR_DT,
                                  filters={"contract_no": ["like", base + "%"], "name": ["!=", doc.name]},
                                  pluck="contract_no", limit_page_length=0, ignore_permissions=True))
    doc.contract_no = kol.contract_number(doc.contract_date or today(), creator.get("ec_cr_party_code"),
                                          kol_lookup.brand_code(doc.get("brand")), existing)


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
        "acceptance_remaining": kol_acceptance.acceptance_remaining(business),
        "funding": kol_acceptance.funding_view(business),
    }}
