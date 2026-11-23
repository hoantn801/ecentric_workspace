# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC - quyet dinh PO 17/11/2026:

* A. Ban hop dong / BBNT DU thong tin ca nhan creator (CCCD, ngay sinh, STK...) chi nguoi tao
  creator + Ke toan + nguoi lap phieu tai duoc, moi lan tai ghi vet. Nguoi duyet xem ban da che
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
    urls = {business.get("signed_file"), business.get("sign_pdf")}     # sign_pdf: ban PDF de ky (23/11)
    urls.update(r.get("signed_file") for r in business.get("acceptances") or [])
    urls.discard(None)
    urls.discard("")
    return urls


def _system_urls(doc):
    """Tep chu = Administrator gan phieu (ban ky da nhan, ke ca ban bi tra lai)."""
    return set(frappe.get_all("File", filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
                                               "owner": "Administrator"}, pluck="file_url",
                              limit_page_length=0, ignore_permissions=True))


def is_pii_file(business, file_name_or_url):
    return is_generated(file_name_or_url) or file_name_or_url in _signed_urls(business)


def has_kol_files(doc):
    """Phieu da tao hop dong / BBNT KOL (in CCCD, STK creator). Chi dua vao dau vet KOL that (mau da
    dung, van tay, dot BBNT) hoac phieu DANG LUU la KOL: ten tep HDDV_ / BBNT_ tren phieu loai khac
    (vd tep nguoi dung, ban doi chung chu Administrator) khong tinh (QC vong cuoi 17/11)."""
    if doc.get("acceptances") or doc.get("generated_template") or doc.get("contract_fingerprint"):
        return True
    if not doc.get("name") or _is_new(doc):
        return False
    stored = frappe.db.get_value(kol_lookup.CR_DT, doc.name, ["contract_type", "generated_template",
                                                               "contract_fingerprint"], as_dict=True) or {}
    if stored.get("generated_template") or stored.get("contract_fingerprint"):
        return True
    if not kol.is_kol(stored):
        return False
    if is_generated(doc.get("contract_file")):
        return True
    names = frappe.get_all("File", filters={"attached_to_doctype": kol_lookup.CR_DT, "attached_to_name": doc.name,
                                            "owner": "Administrator"}, pluck="file_name", limit_page_length=0,
                           ignore_permissions=True)
    return any(is_generated(n) for n in names or [])


def _is_new(doc):
    fn = getattr(doc, "is_new", None)
    return bool(callable(fn) and fn())


def foreign_generated(doc, file_url):
    """Tep ten HDDV_ / BBNT_ ma KHONG gan phieu nay va khong phai tep nguoi dung vua tai len (chua gan):
    ban sinh tu mau cua phieu khac con sot lai khi "Sao chep" phieu."""
    if not file_url or not is_generated(file_url):
        return False
    rows = frappe.get_all("File", filters={"file_url": file_url},
                          fields=["attached_to_doctype", "attached_to_name", "owner"], limit_page_length=0,
                          ignore_permissions=True)
    is_new = _is_new(doc)
    for r in rows or []:
        if doc.get("name") and not is_new and r.get("attached_to_doctype") == doc.doctype \
                and r.get("attached_to_name") == doc.name:
            return False
        if not r.get("attached_to_name") and r.get("owner") == frappe.session.user:
            return False
    return True


def _partner_upload(business, url):
    """Tep hop dong theo mau CUA CREATOR nguoi lap tai len: khong phai ban he thong sinh, du ten bat dau
    HDDV_ / BBNT_ -> nguoi duyet van xem / tai binh thuong nhu truoc (QC vong cuoi 17/11)."""
    return bool(url) and business.get("request_type") == kol.TEMPLATE_PARTNER \
        and url == business.get("request_attachment") and url != business.get("contract_file")


