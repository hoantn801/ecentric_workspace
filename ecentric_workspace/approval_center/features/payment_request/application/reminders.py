# Copyright (c) 2026, eCentric and contributors
"""Nhac Finance xu ly UNC theo NGAY THANH TOAN (07/09, Hoan): tu D-3 toi khi co UNC.

Vi sao can mot job rieng: engine chi ban thong bao theo SU KIEN (duyet xong, nhan viec, hoan
tat). Han la mot NGAY - ngay thanh toan - nen "sap toi han" chi co the phat hien bang cach
quet moi ngay. Nhac viec (Action Center) da xep ToDo theo ngay, nhung do la keo (nguoi dung
phai mo); cai nay la day (thong bao).

Luat:
  - Phieu Assigned / In Progress, payment_date <= hom nay + REMIND_DAYS_BEFORE.
  - Moi phieu MOT lan moi ngay (unc_reminded_on = hom nay), ke ca khi da qua han.
  - Assigned -> moi Fulfiller cua process; In Progress -> nguoi da nhan.
  - Loi mot phieu khong chan phieu khac; tat bang site_config ec_payment_unc_reminder_disabled.
"""
import frappe
from frappe import _
from frappe.utils import add_days, formatdate, getdate

from ecentric_workspace.approval_center.features.payment_request.application.service import (
    BUSINESS_DT, INSTALLMENT, _engine, installments_block)

REMIND_DAYS_BEFORE = 3
#: Dot ke: nhac NGUOI DE NGHI som hon (phieu dot ke con phai qua 5 cap duyet + ky).
NEXT_INSTALLMENT_DAYS_BEFORE = 7
_ACTIVE = ("Assigned", "In Progress")


def _recipients(doc, engine):
    if doc.fulfillment_status == "In Progress" and doc.fulfillment_owner:
        return [doc.fulfillment_owner]
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    if not proc_name:
        return []
    proc = frappe.get_doc("EC Approval Process", proc_name)
    return [u for u, _l in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]


def _subject(doc, today, engine):
    days = (getdate(doc.payment_date) - today).days
    if days > 0:
        when = _("còn {0} ngày").format(days)
    elif days == 0:
        when = _("HÔM NAY")
    else:
        when = _("QUÁ HẠN {0} ngày").format(-days)
    return _("Nhắc xử lý UNC — hạn thanh toán {0} ({1}): {2}").format(
        formatdate(doc.payment_date), when, engine.request_label(BUSINESS_DT, doc.name))


def due_candidates(today=None):
    """Phieu can nhac hom nay (chua nhac hom nay). Loc unc_reminded_on trong Python vi
    `!= today` trong SQL bo qua NULL."""
    today = getdate(today)
    rows = frappe.get_all(BUSINESS_DT,
                          filters={"fulfillment_status": ["in", list(_ACTIVE)],
                                   "payment_date": ["<=", add_days(today, REMIND_DAYS_BEFORE)]},
                          fields=["name", "unc_reminded_on"], limit_page_length=500)
    return [r.name for r in rows if not r.unc_reminded_on or getdate(r.unc_reminded_on) != today]


def remind_unc_due(today=None):
    """Scheduler daily. Tra ve so phieu da nhac (de test/verify)."""
    if frappe.conf.get("ec_payment_unc_reminder_disabled"):
        return 0
    engine = _engine()
    today = getdate(today)
    sent = 0
    for name in due_candidates(today):
        try:
            doc = frappe.get_doc(BUSINESS_DT, name)
            users = _recipients(doc, engine)
            if users:
                engine.notify(users, _subject(doc, today, engine), BUSINESS_DT, name)
            frappe.db.set_value(BUSINESS_DT, name, "unc_reminded_on", today, update_modified=False)
            sent += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "payment_request.remind_unc_due %s" % name)
    return sent


# --------------------------------------------------------------------------- #
# Thanh toan chia dot: nhac nguoi de nghi TAO PHIEU DOT KE tu D-7 truoc ngay du kien (07/09).
# Chi phieu chia dot da chi UNC (Completed), con phan chua chi, co ngay du kien, chua co
# phieu dot ke con hieu luc. Moi phieu mot lan/ngay (next_installment_reminded_on).
# --------------------------------------------------------------------------- #
def next_installment_candidates(today=None):
    today = getdate(today)
    rows = frappe.get_all(BUSINESS_DT,
                          filters={"payment_mode": INSTALLMENT, "fulfillment_status": "Completed",
                                   "next_installment_date": ["<=", add_days(today, NEXT_INSTALLMENT_DAYS_BEFORE)],
                                   "next_installment_amount": [">", 0]},
                          fields=["name", "next_installment_reminded_on"], limit_page_length=500)
    return [r.name for r in rows
            if not r.next_installment_reminded_on or getdate(r.next_installment_reminded_on) != today]


def remind_next_installment(today=None):
    """Scheduler daily. Tra ve so phieu da nhac."""
    if frappe.conf.get("ec_payment_unc_reminder_disabled"):
        return 0
    engine = _engine()
    today = getdate(today)
    sent = 0
    for name in next_installment_candidates(today):
        try:
            doc = frappe.get_doc(BUSINESS_DT, name)
            block = installments_block(doc, None)["installments"] or {}
            if block.get("next_request") or (block.get("remaining_after_this") or 0) <= 0:
                # da tao dot ke (hoac da du) -> khong nhac, khong can nhac lai nua
                frappe.db.set_value(BUSINESS_DT, name, "next_installment_reminded_on", today, update_modified=False)
                continue
            days = (getdate(doc.next_installment_date) - today).days
            when = _("còn {0} ngày").format(days) if days > 0 else (_("HÔM NAY") if days == 0 else _("QUÁ HẠN {0} ngày").format(-days))
            engine.notify([doc.requested_by],
                          _("Sắp tới đợt {0} ({1}, dự kiến {2}) — tạo đề nghị thanh toán đợt kế để kịp duyệt & ký: {3}").format(
                              int(doc.installment_no or 1) + 1, when, formatdate(doc.next_installment_date),
                              engine.request_label(BUSINESS_DT, name)),
                          BUSINESS_DT, name)
            frappe.db.set_value(BUSINESS_DT, name, "next_installment_reminded_on", today, update_modified=False)
            sent += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "payment_request.remind_next_installment %s" % name)
    return sent
