# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC - quyet dinh PO 17/11/2026:

* A. Ban hop dong / BBNT DU thong tin ca nhan creator (CCCD, ngay sinh, STK...) chi nguoi tao
  creator + Ke toan tai duoc, moi lan tai ghi vet. Nguoi lap / nguoi duyet xem ban da che
  (kol_preview). Tep van GAN phieu (nen tang ky so lay tep tu day) nhung: chu tep = Administrator,
  ten tep co doan ngau nhien, URL bi an khoi man hinh chi tiet voi nguoi khong duoc tai.
* D. Van tay tai khoan nhan tien (HMAC, khong luu so) chot luc gui duyet. STK creator doi sau do
  -> canh bao; Ke toan xac nhan thi luu van tay moi vao danh sach da duyet cua HOP DONG nay.
* Thanh ly hop dong (Ke toan): khong mo dot BBNT moi -> tran DNTT dung o phan da nghiem thu.
"""
import hashlib
import hmac
import json
import re

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.domain import kol
from ecentric_workspace.approval_center.features.contract_review.domain.kol_texts import strip_accents

GENERATED_PREFIXES = ("HDDV_", "BBNT_")
_SYSTEM_MANAGER = "System Manager"


# ----------------------------------------------------------------------------- A. tai ban du PII
# Ban sinh tu tep goc: "SIGNED-<ten>", "REVIEW-<sha8>-<ten>" (platform/esign/signed_files.py),
# "[Đối chứng] <ten>" (ban doi chung SharePoint) - QC 17/11.
_DERIVED = re.compile(r"^(?:SIGNED-|REVIEW-(?:[0-9a-f]{8}-)?|\[Đối chứng\]\s*)", re.I)


def is_generated(file_name_or_url):
    """Tep he thong sinh tu mau (HDDV_ / BBNT_), ca cac ban sinh tu no (SIGNED- / REVIEW- / doi chung)."""
    base = str(file_name_or_url or "").rsplit("/", 1)[-1]
    while True:
        m = _DERIVED.match(base)
        if not m or not m.end():
            break
        base = base[m.end():]
    return base.startswith(GENERATED_PREFIXES)


def _signed_urls(business):
    """Ban DA KY (hop dong + tung dot BBNT) cung in du CCCD/STK - xu ly nhu ban sinh tu mau."""
    urls = {business.get("signed_file")}
    urls.update(r.get("signed_file") for r in business.get("acceptances") or [])
    urls.discard(None)
    urls.discard("")
    return urls


def is_pii_file(business, file_name_or_url):
    return is_generated(file_name_or_url) or file_name_or_url in _signed_urls(business)


def can_download_full(business, user):
    if user == "Administrator" or _SYSTEM_MANAGER in frappe.get_roles(user) or kol_lookup.is_finance(user):
        return True
    creator = business.get("creator")
    owner = frappe.db.get_value("Supplier", creator, "owner") if creator else None
    return bool(owner) and owner == user


def redact_business(business, request=None):
    """`business_redactor`: an URL ban du PII khoi chi tiet phieu voi nguoi khong duoc tai. Co
    `has_contract_file` / `has_request_attachment` de trang van biet da co tep (nhan nut, buoc)."""
    if not kol.is_kol(business):
        return
    business["has_contract_file"] = bool(business.get("contract_file"))
    business["has_request_attachment"] = bool(business.get("request_attachment"))
    if can_download_full(business, frappe.session.user):
        return
    for field in ("contract_file", "request_attachment"):
        if is_generated(business.get(field)):
            business[field] = None
    if business.get("signed_file"):
        business["signed_file"] = None
    for row in business.get("acceptances") or []:
        if is_generated(row.get("bbnt_file")):
            row["bbnt_file"] = None
        if row.get("signed_file"):
            row["signed_file"] = None


def redact_attachments(attachments, business, request=None):
    """`attachment_redactor` (ca danh sach Dinh kem lan ban doi chung): hop dong KOL thi bo moi tep du
    PII khoi danh sach - KE CA voi nguoi duoc tai: ho tai bang nut tren the KOL (POST, ghi vet), khong
    mo thang URL (QC 17/11 - mo thang thi khong de lai vet). Ban doi chung (docx_file_url / pdf_file_url)
    la ban sao hop dong: an voi nguoi khong duoc tai."""
    if not kol.is_kol(business):
        return attachments
    allowed = can_download_full(business, frappe.session.user)
    signed = _signed_urls(business)
    out = []
    for a in attachments or []:
        if a.get("docx_file_url") or a.get("pdf_file_url"):
            if allowed:
                out.append(a)
            continue
        if is_generated(a.get("file_name")) or is_generated(a.get("file_url")) or a.get("file_url") in signed:
            continue
        out.append(a)
    return out


def download_file(name, file_url, user):
    """Tai ban du PII (POST - ghi vet duoc). -> (ten tep, noi dung)."""
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc) or not is_pii_file(doc, file_url):
        frappe.throw(_("Tệp này không tải qua đây."))
    row = frappe.db.get_value("File", {"file_url": file_url, "attached_to_doctype": doc.doctype,
                                       "attached_to_name": doc.name}, ["name", "file_name"], as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy tệp của phiếu này."))
    if not can_download_full(doc, user):
        frappe.throw(_("Bản đủ thông tin cá nhân creator chỉ người tạo creator hoặc Kế toán tải được. "
                       "Bấm \"Xem hợp đồng (bản đã che)\" để xem."), frappe.PermissionError)
    # Ghi NHAN tep, khong ghi ten tep (ten co doan ngau nhien = mot phan URL; binh luan ai co quyen
    # xem phieu cung doc duoc) - QC 17/11.
    doc.add_comment("Info", _("{0} tải bản đủ thông tin creator: {1}").format(user, _label(doc, file_url)))
    return row.file_name, frappe.get_doc("File", row.name).get_content()


def _label(doc, file_url):
    if file_url == doc.get("contract_file"):
        return _("hợp đồng")
    if file_url == doc.get("signed_file"):
        return _("hợp đồng đã ký")
    for r in doc.get("acceptances") or []:
        if file_url == r.get("bbnt_file"):
            return _("BBNT đợt {0}").format(r.get("idx"))
        if file_url == r.get("signed_file"):
            return _("BBNT đợt {0} đã ký").format(r.get("idx"))
    return _("tệp hợp đồng")


def strip_url(business, result, *fields):
    """Bo URL tep du PII khoi gia tri tra ve cua endpoint voi nguoi khong duoc tai (QC 17/11)."""
    if isinstance(result, dict) and not can_download_full(business, frappe.session.user):
        for f in fields:
            if result.get(f):
                result[f] = None
    return result


# ----------------------------------------------------------------------------- D. tai khoan nhan tien
def _key():
    from frappe.utils.password import get_encryption_key
    return (get_encryption_key() or "").encode()


def payee_fp(creator):
    """Van tay STK + ngan hang (HMAC theo khoa cua site - khong do nguoc ra so). Rong khi chua co STK."""
    creator = creator or {}
    acct = re.sub(r"\D", "", str(creator.get("ec_bank_account_no") or ""))
    if not acct:
        return ""
    bank = re.sub(r"[^a-z0-9]", "", strip_accents(str(creator.get("ec_bank_name") or "")).lower())
    return hmac.new(_key(), ("%s|%s" % (acct, bank)).encode(), hashlib.sha256).hexdigest()[:32]


def _approved(doc):
    try:
        rows = json.loads(doc.get("kol_payee_ok") or "[]")
    except ValueError:
        rows = []
    return [r for r in rows if isinstance(r, dict) and r.get("fp")]


def snapshot_payee(doc, creator):
    """Luc gui / gui lai duyet: chot van tay theo creator HIEN TAI (hop dong vua sinh lai in STK nay)."""
    doc.kol_payee_fp = payee_fp(creator) or None


def payee_changed(doc, creator=None):
    """STK creator hien tai khac luc ky va chua duoc Ke toan xac nhan. Phieu cu chua chot -> khong bao."""
    base = doc.get("kol_payee_fp")
    if not base or not doc.get("creator"):
        return False
    if creator is None:
        from ecentric_workspace.approval_center.features.contract_review.application import kol_service
        creator = kol_service.creator_row(doc.get("creator"))
    now = payee_fp(creator)
    return bool(now) and now != base and now not in {r["fp"] for r in _approved(doc)}


def confirm_payee(name, user):
    """Ke toan xac nhan STK moi cua creator cho hop dong nay - cac dot sau khong canh bao lai."""
    if not kol_lookup.is_finance(user):
        frappe.throw(_("Chỉ Kế toán xác nhận được tài khoản nhận tiền."), frappe.PermissionError)
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_service
    if kol_service.approval_status(doc) != kol_service.APPROVED:
        # Phieu chua duyet xong van in STK cu: dung la Yeu cau bo sung + tao lai hop dong (QC 17/11).
        frappe.throw(_("Phiếu chưa duyệt xong: yêu cầu bổ sung để tạo lại hợp đồng với tài khoản mới."))
    fp = payee_fp(kol_service.creator_row(doc.get("creator")))
    if not fp or not payee_changed(doc):
        return {"ok": True, "changed": False}
    rows = _approved(doc) + [{"fp": fp, "by": user, "at": str(now_datetime())}]
    # Cap nhat modified: mot ban luu cu (dang mo tu truoc) se bi TimestampMismatch thay vi ghi de mat
    # xac nhan (QC 17/11).
    frappe.db.set_value(kol_lookup.CR_DT, name, "kol_payee_ok", json.dumps(rows))
    doc.add_comment("Info", _("{0} xác nhận tài khoản nhận tiền mới của creator (đổi sau khi ký hợp đồng).")
                    .format(user))
    return {"ok": True, "changed": True}


# ----------------------------------------------------------------------------- thanh ly
def is_closed(doc):
    return bool(doc.get("kol_closed_at"))


def close_contract(name, user, reason):
    """Ke toan thanh ly hop dong (creator bo booking...): khong mo / gui dot BBNT moi nua -> tran DNTT
    dung o coc + cac dot da nghiem thu. Khong xoa gi, khong doi so tien da duyet."""
    if not kol_lookup.is_finance(user):
        frappe.throw(_("Chỉ Kế toán thanh lý được hợp đồng."), frappe.PermissionError)
    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("Nhập lý do thanh lý."))
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
        APPROVED, approval_status)
    if not kol.is_kol(doc) or approval_status(doc) != APPROVED:
        frappe.throw(_("Chỉ thanh lý được hợp đồng KOL đã duyệt."))
    if is_closed(doc):
        return {"ok": True, "closed_at": str(doc.kol_closed_at)}
    when = now_datetime()
    frappe.db.set_value(kol_lookup.CR_DT, name, {"kol_closed_at": when, "kol_closed_by": user,
                                                 "kol_close_reason": reason[:500]})
    doc.add_comment("Info", _("{0} thanh lý hợp đồng: {1}").format(user, reason[:500]))
    return {"ok": True, "closed_at": str(when)}


def require_open(doc):
    if is_closed(doc):
        frappe.throw(_("Hợp đồng đã thanh lý - không tạo / gửi đợt nghiệm thu mới."))