def lock_pii_files(doc):
    """Moi dong File gan phieu KOL tro toi tep du PII (ban sinh tu mau, ban ky) -> chu = Administrator.
    Goi tu `on_change` cua DocType (sau hook attach_files_to_document). Nuot loi: khong lam hong viec luu."""
    if not kol.is_kol(doc):
        return
    try:
        urls = _signed_urls(doc)
        for f in ("contract_file", "request_attachment"):
            if is_generated(doc.get(f)) and not _partner_upload(doc, doc.get(f)):
                urls.add(doc.get(f))
        for r in doc.get("acceptances") or []:
            if r.get("bbnt_file"):
                urls.add(r.get("bbnt_file"))
        urls.discard(None)
        if not urls:
            return
        rows = frappe.get_all("File", filters={"attached_to_doctype": doc.doctype, "attached_to_name": doc.name,
                                               "file_url": ["in", sorted(urls)], "owner": ["!=", "Administrator"]},
                              pluck="name", limit_page_length=0, ignore_permissions=True)
        for n in rows:
            frappe.db.set_value("File", n, "owner", "Administrator", update_modified=False)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "kol lock_pii_files %s" % doc.get("name"))


def can_download_full(business, user):
    """Nguoi tao creator + Ke toan (PO 17/11 A) + nguoi LAP chinh phieu nay (PO 17/11 sau QC: nguoi lap
    phai gui BBNT / hop dong cho creator ky va xuat PDF len cong ky). Nguoi duyet: ban che."""
    if user == "Administrator" or _SYSTEM_MANAGER in frappe.get_roles(user) or kol_lookup.is_finance(user):
        return True
    # Nguoi lap: chi khi phieu DA GUI (co phieu duyet - de lai vet, khong xoa duoc). Nhap thi xem ban
    # che: khong de "lap nhap chon creator bat ky -> tai CCCD -> huy nhap" (QC 17/11 vong 2).
    if user and business.get("requested_by") == user and business.get("approval_request"):
        return True
    # Ky qua nen tang ky so (23/11, ban giao chat Ky so B1): nguoi lap phai xuat PDF tu ban .docx du
    # thong tin TRUOC khi gui (goi ky khoa luc gui). Chi mo khi phieu co ho so ky so dang bat; moi lan
    # tai luc nhap ghi them Access Log (con lai ca khi xoa nhap - download_file).
    if user and user in {business.get("requested_by"), business.get("owner")} \
            and not business.get("approval_request") \
            and business.get("name") and _esign_enabled(business.get("name")):
        return True
    creator = business.get("creator")
    owner = frappe.db.get_value("Supplier", creator, "owner") if creator else None
    return bool(owner) and owner == user


def _esign_enabled(name):
    from ecentric_workspace.approval_center.features.contract_review.application import esign_gate
    return esign_gate.enabled(name)


def _access_log(doc, file_url, user):
    """Vet tai ban du PII KHONG nam tren phieu (binh luan mat theo khi xoa phieu nhap)."""
    try:
        from frappe.core.doctype.access_log.access_log import make_access_log
        make_access_log(doctype=doc.doctype, document=doc.name, method="kol_download_file",
                        file_type=str(file_url or "").rsplit(".", 1)[-1][:10])
    except Exception:
        frappe.log_error(frappe.get_traceback(), "kol download access log %s" % doc.name)


