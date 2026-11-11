# Copyright (c) 2026, eCentric and contributors
"""AI cho hop dong KOL/KOC: doc mau cua creator de goi y truong, va AI QC truoc khi duyet.

Moi lan goi AI di qua cong chung `platform.ai.gateway.generate` (mot cho cam khoa, model du
phong, ghi chi phi) - khong gan khoa rieng (anh Hoan 28/09).

AI QC = 4 phep kiem anh Hoan chot 11/11:
  1. Khop so lieu form <-> tep  : so so tien / CCCD / MST / STK bang MAY (tim chuoi trong van
                                  ban), khong hoi AI - may khong doan.
  2. So voi mau chuan           : AI doc tep + mau EC (neu co) va liet ke dieu khoan bi bo/sua.
  3. Co dieu khoan rui ro       : AI.
  4. Tep ky duoc khong          : MAY (dung .docx/.pdf, khong ReportLab, khong anh doi duoi).
Truoc khi gui van ban cho AI, cac day so dinh danh (CCCD, MST, STK, SDT) bi che bang may.
PDF cung vay: rut chu bang pypdf roi che, KHONG gui nguyen tep (QC 11/11: gui tep PDF = CCCD /
STK ra ngoai). PDF dang anh (khong rut duoc chu) thi khong gui AI, bao nguoi dung tu xem.
"""
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.application.kol_files import (
    doc_file_bytes, file_bytes)
from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
    can_manage, creator_row)
from ecentric_workspace.approval_center.features.contract_review.domain import docx_fill, kol

QC_PASS, QC_REVIEW, QC_ERROR = "Đạt", "Cần xem", "Lỗi"
MAX_TEXT = 40000

EXTRACT_SCHEMA = {"type": "object", "properties": {
    "creator_name": {"type": "string"}, "creator_kind": {"type": "string"},
    "address": {"type": "string"}, "email": {"type": "string"},
    "bank_name": {"type": "string"}, "service_type": {"type": "string"},
    "platform": {"type": "string"}, "quantity": {"type": "integer"},
    "duration": {"type": "string"}, "air_dates": {"type": "string"},
    "amount": {"type": "number"}, "amount_basis": {"type": "string"},
    "advance_percent": {"type": "number"}, "start_date": {"type": "string"},
    "end_date": {"type": "string"}, "notes": {"type": "string"}},
    "required": ["creator_name"]}

QC_SCHEMA = {"type": "object", "properties": {
    "template_deviations": {"type": "array", "items": {"type": "string"}},
    "risky_clauses": {"type": "array", "items": {"type": "object", "properties": {
        "clause": {"type": "string"}, "risk": {"type": "string"},
        "severity": {"type": "string"}}}},
    "summary": {"type": "string"}},
    "required": ["template_deviations", "risky_clauses", "summary"]}


# Day so co the co dau cach / cham / gach / gach cheo / khoang trang khong ngat giua cac nhom.
_NUMBER_RUN = re.compile(r"(?<![\d])\d(?:[\d]|[ \u00a0.\-/](?=\d))*")
# Tien viet kieu 1.000.000 / 1,000,000: GIU (AI can doc so tien), khong phai so dinh danh.
_MONEY = re.compile(r"^\d{1,3}(?:[.,]\d{3})+$")
_DATE = re.compile(r"^\d{1,2}[/.\-]\d{1,2}[/.\-]\d{4}$")
MIN_ID_DIGITS = 8


def redact(text):
    """Che day so dinh danh (CCCD, MST, STK, SDT >= 8 chu so) truoc khi gui ra ngoai."""
    def sub(m):
        token = m.group(0)
        if _DATE.match(token):
            return token
        # Tien: nhom nghin, khong bat dau bang 0 (CCCD / STK hay co so 0 dau), duoi 100 ty.
        if _MONEY.match(token) and token[0] != "0" and len(re.sub(r"\D", "", token)) <= 11:
            return token
        return "[SỐ-ĐÃ-CHE]" if len(re.sub(r"\D", "", token)) >= MIN_ID_DIGITS else token
    return _NUMBER_RUN.sub(sub, text or "")


