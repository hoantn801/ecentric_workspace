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
def is_generated(file_name_or_url):
    """Tep he thong sinh tu mau (HDDV_ / BBNT_), ca ban SIGNED-/REVIEW- cua no."""
    base = str(file_name_or_url or "").rsplit("/", 1)[-1]
    for pre in ("SIGNED-", "REVIEW-"):
        if base.startswith(pre):
            base = base[len(pre):]
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
    """`business_redactor`: an URL ban du PII khoi chi tiet phieu voi nguoi khong duoc tai."""
    if not kol.is_kol(business) or can_download_full(business, frappe.session.user):
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
    """`attachment_redactor`: bo tep HDDV_ / BBNT_ khoi danh sach dinh kem voi nguoi khong duoc tai."""
    if not kol.is_kol(business) or can_download_full(business, frappe.session.user):
        return attachments
    signed = _signed_urls(business)
    return [a for a in attachments or [] if not is_generated(a.get("file_name") or a.get("file_url"))
            and a.get("file_url") not in signed]


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
                       "Bấm \"Xem trước hợp đồng\" để xem bản đã che."), frappe.PermissionError)
    doc.add_comment("Info", _("{0} tải bản đủ thông tin creator: {1}").format(user, row.file_name))
    return row.file_name, frappe.get_doc("File", row.name).get_content()


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
    fp = payee_fp(kol_service.creator_row(doc.get("creator")))
    if not fp or not payee_changed(doc):
        return {"ok": True, "changed": False}
    rows = _approved(doc) + [{"fp": fp, "by": user, "at": str(now_datetime())}]
    frappe.db.set_value(kol_lookup.CR_DT, name, "kol_payee_ok", json.dumps(rows), update_modified=False)
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
