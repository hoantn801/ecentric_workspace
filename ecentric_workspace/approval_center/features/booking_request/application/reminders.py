# Copyright (c) 2026, eCentric and contributors
"""Nhac Booking theo NGAY DU KIEN XU LY XONG: tu D-3 toi khi hoan tat (11/09, Hoan).

Vi sao can mot job rieng: engine chi ban thong bao theo SU KIEN (duyet xong, nhan viec,
hoan tat). "Sap toi han" khong phai su kien - no la mot NGAY, nen chi phat hien duoc bang
cach quet moi ngay.

Moc nhac la ngay CHINH ban Booking cam ket luc nhan viec, khong phai ngay hoat dong bat dau.
Do la lua chon co y: nhac theo cam ket cua chinh minh thi con nhac duoc; nhac theo mot moc
ma nguoi nhan khong dat ra thi chi la tieng on.

Luat:
  - Phieu Assigned / In Progress, co `fulfillment_expected_date` <= hom nay + REMIND_DAYS_BEFORE.
  - Moi phieu MOT lan moi ngay (`booking_reminded_on`), ke ca khi da qua han.
  - Gui cho nguoi da nhan; chua ai nhan thi gui ca nhom Fulfiller.
  - Loi mot phieu khong chan phieu khac; tat bang site_config `ec_booking_reminder_disabled`.
"""
import frappe
from frappe import _
from frappe.utils import add_days, formatdate, getdate

from ecentric_workspace.approval_center.features.booking_request.application.service import (
    BUSINESS_DT, _ca_nhom_booking)
from ecentric_workspace.approval_center.shared.workflow import transitions as engine

REMIND_DAYS_BEFORE = 3
_ACTIVE = ("Assigned", "In Progress")


def _truong(row, key):
    """Doc mot truong du `row` la dict, frappe._dict hay Document.

    Khong dung `hasattr(row, "get")` roi tra None im lang cho truong hop con lai: "khong doc
    duoc" va "khong co gia tri" la hai chuyen khac nhau, va gop chung lai thi mot phep loc se
    bo qua ca danh sach ma khong ai biet (bai hoc tu reminders cua Payment Request)."""
    if isinstance(row, dict):
        return row.get(key)
    return getattr(row, key, None)


def _nguoi_nhan(doc):
    if doc.fulfillment_status == "In Progress" and doc.fulfillment_owner:
        return [doc.fulfillment_owner]
    return _ca_nhom_booking(doc)


def _tieu_de(doc, hom_nay):
    moc = getdate(_truong(doc, "fulfillment_expected_date"))
    con = (moc - hom_nay).days
    if con > 0:
        khi = _("còn {0} ngày").format(con)
    elif con == 0:
        khi = _("HÔM NAY")
    else:
        khi = _("QUÁ HẠN {0} ngày").format(-con)
    bat_dau = _truong(doc, "campaign_start_date")
    return _("Nhắc xử lý booking — dự kiến xong {0} ({1}){2}: {3}").format(
        formatdate(moc), khi,
        _(" · hoạt động bắt đầu {0}").format(formatdate(bat_dau)) if bat_dau else "",
        engine.request_label(BUSINESS_DT, doc.name))


def due_candidates(today=None):
    """Phieu can nhac hom nay (chua nhac hom nay).

    Loc `booking_reminded_on` o PYTHON chu khong o SQL: `!= today` trong SQL bo qua NULL,
    tuc bo qua dung nhung phieu CHUA NHAC LAN NAO - dung tap can nhac nhat."""
    hom_nay = getdate(today)
    han = add_days(hom_nay, REMIND_DAYS_BEFORE)
    rows = frappe.get_all(BUSINESS_DT,
                          filters={"fulfillment_status": ["in", list(_ACTIVE)]},
                          fields=["name", "booking_reminded_on", "fulfillment_expected_date"],
                          limit_page_length=500)
    out = []
    for r in rows:
        moc = _truong(r, "fulfillment_expected_date")
        if not moc or getdate(moc) > getdate(han):
            continue
        if r.booking_reminded_on and getdate(r.booking_reminded_on) == hom_nay:
            continue
        out.append(r.name)
    return out


def remind_booking_due(today=None):
    """Scheduler daily. Tra ve so phieu da nhac (de test/verify)."""
    if frappe.conf.get("ec_booking_reminder_disabled"):
        return 0
    hom_nay = getdate(today)
    da_nhac = 0
    for name in due_candidates(hom_nay):
        try:
            doc = frappe.get_doc(BUSINESS_DT, name)
            users = [u for u in _nguoi_nhan(doc) if u]
            if users:
                engine.notify(users, _tieu_de(doc, hom_nay), BUSINESS_DT, name)
            frappe.db.set_value(BUSINESS_DT, name, "booking_reminded_on", hom_nay,
                                update_modified=False)
            da_nhac += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), "booking_request.remind_booking_due %s" % name)
    return da_nhac