def _digits(v):
    return re.sub(r"\D", "", str(v or ""))


def number_tokens(text):
    """Moi con so trong van ban (da bo dau phan cach) - so khop NGUYEN con so, khong noi chuoi."""
    return {_digits(m.group(0)) for m in _NUMBER_RUN.finditer(text or "")}


def data_checks(text, doc, creator):
    """Phep kiem 1 bang may: moi gia tri form phai xuat hien NGUYEN VEN trong van ban hop dong.
    (Truoc 11/11 so tren chuoi chu so noi lien ca van ban: 5.000.000 'khop' voi 15.000.000.)"""
    tokens = number_tokens(text)
    norm_text = re.sub(r"\s+", " ", text or "").lower()
    out = []

    def need(label, value, digits=True):
        if not value:
            return
        if digits:
            ok = _digits(value) in tokens
        else:
            ok = re.sub(r"\s+", " ", str(value)).lower() in norm_text
        out.append({"field": label, "value_present": ok})

    need("Số tiền trả creator", int(round(float(doc.get("payable_amount") or 0))) or None)
    need("Số hợp đồng", doc.get("contract_no"), digits=False)
    need("Tên creator", creator.get("supplier_name"), digits=False)
    need("CCCD", creator.get("ec_cr_cccd"))
    need("MST", creator.get("tax_id"))
    need("Số tài khoản", creator.get("ec_bank_account_no"))
    return out


def pdf_text(data, limit=MAX_TEXT):
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(data))
        return "\n".join((page.extract_text() or "") for page in reader.pages)[:limit].strip()
    except Exception:
        return ""


def signable_check(file_url, data):
    name = (file_url or "").lower()
    if name.endswith(".pdf"):
        if not data.startswith(b"%PDF"):
            return "Tệp đuôi .pdf nhưng không phải PDF (ảnh đổi đuôi?) - cổng ký sẽ nhận rồi im."
        if docx_fill.is_reportlab_pdf(data):
            return "PDF sinh bằng ReportLab - cổng ký SCTS không ký được loại này. In lại ra PDF."
        return ""
    if name.endswith(".docx"):
        return "" if data[:2] == b"PK" else "Tệp đuôi .docx nhưng không đọc được như Word."
    return "Chỉ ký được tệp .docx hoặc .pdf."


def _load(name, user):
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc):
        frappe.throw(_("Phiếu này không phải hợp đồng KOL/KOC."))
    if not (can_manage(doc, user) or _is_approver(doc, user)):
        frappe.throw(_("Bạn không có quyền chạy AI trên phiếu này."), frappe.PermissionError)
    return doc


def _is_approver(doc, user):
    return bool(doc.get("approval_request") and frappe.db.exists(
        "EC Approval Request Approver", {"approval_request": doc.approval_request, "approver": user}))


def _file_payload(doc, file_url):
    """-> (bytes, van ban THO cho may kiem, van ban DA CHE cho AI). Khong bao gio gui tep nguyen."""
    data = doc_file_bytes(doc, file_url)
    if file_url.lower().endswith(".docx"):
        raw = docx_fill.docx_text(data, MAX_TEXT)
    elif file_url.lower().endswith(".pdf"):
        raw = pdf_text(data)
    else:
        frappe.throw(_("AI chỉ đọc được tệp .docx hoặc .pdf."))
    return data, raw, redact(raw)


NO_TEXT = ("Tệp PDF dạng ảnh (không có chữ để đọc) - AI không đọc được và không gửi tệp ra "
           "ngoài. Vui lòng kiểm bằng mắt hoặc xin creator bản Word / PDF xuất từ Word.")


