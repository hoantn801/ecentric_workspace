# Copyright (c) 2026, eCentric and contributors
"""Cua noi form 27 voi nen tang ky so (platform/esign) - B4 trong ban giao chat Ky so 23/11/2026.

Moi cho phia Hop dong can biet "phieu nay co ky so tren cong khong" va moi lan goi vao nen tang luc
gui duyet di qua DAY, de:
  * truoc khi Ky so tao ho so ky cho hop dong tren prod, form 27 chay NGUYEN nhu cu (khong ho so ->
    `enabled()` False -> khong goi gi) - deploy truoc, bat sau;
  * thu tu goi dung hop dong: `requester.assert_ready_to_submit` TRUOC engine.submit (chan som, chua
    ghi gi) va `requester.lock_on_submit` SAU engine.submit trong CUNG giao dich (ho so nguoi lap
    KHONG ky, WF09). Ho so co yeu cau nguoi lap ky -> khong dung luong nay (nen tang co luong rieng).
Khong import code nen tang o muc module: test chi gia lap frappe van nap duoc file nay.
"""
import frappe
from frappe import _

CR_DT = "EC Contract Review Request"
APPROVAL_TYPE = "CONTRACT_REVIEW"


def _guard():
    from ecentric_workspace.platform.esign import guard
    return guard


def profile(name):
    """Ten ho so ky so DANG BAT cho phieu nay (chon theo quy trinh ky cua phieu), hoac None.
    Loi cau hinh (nhieu ho so mo ho) -> nem: khong doan."""
    if not name:
        return None
    return _guard().get_enabled_profile(CR_DT, APPROVAL_TYPE, name)


def enabled(name):
    """True khi phieu ky qua nen tang ky so. Loi bat ky -> False (form chay nhu cu, KHONG chan)."""
    try:
        return bool(profile(name))
    except Exception:
        return False


def requester_signs(name):
    try:
        return bool(_guard().requester_signature_required(CR_DT, APPROVAL_TYPE, name))
    except Exception:
        return False


def before_submit(doc):
    """Goi TRUOC engine.submit / engine.resubmit. Chua co Ban PDF de ky -> bao ro bang loi cua form;
    con lai giao nen tang kiem (o ky du, doi chieu noi dung tep). Khong ky so -> khong lam gi."""
    if not profile(doc.name):
        return False
    # CMC bat buoc CCCD / MST cua doi tac (chat Ky so 24/11): thieu thi bao nguoi lap NGAY luc gui, khong
    # de toi luc nen tang gui cong moi bi tu choi.
    from ecentric_workspace.approval_center.features.contract_review.application import kol_service
    err = kol_service.partner_identity_error(doc)
    if err:
        frappe.throw(err)
    if requester_signs(doc.name):
        return False
    if not doc.get("sign_pdf"):
        frappe.throw(_("Tải \"Bản PDF để ký\" (xuất từ Word: Tệp → Lưu thành PDF) trước khi gửi duyệt."))
    from ecentric_workspace.approval_center.features.contract_review.application import kol_sign_pdf
    if kol_sign_pdf.is_stale(doc):
        frappe.throw(_("Hợp đồng vừa được tạo lại sau khi bạn tải \"Bản PDF để ký\" - tải hợp đồng mới, "
                       "xuất lại PDF rồi tải lên trước khi gửi."))
    from ecentric_workspace.platform.esign import requester
    requester.assert_ready_to_submit(CR_DT, doc.name)
    return True


def after_submit(doc):
    """Goi SAU engine.submit, cung giao dich: khoa goi ky (chot ma bam tep + o ky). Nen tang tu tra
    lai khi goi da khoa (gui lai sau "Can bo sung" ma tep khong doi)."""
    if not profile(doc.name) or requester_signs(doc.name):
        return None
    from ecentric_workspace.platform.esign import requester
    return requester.lock_on_submit(CR_DT, doc.name)
