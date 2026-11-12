# Copyright (c) 2026, eCentric and contributors
"""Diem nen tang ky so (platform/esign) goi vao khi MOT goi ky cua phieu Contract Review ky du.

Hop dong giua hai chat (chot 12/11/2026): nen tang ky so KHONG ghi thang vao phieu hop dong; no
goi ham nay, phia Hop dong tu ghi trang thai cua minh. Khong whitelist - chi goi tu server.

    on_signed(business_name, purpose, signed_file, signed_at=None)

    purpose = "contract"          -> ban hop dong ky du (signed_file, signing_status)
              "bbnt:<row.name>"   -> BBNT cua dot nghiem thu <row.name> ky du (trang thai dot, han thanh toan)
    signed_file = file_url cua ban PDF ky du, DA dinh kem vao phieu (nen tang dinh kem).

Goi lai nhieu lan an toan: da ky du / dot da hoan tat thi khong lam gi.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.domain import kol

ESIGN_ACTOR = "Ký số (cổng)"
CONTRACT = "contract"
BBNT_PREFIX = "bbnt:"


def on_signed(business_name, purpose, signed_file, signed_at=None):
    """-> {"changed": bool, ...}. Sai purpose / khong tim thay -> ValueError (nen tang ghi log)."""
    if not signed_file or not str(signed_file).lower().endswith(".pdf"):
        raise ValueError("signed_file phai la PDF da dinh kem")
    doc = frappe.get_doc(kol_lookup.CR_DT, business_name)
    when = signed_at or now_datetime()
    if purpose == CONTRACT:
        return _contract_signed(doc, signed_file, when)
    if str(purpose or "").startswith(BBNT_PREFIX):
        return _round_signed(doc, str(purpose)[len(BBNT_PREFIX):], signed_file, when)
    raise ValueError("purpose khong hop le: %r" % (purpose,))


def _contract_signed(doc, signed_file, when):
    if doc.get("signing_status") == kol.SIGN_DONE:
        return {"changed": False, "signing_status": doc.signing_status}
    doc.signed_file = signed_file
    doc.signed_at = when
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


def _round_signed(doc, row_name, signed_file, when):
    row = next((r for r in (doc.get("acceptances") or []) if r.name == row_name), None)
    if row is None:
        raise ValueError("khong co dot nghiem thu %r tren %s" % (row_name, doc.name))
    if row.status in (kol.BBNT_DONE, kol.BBNT_REVIEW):
        return {"changed": False, "status": row.status}
    from ecentric_workspace.approval_center.features.contract_review.application import kol_acceptance
    findings = kol_acceptance.finish_round(doc, row, signed_file, when, ESIGN_ACTOR)
    return {"changed": True, "status": row.status, "due_date": str(row.due_date or ""), "findings": findings}