def extract_fields(name, user):
    """Doc hop dong theo mau creator -> goi y truong cho nguoi tao dien (KHONG tu ghi)."""
    from ecentric_workspace.platform.ai import gateway
    doc = _load(name, user)
    url = doc.get("request_attachment")
    if not url:
        frappe.throw(_("Tải hợp đồng của creator lên trước."))
    _data, raw, text = _file_payload(doc, url)
    if not raw:
        frappe.throw(_(NO_TEXT))
    prompt = ("Đây là hợp đồng dịch vụ KOL/KOC giữa eCentric và một creator. Trích các thông tin "
              "sau nếu CÓ trong văn bản, thiếu thì để trống, KHÔNG suy đoán: tên creator, loại "
              "(cá nhân/công ty/hộ kinh doanh), địa chỉ, email, ngân hàng, dịch vụ, nền tảng, số "
              "buổi/video, thời lượng, ngày thực hiện, số tiền và số tiền đó là thực nhận/gross/"
              "chưa VAT/đã VAT, tỷ lệ cọc %, ngày bắt đầu/kết thúc (yyyy-mm-dd). Số định danh đã bị "
              "che, đừng điền.\n\n" + text)
    res = gateway.generate(prompt, schema=EXTRACT_SCHEMA, purpose="contract_extract")
    if not res.get("ok"):
        frappe.throw(_("AI chưa đọc được hợp đồng ({0}). Vui lòng nhập tay.").format(res.get("error") or "lỗi"))
    return {"suggestions": res.get("data") or {}, "model": res.get("model")}


def run_qc(name, user):
    from ecentric_workspace.platform.ai import gateway
    doc = _load(name, user)
    url = doc.get("contract_file") or doc.get("request_attachment")
    if not url:
        frappe.throw(_("Chưa có tệp hợp đồng để kiểm."))
    data, raw, text = _file_payload(doc, url)
    creator = creator_row(doc.get("creator")) or {}
    checks = data_checks(raw, doc.as_dict(), creator) if raw else []
    signable = signable_check(url, data)
    template_text = ""
    if doc.get("request_type") == kol.TEMPLATE_PARTNER:
        tpl = kol_lookup.pick_template("Hợp đồng", doc.get("creator_type"), doc.get("service_type"),
                                       doc.get("payment_schedule") == kol.PAY_ADVANCE)
        if tpl:
            tpl_url = frappe.db.get_value("EC Contract Template", tpl, "template_file")
            template_text = redact(docx_fill.docx_text(file_bytes(tpl_url), MAX_TEXT // 2))
    prompt = ("Bạn là chuyên viên pháp chế của eCentric (bên A, bên thuê dịch vụ). Kiểm hợp đồng "
              "dịch vụ KOL/KOC dưới đây. (1) So với MẪU CHUẨN của eCentric (nếu có): liệt kê điều "
              "khoản bị bỏ, bị sửa nghĩa, hoặc thêm mới. (2) Liệt kê điều khoản bất lợi cho eCentric "
              "(phạt vi phạm, thanh toán trước, độc quyền, bồi thường, chấm dứt, sở hữu nội dung, "
              "thuế) với mức Cao/Trung bình/Thấp. Trả lời tiếng Việt, ngắn.\n\n"
              + ("=== MẪU CHUẨN ===\n" + template_text + "\n\n" if template_text else "")
              + "=== HỢP ĐỒNG CẦN KIỂM ===\n" + text)
    if raw:
        res = gateway.generate(prompt, schema=QC_SCHEMA, purpose="contract_qc")
    else:
        res = {"ok": False, "error": NO_TEXT}
    ai = res.get("data") if res.get("ok") else None
    result = {"data_checks": checks, "signable": signable or "OK", "ai": ai,
              "ai_error": None if ai else (res.get("error") or "AI lỗi"), "model": res.get("model")}
    doc.ai_qc_status = qc_status(checks, signable, ai)
    doc.ai_qc_result = json.dumps(result, ensure_ascii=False)
    doc.ai_qc_at = now_datetime()
    doc.save(ignore_permissions=True)
    return {"status": doc.ai_qc_status, "result": result}


def qc_status(checks, signable, ai):
    if signable or any(not c["value_present"] for c in checks):
        return QC_ERROR
    if ai is None or not checks:   # khong doc duoc chu = chua kiem duoc so lieu -> nguoi xem
        return QC_REVIEW
    high = [r for r in (ai.get("risky_clauses") or []) if (r.get("severity") or "").lower().startswith("cao")]
    if high or ai.get("template_deviations"):
        return QC_REVIEW
    return QC_PASS
