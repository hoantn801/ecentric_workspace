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

"signed" chi nhan khi phieu da duyet xong tren ERP. Ket qua khong thanh nhan o MOI trang thai (ban
thiet ke 2, 12/11 11:49: khoi ky hien tu luc lap phieu, tu choi / tra lai co the den giua luong duyet):
chi ghi vet + dua trang thai ky ve - hop dong ve "Chua ky", dot BBNT ve "Nhap" (THIETKE Q2). Module
nay KHONG mo lai / doi trang thai luong duyet ERP; viec do do luong duyet tu lam.

`package_title(business_name, purpose)`: tieu de tai lieu tren cong (phia Hop dong truyen vao).

Them 23/11/2026 (ban giao chat Ky so, B2 + B6):
  * `verify_document(business_doctype, business_name, file_name, pages_text)` - hook
    ec_esign_document_verifiers: doi chieu lop chu PDF ky voi phieu (so HD + so tien tra creator).
  * `external_handlers(business_name)` - hook ec_esign_external_handlers: nguoi ky phia doi tac
    (creator / nguoi lao dong) cho tai lieu tren cong. Thieu thong tin -> frappe.throw cau tieng Viet
    (Ky so giu nguyen cau do de bao nguoi dung).
Khong whitelist - chi goi tu server.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup, kol_rounds
from ecentric_workspace.approval_center.features.contract_review.domain import esign_flow, kol, sign_pdf_check

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
    # Ky du chi den sau khi ERP duyet xong (CEO ky o cap cuoi, doi tac ky sau). Ket qua KHONG thanh
    # (tu choi / tra lai / huy) co the den GIUA luong duyet (ban thiet ke 2, 12/11 11:49): nhan o moi
    # trang thai, chi ghi vet + dua trang thai ky ve cho lam lai.
    if outcome == SIGNED and approval_status(doc) != APPROVED:
        raise ValueError("phieu %s chua duyet xong tren ERP" % business_name)
    if outcome == SIGNED:
        _check_signed_file(doc, signed_file)
    if purpose == CONTRACT:
        return _contract(doc, outcome, signed_file, detail)
    if str(purpose or "").startswith(BBNT_PREFIX):
        return _round(doc, str(purpose)[len(BBNT_PREFIX):], outcome, signed_file, detail)
    raise ValueError("purpose khong hop le: %r" % (purpose,))


def _check_signed_file(doc, signed_file):
    """Ban ky du phai la tep DA GAN phieu nay va khong phai ban chua ky dem di ky (QC 15/11 B-06:
    phieu thuong khong qua may kiem, truoc do nhan bat ky URL .pdf -> 'Da ky du' ngay)."""
    if signed_file in {doc.get("request_attachment"), doc.get("contract_file"), doc.get("sign_pdf")}:
        raise ValueError("signed_file %s la ban chua ky cua phieu" % signed_file)
    if not frappe.db.exists("File", {"file_url": signed_file, "attached_to_doctype": doc.doctype,
                                     "attached_to_name": doc.name}):
        raise ValueError("signed_file %s chua dinh kem vao phieu %s" % (signed_file, doc.name))


def package_title(business_name, purpose):
    """Tieu de tai lieu tren cong: "HĐ <so HD> - <doi tac>" / "BBNT đợt n - <so HD>"."""
    doc = frappe.get_doc(kol_lookup.CR_DT, business_name)
    no = doc.get("contract_no") or doc.name
    if str(purpose or "").startswith(BBNT_PREFIX):
        row = _find_row(doc, str(purpose)[len(BBNT_PREFIX):])
        return "BBNT đợt %s - %s" % (row.round_no, no)
    who = doc.get("creator_name") or doc.get("partner_signer_name") or doc.get("request_title") or ""
    return ("HĐ %s - %s" % (no, who)).strip(" -")[:140]


#: Viec nguoi lap phai lam tiep theo tung ket qua khong thanh (B5, ban giao 23/11). "returned": tai lieu
#: tren cong da dung han, khong ky tiep duoc - phai sua roi gui lai (tao tai lieu moi).
_NEXT_STEP = {
    REJECTED: "Xem lý do, sửa hợp đồng rồi gửi lại.",
    RETURNED: "Tài liệu đó không ký tiếp được - sửa theo góp ý rồi gửi lại.",
    DESTROYED: "Tài liệu đã bị huỷ trên cổng - liên hệ Kế toán / quản trị trước khi gửi lại.",
}


