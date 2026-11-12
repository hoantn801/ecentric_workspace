# Copyright (c) 2026, eCentric and contributors
"""Kiem ban da ky (hop dong / BBNT) truoc khi mo tran chi DNTT.

Anh Hoan chot 11/11/2026: nguoi tao hop dong tai ban ky len KHONG tu dong "ky du" - can Ke toan
hoac kiem tu dong. Luong:
  1. Tai ban ky -> may kiem (domain.kol.signed_pdf_findings): >= 2 chu ky so, dung so hop
     dong, BBNT co so tien cua dot.
  2. Dat -> "Đã ký đủ" / "Hoàn tất", nguoi xac nhan = "Tự động (máy kiểm)".
  3. Khong dat (ban scan ky tay, thieu chu ky, sai tep...) -> "Chờ kiểm tra", ghi ly do; Ke toan
     (EC Finance / SM) xac nhan hoac tra lai. Tran chi chi mo khi da xac nhan.
Truoc giai doan 4 (SCTS) day la cho DUY NHAT chan nguoi tao tu xac nhan ky cho chinh minh.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.application.kol_ai import (
    number_tokens, pdf_text)
from ecentric_workspace.approval_center.features.contract_review.application.kol_files import doc_file_bytes
from ecentric_workspace.approval_center.features.contract_review.domain import kol


def check(doc, file_url, amount=None):
    """-> danh sach van de (rong = dat)."""
    data = doc_file_bytes(doc, file_url)
    text = pdf_text(data)
    return kol.signed_pdf_findings(data, number_tokens(text), text, doc.get("contract_no"), amount)


def _note(findings):
    return "\n".join("- " + f for f in findings) or None


def apply_contract_check(doc):
    """Goi sau khi gan doc.signed_file (chua luu). Dat thi ky du ngay, khong thi cho Ke toan."""
    findings = check(doc, doc.signed_file)
    doc.sign_check_note = _note(findings)
    if findings:
        doc.signing_status = kol.SIGN_REVIEW
        doc.signed_verified_by = doc.signed_verified_at = None
    else:
        doc.signing_status = kol.SIGN_DONE
        doc.signed_verified_by = kol.AUTO_VERIFIER
        doc.signed_verified_at = now_datetime()
    return findings


def apply_acceptance_check(doc, row):
    findings = check(doc, row.signed_file, row.amount)
    row.check_note = _note(findings)
    if findings:
        row.status = kol.BBNT_REVIEW
        row.verified_by = None
    else:
        row.status = kol.BBNT_DONE
        row.verified_by = kol.AUTO_VERIFIER
    return findings


def _finance_doc(name, user):
    if not kol_lookup.is_finance(user):
        frappe.throw(_("Chỉ Kế toán (EC Finance) xác nhận bản ký."), frappe.PermissionError)
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc):
        frappe.throw(_("Phiếu này không phải hợp đồng KOL/KOC."))
    return doc


def _who(user):
    return frappe.db.get_value("User", user, "full_name") or user


def verify_contract(name, user, ok, note=None):
    """Ke toan xac nhan / tra lai ban hop dong da ky dang 'Chờ kiểm tra'."""
    doc = _finance_doc(name, user)
    if doc.get("signing_status") != kol.SIGN_REVIEW:
        frappe.throw(_("Bản ký không ở trạng thái chờ kiểm tra."))
    note = (note or "").strip()
    if ok:
        doc.signing_status = kol.SIGN_DONE
        doc.signed_verified_by = _who(user)
        doc.signed_verified_at = now_datetime()
        msg = _("Kế toán xác nhận hợp đồng đã ký đủ hai bên.")
    else:
        if not note:
            frappe.throw(_("Nhập lý do trả lại để người tạo biết cần sửa gì."))
        doc.signing_status = kol.SIGN_PENDING
        doc.signed_file = None
        msg = _("Kế toán trả lại bản ký: {0}").format(note)
    if note:
        doc.sign_check_note = ((doc.get("sign_check_note") or "") + "\nKế toán: " + note).strip()
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", msg)
    return {"signing_status": doc.signing_status}


def verify_acceptance(name, user, row_name, ok, note=None):
    doc = _finance_doc(name, user)
    row = next((r for r in (doc.acceptances or []) if r.name == row_name), None)
    if not row:
        frappe.throw(_("Không tìm thấy đợt nghiệm thu."))
    if row.status != kol.BBNT_REVIEW:
        frappe.throw(_("Đợt này không ở trạng thái chờ kiểm tra."))
    note = (note or "").strip()
    if ok:
        row.status = kol.BBNT_DONE
        row.verified_by = _who(user)
        msg = _("Kế toán xác nhận BBNT đợt {0} đã ký đủ.").format(row.idx)
    else:
        if not note:
            frappe.throw(_("Nhập lý do trả lại để người tạo biết cần sửa gì."))
        row.status = kol.BBNT_SENT
        row.signed_file = row.completed_at = row.completed_by = row.due_date = None
        msg = _("Kế toán trả lại BBNT đợt {0}: {1}").format(row.idx, note)
    if note:
        row.check_note = ((row.get("check_note") or "") + "\nKế toán: " + note).strip()
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", msg)
    return {"status": row.status}


def pending_checks(user):
    """Hang doi cua Ke toan: hop dong / BBNT dang cho kiem ban ky."""
    if not kol_lookup.is_finance(user):
        frappe.throw(_("Chỉ Kế toán (EC Finance) xem hàng chờ này."), frappe.PermissionError)
    out = []
    for r in frappe.get_all(kol_lookup.CR_DT, filters={"contract_type": kol.KOL_CONTRACT_TYPE,
                                                       "signing_status": kol.SIGN_REVIEW},
                            fields=["name", "contract_no", "creator_name", "requested_by", "signed_at"],
                            order_by="signed_at asc", limit_page_length=200, ignore_permissions=True):
        out.append({"kind": "Hợp đồng", "name": r.name, "contract_no": r.contract_no,
                    "creator_name": r.creator_name, "requested_by": r.requested_by,
                    "at": str(r.signed_at or "")})
    for r in frappe.get_all("EC Contract Acceptance", filters={"status": kol.BBNT_REVIEW,
                                                               "parenttype": kol_lookup.CR_DT},
                            fields=["parent", "idx", "amount", "completed_at"],
                            order_by="completed_at asc", limit_page_length=200, ignore_permissions=True):
        head = frappe.db.get_value(kol_lookup.CR_DT, r.parent,
                                   ["contract_no", "creator_name", "requested_by"], as_dict=True) or {}
        out.append({"kind": "BBNT đợt %s" % r.idx, "name": r.parent, "contract_no": head.get("contract_no"),
                    "creator_name": head.get("creator_name"), "requested_by": head.get("requested_by"),
                    "amount": float(r.amount or 0), "at": str(r.completed_at or "")})
    return out
