# Copyright (c) 2026, eCentric and contributors
"""Cac dot nghiem thu (BBNT) cua hop dong KOL/KOC va tran chi cho DNTT.

Luat chot 11/11/2026:
  * BBNT chi tao khi hop dong da duyet xong VA da ky du. BBNT di cung chuoi ky voi hop dong
    (KTTH -> KTT -> CEO ky -> creator ky); truoc giai doan 4 thi ky tren cong roi tai ban da
    ky len, bam "Hoàn tất".
  * Han thanh toan = ngay hoan tat + so ngay cua hop dong (ngay lich, T7/CN doi sang thu Hai).
  * DNTT: coc duoc chi khi DA KY; phan con lai chi theo BBNT da hoan tat. Mot hop dong nhan
    nhieu dot (hoa hong affiliate theo thang).
"""
import frappe
from frappe import _
from frappe.utils import flt, now_datetime, nowdate

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
    APPROVED, approval_status, can_manage, creator_row, is_signed)
from ecentric_workspace.approval_center.features.contract_review.domain import kol


def _load(name, user):
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc) or not can_manage(doc, user):
        frappe.throw(_("Chỉ người tạo hợp đồng hoặc Kế toán được thao tác nghiệm thu."),
                     frappe.PermissionError)
    return doc


def _row(doc, row_name):
    for r in doc.acceptances or []:
        if r.name == row_name:
            return r
    frappe.throw(_("Không tìm thấy đợt nghiệm thu."))


def done_amount(doc):
    return sum(flt(r.amount) for r in (doc.acceptances or []) if r.status == kol.BBNT_DONE)


def add_acceptance(name, user, description, acceptance_date=None, amount=None):
    doc = _load(name, user)
    if approval_status(doc) != APPROVED or not is_signed(doc):
        frappe.throw(_("Chỉ tạo BBNT khi hợp đồng đã duyệt xong và đã ký đủ hai bên."))
    amount = flt(amount)
    if amount <= 0:
        frappe.throw(_("Số tiền đợt nghiệm thu phải lớn hơn 0."))
    planned = sum(flt(r.amount) for r in (doc.acceptances or [])) + flt(doc.advance_amount)
    if planned + amount > flt(doc.payable_amount) + 0.5:
        frappe.throw(_("Tổng các đợt nghiệm thu và tiền cọc vượt số tiền trả creator ({0}).")
                     .format(kol.fmt_money(doc.payable_amount)))
    row = doc.append("acceptances", {"description": (description or "").strip()[:140] or "Nghiệm thu",
                                     "acceptance_date": acceptance_date or nowdate(),
                                     "amount": amount, "status": kol.BBNT_DRAFT})
    doc.save(ignore_permissions=True)
    row = _row(doc, row.name)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_files
    url, missing = kol_files.generate_acceptance(doc, row, creator_row(doc.creator))
    row.bbnt_file = url
    doc.save(ignore_permissions=True)
    return {"row": row.name, "bbnt_file": url, "missing": missing}


def send_acceptance(name, user, row_name):
    doc = _load(name, user)
    row = _row(doc, row_name)
    if row.status != kol.BBNT_DRAFT:
        frappe.throw(_("Đợt này đã gửi ký."))
    row.status = kol.BBNT_SENT
    doc.save(ignore_permissions=True)
    return {"status": row.status}


def complete_acceptance(name, user, row_name, signed_file):
    doc = _load(name, user)
    row = _row(doc, row_name)
    if row.status == kol.BBNT_DONE:
        frappe.throw(_("Đợt này đã hoàn tất."))
    if not (signed_file or "").lower().endswith(".pdf"):
        frappe.throw(_("Tải lên BBNT đã ký (PDF) trước khi hoàn tất."))
    from ecentric_workspace.approval_center.features.contract_review.application.kol_files import claim_upload
    row.signed_file = claim_upload(doc, signed_file, user)
    row.status = kol.BBNT_DONE
    row.completed_at = now_datetime()
    row.completed_by = user
    row.due_date = kol.due_date(row.completed_at.date(), doc.payment_term_days)
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", _("BBNT đợt {0} hoàn tất, hạn thanh toán {1}.").format(
        row.idx, row.due_date.strftime("%d/%m/%Y")))
    return {"status": row.status, "due_date": str(row.due_date)}


def payable_cap(doc):
    """Tran chi hien tai cho DNTT (truoc khi tru phan da de nghi)."""
    if approval_status(doc) != APPROVED:
        return 0.0
    return kol.acceptance_cap(is_signed(doc), doc.get("advance_amount"), done_amount(doc),
                              doc.get("payable_amount"))


def rows_view(doc):
    return [{"name": r.name, "idx": r.idx, "description": r.description,
             "acceptance_date": str(r.acceptance_date or ""), "amount": flt(r.amount),
             "status": r.status, "bbnt_file": r.bbnt_file, "signed_file": r.signed_file,
             "completed_at": str(r.completed_at or ""), "due_date": str(r.due_date or "")}
            for r in (doc.acceptances or [])]


def funding_view(doc):
    from ecentric_workspace.approval_center.features.payment_request.application import funding
    cap = payable_cap(doc)
    used = funding.consumed_amount(kol_lookup.CR_DT, doc.name)
    return {"payable": flt(doc.payable_amount), "advance": flt(doc.advance_amount),
            "accepted": done_amount(doc), "cap": cap, "used": used, "remaining": cap - used}