def _tell_requester(doc, text):
    """Bao nguoi lap (chuong + Teams theo cai dat cua ho). Loi thong bao KHONG lam hong ket qua ky."""
    to = doc.get("requested_by") or doc.get("owner")
    if not to:
        return
    try:
        from ecentric_workspace.approval_center.shared.workflow import transitions
        transitions.notify([to], text, doc.doctype, doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "contract esign outcome notify %s" % doc.name)


def _why(detail):
    if isinstance(detail, dict):
        detail = detail.get("reason") or detail.get("comment") or detail.get("message") or ""
    return str(detail or "").strip()[:500]


def _contract(doc, outcome, signed_file, detail):
    if outcome != SIGNED:
        if doc.get("signing_status") == kol.SIGN_DONE:
            return {"changed": False, "signing_status": doc.signing_status}
        if doc.get("signing_status") == kol.SIGN_REVIEW:
            # Ban ky (tai tay) dang cho Ke toan kiem: giu nguyen nhu nhanh BBNT, chi ghi vet de Ke toan
            # can nhac (QC 15/11 B-07 - truoc do ve "Chua ky" ma van giu signed_file).
            doc.add_comment("Info", _("{0}: hợp đồng {1}{2} trong khi bản ký tải lên đang chờ Kế toán kiểm "
                                      "- Kế toán xem lại trước khi xác nhận.").format(
                ESIGN_ACTOR, _OUTCOME_TEXT[outcome], (": " + _why(detail)) if _why(detail) else ""))
            return {"changed": False, "signing_status": doc.signing_status}
        doc.signing_status = kol.SIGN_PENDING
        doc.save(ignore_permissions=True)
        doc.add_comment("Info", _("{0}: hợp đồng {1}{2}. Sửa tệp rồi Gửi ký lại.").format(
            ESIGN_ACTOR, _OUTCOME_TEXT[outcome], (": " + _why(detail)) if _why(detail) else ""))
        _tell_requester(doc, _("Hợp đồng {0} {1} trên cổng ký{2}. {3}").format(
            doc.get("contract_no") or doc.name, _OUTCOME_TEXT[outcome],
            (": " + _why(detail)) if _why(detail) else "", _NEXT_STEP[outcome]))
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
    """Document dot nghiem thu (EC KOL Acceptance, 24/11) theo ten moi hoac ten dong con cu (legacy_row)."""
    view = kol_rounds.find(doc, row_name)
    if view is None:
        raise ValueError("khong co dot nghiem thu %r tren %s" % (row_name, doc.name))
    return kol_rounds.get(doc, view.name)


def _round(doc, row_name, outcome, signed_file, detail):
    row = _find_row(doc, row_name)
    no = row.round_no
    if row.status in (kol.BBNT_DONE, kol.BBNT_REVIEW):
        return {"changed": False, "status": row.status}
    if outcome != SIGNED:
        if row.status != kol.BBNT_SENT:
            return {"changed": False, "status": row.status}
        if not row.get("approval_request"):
            row.status = kol.BBNT_DRAFT        # dot cu (truoc 24/11): ve Nhap, sua, tao lai BBNT, gui lai
            kol_rounds.save(row)
        # Dot co chuoi duyet rieng (24/11): giu trang thai, chi ghi vet + bao - luong ky so cua phieu dot
        # (C3, hook rieng cho EC KOL Acceptance) se thay nhanh nay.
        doc.add_comment("Info", _("{0}: BBNT đợt {1} {2}{3}.").format(
            ESIGN_ACTOR, no, _OUTCOME_TEXT[outcome], (": " + _why(detail)) if _why(detail) else ""))
        _tell_requester(doc, _("BBNT đợt {0} của hợp đồng {1} {2} trên cổng ký{3}. {4}").format(
            no, doc.get("contract_no") or doc.name, _OUTCOME_TEXT[outcome],
            (": " + _why(detail)) if _why(detail) else "", _NEXT_STEP[outcome]))
        return {"changed": True, "status": row.status}
    # Cung chot nhu tai tay (complete_acceptance): da qua buoc gui duyet (kiem thieu + tao lai BBNT),
    # dot da duyet xong neu co chuoi duyet, hop dong da ky du, tep khong trung hop dong / dot khac (QC7).
    if row.status != kol.BBNT_SENT:
        raise ValueError("dot %s chua qua buoc gui duyet (trang thai %s)" % (no, row.status))
    if row.get("approval_request") and frappe.db.get_value(
            "EC Approval Request", row.approval_request, "approval_status") != "Approved":
        raise ValueError("dot %s chua duyet xong tren ERP" % no)
    from ecentric_workspace.approval_center.features.contract_review.application.kol_service import is_signed
    if not is_signed(doc):
        raise ValueError("hop dong %s chua ky du" % doc.name)
    used = {r.signed_file for r in kol_rounds.rows(doc) if r.name != row.name and r.signed_file}
    if signed_file in used or signed_file == doc.get("signed_file"):
        raise ValueError("tep %s da dung cho hop dong / dot khac" % signed_file)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_acceptance
    findings = kol_acceptance.finish_round(doc, row, signed_file, now_datetime(), ESIGN_ACTOR)
    return {"changed": True, "status": row.status, "due_date": str(row.due_date or ""), "findings": findings}