def redact_business(business, request=None):
    """`business_redactor`: an URL ban du PII khoi chi tiet phieu voi nguoi khong duoc tai. Co
    `has_contract_file` / `has_request_attachment` de trang van biet da co tep (nhan nut, buoc)."""
    if not kol.is_kol(business):
        return
    business["has_contract_file"] = bool(business.get("contract_file"))
    business["has_request_attachment"] = bool(business.get("request_attachment"))
    business["has_sign_pdf"] = bool(business.get("sign_pdf"))
    if can_download_full(business, frappe.session.user):
        return
    business["sign_pdf"] = None
    for field in ("contract_file", "request_attachment"):
        if is_generated(business.get(field)) and not _partner_upload(business, business.get(field)):
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
    sign_url = _approver_sign_pdf(business, frappe.session.user)
    out = []
    for a in attachments or []:
        if sign_url and a.get("file_url") == sign_url:
            # PO 24/11 (cau 4 chat Ky so): nguoi trong luong duyet (KTTH, KTT, CEO) xem / mo duoc ban PDF
            # de ky o khoi Ky so - ho ky chinh tep do. Moi tep PII khac van an.
            out.append(a)
            continue
        if a.get("docx_file_url") or a.get("pdf_file_url"):
            if allowed:
                out.append(a)
            continue
        if a.get("owner") != "Administrator" and _partner_upload(business, a.get("file_url")):
            out.append(a)
            continue
        if _is_pii_attachment(business, a):
            continue
        # Nguoi khong duoc tai: an CA ban PDF nguoi lap xuat tu Word (HDDV_...pdf) va ban SIGNED-/REVIEW-
        # cua cong ky (QC ban do 17/11). Nguoi duoc tai van thay de soat / xoa.
        if not allowed and (is_generated(a.get("file_name")) or is_generated(a.get("file_url"))):
            continue
        out.append(a)
    return out


def _approver_sign_pdf(business, user):
    """URL "Ban PDF de ky" neu `user` nam trong luong duyet phieu nay va phieu ky qua nen tang ky so;
    nguoc lai None. Doc lai tu DB: `business` co the da qua redact_business (sign_pdf = None)."""
    name = business.get("name")
    if not name or not user or user == "Guest":
        return None
    row = frappe.db.get_value(kol_lookup.CR_DT, name, ["sign_pdf", "approval_request"], as_dict=True) or {}
    url, ar = row.get("sign_pdf"), row.get("approval_request")
    if not url or not ar:
        return None
    if not frappe.db.exists("EC Approval Request Approver", {"approval_request": ar, "approver": user}):
        return None
    return url if _esign_enabled(name) else None


def _is_pii_attachment(business, a):
    """Tep du PII tren phieu KOL: tep he thong (chu = Administrator: ban sinh tu mau, ban ky da nhan,
    ca ban ky bi tra lai), ban HDDV_/BBNT_ .docx cu (truoc 17/11 chu la nguoi bam tao), URL dang la ban
    ky. PDF nguoi lap tu xuat tu Word (ten van HDDV_...pdf, chu la nguoi lap) KHONG an: do la ban dua
    len cong ky, nguoi lap / Ke toan can thay de soat / xoa (QC 17/11 vong 2)."""
    url, name = a.get("file_url"), a.get("file_name") or ""
    if a.get("owner") == "Administrator" or url in _signed_urls(business):
        return True
    gen = is_generated(name) or is_generated(url)
    return gen and (str(name or url or "").lower().endswith(".docx") or url in {
        business.get("contract_file"), business.get("request_attachment")} or url in {
        r.get("bbnt_file") for r in business.get("acceptances") or []})


def download_file(name, file_url, user):
    """Tai ban du PII (POST - ghi vet duoc). -> (ten tep, noi dung)."""
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc) or not (is_pii_file(doc, file_url) or file_url in _system_urls(doc)):
        frappe.throw(_("Tệp này không tải qua đây."))
    row = frappe.db.get_value("File", {"file_url": file_url, "attached_to_doctype": doc.doctype,
                                       "attached_to_name": doc.name}, ["name", "file_name"], as_dict=True)
    if not row:
        frappe.throw(_("Không tìm thấy tệp của phiếu này."))
    if not can_download_full(doc, user) or not _can_view(doc, user):
        frappe.throw(_("Chỉ người lập phiếu (sau khi gửi), người tạo creator hoặc Kế toán tải được bản đủ thông "
                       "tin creator. Người duyệt xem bản che bằng nút \"Xem hợp đồng\"."), frappe.PermissionError)
    # Ghi NHAN tep, khong ghi ten tep (ten co doan ngau nhien = mot phan URL; binh luan ai co quyen
    # xem phieu cung doc duoc) - QC 17/11.
    doc.add_comment("Info", _("{0} tải bản đủ thông tin creator: {1}").format(user, _label(doc, file_url)))
    if not doc.get("approval_request"):
        _access_log(doc, file_url, user)
    return row.file_name, frappe.get_doc("File", row.name).get_content()


