# Copyright (c) 2026, eCentric and contributors
"""Ban XEM TRUOC hop dong KOL/KOC tu du lieu DANG GO tren form (PO 12/11/2026).

Gia tri ERP dien to vang, cho con thieu to do. KHONG ghi gi: khong luu phieu, khong dinh kem
tep, khong cap so. Tep tai ve / gui ky van la tep generate_contract sinh ra (khong to mau).

Bao ve (QC6):
  * Phieu da luu: chi nguoi quan ly phieu xem truoc duoc.
  * Thong tin ca nhan creator (CCCD, ngay sinh, dia chi, STK, SDT, email, MST): nguoi khong
    duoc xem ban day du cua creator (khong phai nguoi tao creator / Ke toan) thay "da co, an".
  * Tep lam sach truoc khi ve tren trinh duyet (docx_safe): mau chua the HTML / link javascript
    khong chay duoc trong phien nguoi xem.
  * Moi loi tra cau tieng Viet, khong lo duong dan tep / traceback.
"""
import base64
import json
import re

import frappe
from frappe import _

from ecentric_workspace.approval_center.features.contract_review.application import kol_files, kol_lookup
from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
    can_manage, creator_row)
from ecentric_workspace.approval_center.features.contract_review.domain import docx_fill, docx_safe, kol, kol_values

# Ten <<...>> mang thong tin ca nhan creator - an khi nguoi xem khong co quyen xem ban day du.
PII_PLACEHOLDERS = ("PERSON_ID_NO", "PERSON_DOB", "PERSON_EMAIL", "PERSON_PHONE", "PERSON_ID_ISSUE_DATE",
                    "PERSON_ID_ISSUE_PLACE", "PARTY_ADDRESS", "PARTY_TAX_ID", "BANK_ACCOUNT_NO",
                    "BANK_NAME_BRANCH", "BANK_ACCOUNT_HOLDER")
MASK = "••• (đã có, ẩn)"
_BAD_TEMPLATE = "Mẫu hợp đồng lỗi định dạng, chưa xem trước được. Nhờ Kế toán kiểm tra lại mẫu."


def parse_fields(raw):
    """Du lieu form gui len (chuoi JSON hoac dict) -> dict; sai dang -> {}."""
    if isinstance(raw, dict):
        return raw
    try:
        val = json.loads(raw or "{}")
    except (TypeError, ValueError):
        return {}
    return val if isinstance(val, dict) else {}


def _plain(text):
    return re.sub(r"<[^>]+>", "", text or "").strip()


def _fail(msg):
    return {"ok": False, "error": msg}


def _load(name, user):
    from ecentric_workspace.approval_center.features.contract_review.domain.definition import (
        CONTRACT_REVIEW_DEFINITION)
    if name:
        if not frappe.db.exists(kol_lookup.CR_DT, name):
            return None, _fail(_("Không tìm thấy phiếu {0}.").format(name))
        doc = frappe.get_doc(kol_lookup.CR_DT, name)
        if not can_manage(doc, user):
            frappe.throw(_("Bạn không xem trước được hợp đồng của phiếu này."), frappe.PermissionError)
    else:
        doc = frappe.new_doc(kol_lookup.CR_DT)
    return doc, set(CONTRACT_REVIEW_DEFINITION.editable_fields)


def _can_see_pii(user, creator):
    from ecentric_workspace.approval_center.shared.creators.service import CreatorService
    try:
        return bool(CreatorService().can_see_pii(user, creator))
    except Exception:
        return False


def preview_contract(fields, name, user):
    """-> {"ok": True, "docx": base64, ...} hoac {"ok": False, "error": cau tieng Viet}."""
    from ecentric_workspace.approval_center.features.contract_review.application import kol_service
    doc, allowed = _load(name, user)
    if doc is None:
        return allowed
    for k, v in (fields or {}).items():
        if k in allowed:
            doc.set(k, v)
    if not kol.is_kol(doc):
        return _fail(_("Chỉ hợp đồng KOL/KOC có bản xem trước từ mẫu."))
    if doc.get("request_type") != kol.TEMPLATE_EC:
        return _fail(_("Phiếu dùng mẫu của creator: mở tệp đã tải lên để xem."))
    try:
        kol_service.prepare_draft(doc)
        errors = kol.validate_kol(doc, doc.get("creator_type"), kol_service.ref_day(doc))
        if errors:
            return _fail(" ".join(errors))
        kol_service.apply_amounts(doc, strict=True)
        creator = creator_row(doc.get("creator"))
        if not creator:
            return _fail(_("Chọn creator để xem trước hợp đồng."))
        kol_service.assign_number(doc, creator)
        tpl = frappe.get_doc("EC Contract Template", kol_files.template_for(doc, kol_files.KIND_CONTRACT))
    except frappe.PermissionError:
        raise
    except (frappe.ValidationError, ValueError) as e:
        return _fail(_plain(str(e)) or _("Chưa đủ thông tin để xem trước."))
    try:
        values = kol_files._values(doc, creator, kol_service.expected_bbnt_date(doc))
        data = kol_files.file_bytes(tpl.template_file)
        _content, missing = kol_files._fill(data, values, doc)
        shown = {k: v for k, v in values.items() if k not in set(missing)}
        if not _can_see_pii(user, creator):
            shown.update({k: MASK for k in PII_PLACEHOLDERS if str(shown.get(k) or "").strip()})
        content, _m = docx_fill.fill_docx(
            data, shown, kol_values.CONDITIONAL_LINES, mark=True,
            missing_text=lambda k: "[Thiếu: %s]" % (kol_values.LABELS.get(k) or k))
        content = docx_safe.sanitize_for_viewer(content)
    except Exception:
        # Mau hong (khong phai zip / XML loi / tep mat tren dia): ghi Error Log, bao cau tieng Viet,
        # khong lo duong dan tep rieng.
        frappe.log_error(frappe.get_traceback(), "kol_preview_contract")
        return _fail(_(_BAD_TEMPLATE))
    return {"ok": True, "docx": base64.b64encode(content).decode("ascii"), "template": tpl.name,
            "template_title": tpl.get("template_name") or tpl.name, "contract_no": doc.get("contract_no"),
            "missing_labels": kol_values.missing_labels(missing)}