# ----------------------------------------------------------------------------- B2: doi chieu tep ky
def verify_document(business_doctype, business_name, file_name, pages_text):
    """Hook ec_esign_document_verifiers. -> {"status": match|mismatch|no_text|not_applicable, "reason"}.
    Nen tang LUON goi (PR-G 24/11): PDF khong lop chu -> pages_text = []. Nem loi / tra trang thai
    khong qua -> Ky so chan (dung y: khong doan)."""
    doc = frappe.get_doc(kol_lookup.CR_DT, business_name)
    if not kol.is_kol(doc):
        # Hop dong thuong: van ban do doi tac / phong ban soan (co the la ban scan doi tac da ky - WF05),
        # khong co du lieu doi chieu tren phieu -> "khong ap dung" = qua, nguoi lap keo o ky tay.
        return {"status": "not_applicable",
                "reason": _("Hợp đồng không phải KOL/KOC - không đối chiếu tự động.")}
    text = "\n".join(str(p or "") for p in (pages_text or []))
    if not text.strip():
        return {"status": "no_text", "reason": None}
    from ecentric_workspace.approval_center.features.contract_review.application.kol_ai import number_tokens
    payable = kol.printed_digits(doc.get("payable_amount"))
    problems = sign_pdf_check.findings(
        text, number_tokens(text), doc.get("contract_no"), payable,
        # Mau cua creator: van ban creator soan, khong mang so HD cua ERP.
        check_contract_no=doc.get("request_type") != kol.TEMPLATE_PARTNER)
    if problems:
        return {"status": "mismatch", "reason": " ".join(problems)}
    return {"status": "match", "reason": None}


# ----------------------------------------------------------------------------- PR-H: tep ky do nghiep vu khai
def signing_files(business_name):
    """Hook ec_esign_signing_files (PR-G 24/11) -> [file_url]: DUY NHAT cac tep nay la tai lieu ky.

    * KOL: chi "Ban PDF de ky" (sign_pdf). Ban .docx sinh tu mau, dinh kem, ban ky cu = bo chung tu.
    * Hop dong thuong: [] - chua chot tep ky voi PO; ho so ky dau tien chi ap cho KOL (chat Ky so dong
      y 24/11). Bat ho so cho hop dong thuong ma van tra rong -> nen tang chan khoa goi (CO Y)."""
    doc = frappe.get_doc(kol_lookup.CR_DT, business_name)
    if not kol.is_kol(doc):
        return []
    url = doc.get("sign_pdf")
    return [url] if url else []


# ----------------------------------------------------------------------------- B6: doi tac ky tren cong
def external_handlers(business_name):
    """Hook ec_esign_external_handlers -> [{full_name, email, phone?, identity, identity_place?,
    identity_date?, dob?}]. Lay tu o "Nguoi ky phia doi tac" cua phieu (luc gui da kiem bang
    kol_service.partner_signer_errors + esign_gate). KHONG dat sign_type: Ky so dat mac dinh (eKYC).

    `identity` LUON co (CMC bat buoc CCCD / MST doi tac - chat Ky so 24/11): xem
    kol_service.partner_identity (o nhap tay > CCCD creator ca nhan ky chinh minh > MST cong ty / ho
    kinh doanh). Thieu -> nem loi ro rang thay vi gui cong roi bi CMC tu choi. Ngay dd/mm/yyyy nhu tren
    hop dong. Khong ghi log gia tri nao (PII)."""
    doc = frappe.get_doc(kol_lookup.CR_DT, business_name)
    if not esign_flow.needs_partner(doc.get("esign_flow")):
        frappe.throw(_("Quy trình ký của phiếu {0} không có đối tác ký trên cổng.").format(business_name))
    from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
        partner_identity, partner_signer_errors)
    errors = partner_signer_errors(doc)
    if errors:
        frappe.throw(errors[0])
    ident, err = partner_identity(doc)
    if err:
        frappe.throw(err)
    row = {"full_name": (doc.get("partner_signer_name") or "").strip(),
           "email": (doc.get("partner_signer_email") or "").strip()}
    phone = (doc.get("partner_signer_phone") or "").strip()
    if phone:
        row["phone"] = phone
    row.update(ident)
    return [row]