def _can_view(doc, user):
    """Phai xem duoc phieu (Ke toan / SM luon duoc) - nguoi tao creator khong lien quan toi phieu thi
    khong tai qua URL doan duoc (QC ban do 17/11)."""
    if user == "Administrator" or kol_lookup.is_finance(user):
        return True
    from ecentric_workspace.approval_center.shared.requests import capabilities
    req = frappe.db.get_value("EC Approval Request", doc.get("approval_request"), ["name", "approval_status"],
                              as_dict=True) if doc.get("approval_request") else None
    return bool(capabilities.can_view(user, doc, req))


def _label(doc, file_url):
    if file_url == doc.get("contract_file"):
        return _("hợp đồng")
    if file_url == doc.get("signed_file"):
        return _("hợp đồng đã ký")
    if file_url == doc.get("sign_pdf"):
        return _("bản PDF để ký")
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


#: Moc "luc gui creator CHUA CO STK": STK them sau do cung phai Ke toan xac nhan (QC vong 4 17/11).
NO_ACCOUNT = "-"


def snapshot_payee(doc, creator):
    """Luc gui / gui lai duyet: chot van tay theo creator HIEN TAI (hop dong vua sinh lai in STK nay)."""
    doc.kol_payee_fp = payee_fp(creator) or NO_ACCOUNT


def payee_changed(doc, creator=None):
    """STK creator hien tai khac luc ky va chua duoc Ke toan xac nhan. Phieu cu chua chot -> khong bao."""
    base = doc.get("kol_payee_fp")
    if not base or not doc.get("creator"):
        return False
    if creator is None:
        from ecentric_workspace.approval_center.features.contract_review.application import kol_service
        creator = kol_service.creator_row(doc.get("creator"))
    now = payee_fp(creator) or NO_ACCOUNT
    # STK bi XOA sau khi ky cung la "doi" (QC ban do 17/11); STK THEM sau khi gui (luc gui chua co) cung
    # la "doi" (QC vong 4).
    return now != base and now not in {r["fp"] for r in _approved(doc)}


_PAYEE_NOTE = "Đổi thông tin nhận tiền"     # binh luan creators.service.update ghi tren Supplier


def payee_changers(doc):
    """Nguoi da doi STK creator tu luc chot van tay (gui phieu / lan Ke toan xac nhan gan nhat). Doc tu
    binh luan "Đổi thông tin nhận tiền" tren Supplier (creators.service.update ghi); sua tren Desk khong
    co binh luan -> lay nguoi sua Supplier cuoi neu sua sau moc (QC 18/11 tach nhiem vu)."""
    creator = doc.get("creator")
    if not creator:
        return set()
    marks = [str(doc.get("submitted_at") or "")] + [str(r.get("at") or "") for r in _approved(doc)]
    since = max(m for m in marks if m) if any(marks) else ""
    filters = {"reference_doctype": "Supplier", "reference_name": creator, "comment_type": "Info",
               "content": ["like", _PAYEE_NOTE + "%"]}
    if since:
        filters["creation"] = [">", since]
    rows = frappe.get_all("Comment", filters=filters, fields=["owner", "comment_email"], limit_page_length=0)
    users = {r.get("comment_email") or r.get("owner") for r in rows or []}
    if not users:
        mod = frappe.db.get_value("Supplier", creator, ["modified_by", "modified"], as_dict=True) or {}
        if mod.get("modified_by") and (not since or str(mod.get("modified") or "") > since):
            users.add(mod.get("modified_by"))
    return {u for u in users if u}


def can_confirm_payee(doc, user):
    return bool(kol_lookup.is_finance(user) and user not in
                payee_changers(doc) | {doc.get("requested_by"), doc.get("owner")})


