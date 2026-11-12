# Copyright (c) 2026, eCentric and contributors
"""Diem nen tang ky so (platform/esign) goi vao phieu Contract Review - hop dong giua hai chat,
chot 12/11/2026 (ERP Website/THIETKE_ky_so_hop_dong.md, K1 / K5).

Nen tang KHONG import module nay: no doc `ec_esign_outcome_handlers` trong hooks.py roi goi

    on_signing_outcome(business_name, purpose, outcome, signed_file=None, detail=None)

    purpose = "contract"          -> goi ky ban hop dong
              "bbnt:<row.name>"   -> goi ky BBNT cua dot nghiem thu <row.name>
    outcome = "signed"            -> ky du; signed_file = file_url PDF ky du, DA dinh kem vao phieu
              "rejected" / "returned" / "destroyed" -> khong thanh (doi tac / CEO tu choi, tra lai
                                                       nguoi tao, huy tren cong); detail = ly do
    -> {"changed": bool, ...}. Goi lai nhieu lan an toan. Sai tham so / trang thai -> ValueError
    (nen tang ghi log, khong nuot im).

Khi khong thanh, phieu GIU "Da duyet" (khong mo lai luong duyet ERP): hop dong ve "Chua ky" de
nguoi lap sua tep va Gui ky lai; dot BBNT ve "Nhap" de tao lai BBNT (THIETKE Q2).

`package_title(business_name, purpose)`: tieu de tai lieu tren cong (phia Hop dong truyen vao).
Khong whitelist - chi goi tu server.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.domain import kol

ESIGN_ACTOR = "Ký số (cổng)"
CONTRACT = "contract"
BBNT_PREFIX = "bbnt:"
SIGNED, REJECTED, RETURNED, DESTROYED = "signed", "rejected", "returned", "destroyed"
OUTCOMES = (SIGNED, REJECTED, RETURNED, DESTROYED)
_OUTCOME_TEXT = {REJECTED: "bị từ chối", RETURNED: "bị trả lại người tạo", DESTROYED: "bị huỷ trên cổng"}


def on_signing_outcome(business_name, purpose, outcome, signed_file=None, detail=None):
    if outcome not in OUTCOMES:
        raise ValueError("outcome khong hop le: %r" % (outcome,))
    if not frappe.db.exists(kol_lookup.CR_DT, business_name):
        raise ValueError("khong co phieu %r" % (business_name,))
    if outcome == SIGNED and not str(signed_file or "").lower().endswith(".pdf"):
        raise ValueError("signed_file phai la PDF da dinh kem")
    doc = frappe.get_doc(kol_lookup.CR_DT, business_name)
    from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
        APPROVED, approval_status)
    if approval_status(doc) != APPROVED:
        raise ValueError("phieu %s chua duyet xong tren ERP" % business_name)
    if purpose == CONTRACT:
        return _contract(doc, outcome, signed_file, detail)
    if str(purpose or "").startswith(BBNT_PREFIX):
        return _round(doc, str(purpose)[len(BBNT_PREFIX):], outcome, signed_file, detail)
    raise ValueError("purpose khong hop le: %r" % (purpose,))


def package_title(business_name, purpose):
    """Tieu de tai lieu tren cong: "HĐ <so HD> - <doi tac>" / "BBNT đợt n - <so HD>"."""
    doc = frappe.get_doc(kol_lookup.CR_DT, business_name)
    no = doc.get("contract_no") or doc.name
    if str(purpose or "").startswith(BBNT_PREFIX):
        row = _find_row(doc, str(purpose)[len(BBNT_PREFIX):])
        return "BBNT đợt %s - %s" % (row.idx, no)
    who = doc.get("creator_name") or doc.get("partner_signer_name") or doc.get("request_title") or ""
    return ("HĐ %s - %s" % (no, who)).strip(" -")[:140]


def _why(detail):
    if isinstance(detail, dict):
        detail = detail.get("reason") or detail.get("comment") or detail.get("message") or ""
    return str(detail or "").strip()[:500]


def _contract(doc, outcome, signed_file, detail):
    if outcome != SIGNED:
        if doc.get("signing_status") == kol.SIGN_DONE:
            return {"changed": False, "signing_status": doc.signing_status}
        doc.signing_status = kol.SIGN_PENDING
        doc.save(ignore_permissions=True)
        doc.add_comment("Info", _("{0}: hợp đồng {1}{2}. Sửa tệp rồi Gửi ký lại.").format(
            ESIGN_ACTOR, _OUTCOME_TEXT[outcome], (": " + _why(detail)) if _why(detail) else ""))
        return {"changed": True, "signing_status": doc.signing_status}
    if doc.get("signing_status") == kol.SIGN_DONE or (
            doc.get("signing_status") == kol.SIGN_REVIEW and doc.get("signed_file") == signed_file):
        return {"changed": False, "signing_status": doc.signing_status}
    doc.signed_file = signed_file
    doc.signed_at = now_datetime()
    doc.signed_marked_by = None
    findings = []
    if kol.is_kol(doc):
        # Van cho may kiem so HD / chu ky chay: cong bao "ky du" nhung tep sai so HD thi Ke toan xem.
        from ecentric_workspace.approval_center.features.contract_review.application import kol_verify
        findings = kol_verify.apply_contract_check(doc)
    else:
        doc.signing_status = kol.SIGN_DONE
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", _("{0}: hợp đồng ký đủ trên cổng.").format(ESIGN_ACTOR) if not findings
                    else _("{0}: cổng báo ký đủ - chờ Kế toán kiểm: {1}").format(ESIGN_ACTOR, "; ".join(findings)))
    return {"changed": True, "signing_status": doc.signing_status, "findings": findings}


def _find_row(doc, row_name):
    row = next((r for r in (doc.get("acceptances") or []) if r.name == row_name), None)
    if row is None:
        raise ValueError("khong co dot nghiem thu %r tren %s" % (row_name, doc.name))
    return row


def _round(doc, row_name, outcome, signed_file, detail):
    row = _find_row(doc, row_name)
    if row.status in (kol.BBNT_DONE, kol.BBNT_REVIEW):
        return {"changed": False, "status": row.status}
    if outcome != SIGNED:
        if row.status != kol.BBNT_SENT:
            return {"changed": False, "status": row.status}
        row.status = kol.BBNT_DRAFT            # ve Nhap: sua du lieu, tao lai BBNT, gui ky lai
        doc.save(ignore_permissions=True)
        doc.add_comment("Info", _("{0}: BBNT đợt {1} {2}{3}.").format(
            ESIGN_ACTOR, row.idx, _OUTCOME_TEXT[outcome], (": " + _why(detail)) if _why(detail) else ""))
        return {"changed": True, "status": row.status}
    # Cung chot nhu tai tay (complete_acceptance): da qua buoc gui ky (kiem thieu + tao lai BBNT),
    # hop dong da ky du, tep khong trung hop dong / dot khac (QC7).
    if row.status != kol.BBNT_SENT:
        raise ValueError("dot %s chua qua buoc gui ky (trang thai %s)" % (row.idx, row.status))
    from ecentric_workspace.approval_center.features.contract_review.application.kol_service import is_signed
    if not is_signed(doc):
        raise ValueError("hop dong %s chua ky du" % doc.name)
    used = {r.signed_file for r in (doc.acceptances or []) if r.name != row.name and r.signed_file}
    if signed_file in used or signed_file == doc.get("signed_file"):
        raise ValueError("tep %s da dung cho hop dong / dot khac" % signed_file)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_acceptance
    findings = kol_acceptance.finish_round(doc, row, signed_file, now_datetime(), ESIGN_ACTOR)
    return {"changed": True, "status": row.status, "due_date": str(row.due_date or ""), "findings": findings}
