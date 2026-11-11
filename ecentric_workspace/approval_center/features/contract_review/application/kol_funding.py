# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC lam "nguon chi phi" cua DNTT - cac ham `funding._SOURCES` goi theo ten.

Giu o module hop dong (khong o payment_request): quy tac tran chi la cua hop dong. Payment
request chi biet "nguon nay co ham tinh tong / ham xet da duyet", khong biet BBNT la gi.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.features.contract_review.application import (
    kol_acceptance, kol_lookup)
from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
    APPROVED, approval_status, is_signed)
from ecentric_workspace.approval_center.features.contract_review.domain import kol

KOL_EXPENSE_CATEGORY = "TT_KOL"


def _doc(name):
    return frappe.get_doc(kol_lookup.CR_DT, name)


def funding_total(name):
    return kol_acceptance.payable_cap(_doc(name))


def funding_approved(name):
    doc = _doc(name)
    return kol.is_kol(doc) and approval_status(doc) == APPROVED


def funding_owner_filters(user):
    if kol_lookup.is_finance(user):
        return {}
    return {"requested_by": ["in", sorted(kol_lookup.team_users(user))]}


def funding_can_use(user, name):
    """Nguoi lap DNTT duoc dung hop dong nay: cua minh / cung phong ban / Ke toan."""
    if kol_lookup.is_finance(user):
        return True
    owner = frappe.db.get_value(kol_lookup.CR_DT, name, "requested_by")
    return bool(owner) and owner in kol_lookup.team_users(user)


def funding_explain(name, amount, remaining):
    doc = _doc(name)
    if not is_signed(doc):
        return _("Hợp đồng {0} chưa ký đủ hai bên nên chưa chi được, kể cả tiền cọc.").format(name)
    view = kol_acceptance.funding_view(doc)
    return _("Số tiền {0} vượt mức được chi của hợp đồng {1}: hiện chi được {2} (cọc {3} + BBNT "
             "đã hoàn tất {4}), đã đề nghị {5}, còn {6}. Phần còn lại chỉ chi sau khi BBNT hoàn tất."
             ).format(kol.fmt_money(amount), name, kol.fmt_money(view["cap"]),
                      kol.fmt_money(view["advance"]), kol.fmt_money(view["accepted"]),
                      kol.fmt_money(view["used"]), kol.fmt_money(max(remaining, 0)))


def fill_payment(pr, name):
    """Dien san tren DNTT tu hop dong: brand, loai chi phi Booking KOL/KOC, nguoi nhan.

    SO do NGUOI LAP DNTT chon (anh Hoan 12/11: "SO se duoc gan vao payment request de ke toan
    kiem tra"). Hop dong cu tung gan SO thi chi goi y khi DNTT chua chon."""
    doc = _doc(name)
    # Chi dien tu hop dong KOL nguoi lap duoc dung - khong de luu nhap DNTT thanh duong doc brand /
    # ten creator cua hop dong team khac. Sai thi bo trong, validate_funding bao loi luc nop.
    if not kol.is_kol(doc) or not funding_can_use(pr.get("requested_by") or frappe.session.user, name):
        return
    if not pr.get("ec_sales_order") and doc.get("sales_order"):
        pr.ec_sales_order = doc.get("sales_order")
    if not pr.get("ec_loai_chi_phi"):
        pr.ec_loai_chi_phi = KOL_EXPENSE_CATEGORY
    if doc.get("brand") and not pr.get("ec_brand") and frappe.db.exists("Brand", doc.brand):
        pr.ec_brand = doc.brand
    if not pr.get("payee_full_name"):
        pr.payee_full_name = doc.get("creator_name")


# --------------------------------------------------------------------------- SO tren DNTT
def funding_so_search(user, query=None):
    """SO cho o "SO doanh thu" cua DNTT: cung bo loc voi form hop dong cu (SO cua minh / team,
    SO doi ung cua GBS SO team tao; Ke toan thay het). "Da de nghi chi" do payment_request tinh."""
    return {"rows": kol_lookup.search_sales_orders(user, query),
            "missing": kol_lookup.gbs_without_counterpart(user, query)}


def funding_so_info(name):
    """SO dang gan tren DNTT (trang chi tiet - nguoi xem da duoc quyen xem DNTT): nhan, brand,
    doanh thu EC. None = SO khong con / da huy."""
    row = kol_lookup.so_row(name)
    if not row:
        return None
    return {"label": kol_lookup.so_label(row), "brand": row.get("ec_brand") or "",
            "revenue": float(row.get("net_total") or 0)}


def funding_validate(pr, user):
    """Luc nop DNTT tu hop dong KOL: bat buoc SO doanh thu va nguoi lap duoc dung SO do."""
    so = (pr.get("ec_sales_order") or "").strip()
    if not so:
        frappe.throw(_("Chọn SO doanh thu (SO cung cấp dịch vụ cho brand) để Kế toán đối chiếu chi phí "
                       "với doanh thu."))
    _row, err = kol_lookup.so_allowed(user, so)
    if err:
        frappe.throw(_(err), frappe.PermissionError)