def confirm_payee(name, user):
    """Ke toan xac nhan STK moi cua creator cho hop dong nay - cac dot sau khong canh bao lai."""
    if not kol_lookup.is_finance(user):
        frappe.throw(_("Chỉ Kế toán xác nhận được tài khoản nhận tiền."), frappe.PermissionError)
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc):
        frappe.throw(_("Phiếu này không phải hợp đồng KOL/KOC."))
    changers = payee_changers(doc)
    if user in changers | {doc.get("requested_by"), doc.get("owner")}:
        # Tach nhiem vu (QC 18/11): nguoi doi noi nhan tien / nguoi lap phieu khong tu duyet thay doi do.
        frappe.throw(_("Bạn là người đổi tài khoản nhận tiền / người lập phiếu nên không tự xác nhận được. "
                       "Nhờ một Kế toán khác kiểm."), frappe.PermissionError)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_service
    if kol_service.approval_status(doc) != kol_service.APPROVED:
        # Phieu chua duyet xong van in STK cu: dung la Yeu cau bo sung + tao lai hop dong (QC 17/11).
        frappe.throw(_("Phiếu chưa duyệt xong: yêu cầu bổ sung để tạo lại hợp đồng với tài khoản mới."))
    fp = payee_fp(kol_service.creator_row(doc.get("creator")))
    if not fp and doc.get("kol_payee_fp"):
        frappe.throw(_("Creator chưa có số tài khoản: bổ sung thông tin creator trước khi xác nhận."))
    if not fp or not payee_changed(doc):
        return {"ok": True, "changed": False}
    # Khoa dong (for_update): hai Ke toan xac nhan cung luc khong lam mat mot van tay (QC he thong 17/11).
    cur = frappe.db.get_value(kol_lookup.CR_DT, name, "kol_payee_ok", for_update=True)
    rows = _approved({"kol_payee_ok": cur}) + [{"fp": fp, "by": user, "at": str(now_datetime())}]
    # Cap nhat modified: mot ban luu cu (dang mo tu truoc) se bi TimestampMismatch thay vi ghi de mat
    # xac nhan (QC 17/11).
    frappe.db.set_value(kol_lookup.CR_DT, name, "kol_payee_ok", json.dumps(rows))
    doc.add_comment("Info", _("{0} xác nhận tài khoản nhận tiền mới của creator (đổi sau khi ký hợp đồng; người "
                              "đổi: {1}).").format(user, ", ".join(sorted(changers)) or "-"))
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


def reopen_contract(name, user, reason):
    """Mo lai hop dong thanh ly nham (Ke toan, bat buoc ly do, ghi binh luan) - QC ban do 17/11."""
    if not kol_lookup.is_finance(user):
        frappe.throw(_("Chỉ Kế toán mở lại được hợp đồng."), frappe.PermissionError)
    reason = str(reason or "").strip()
    if not reason:
        frappe.throw(_("Nhập lý do mở lại."))
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not is_closed(doc):
        return {"ok": True}
    if user in {doc.get("requested_by"), doc.get("owner")}:
        # Mo lai = mo lai tran chi: nguoi lap phieu khong tu mo (QC 18/11 tach nhiem vu).
        frappe.throw(_("Bạn là người lập phiếu nên không tự mở lại được. Nhờ một Kế toán khác."),
                     frappe.PermissionError)
    frappe.db.set_value(kol_lookup.CR_DT, name, {"kol_closed_at": None, "kol_closed_by": None,
                                                 "kol_close_reason": None})
    doc.add_comment("Info", _("{0} mở lại hợp đồng đã thanh lý ({1}): {2}").format(
        user, doc.get("kol_close_reason") or "", reason[:500]))
    return {"ok": True}


def require_open(doc):
    if is_closed(doc):
        frappe.throw(_("Hợp đồng đã thanh lý - không tạo / gửi đợt nghiệm thu mới."))
