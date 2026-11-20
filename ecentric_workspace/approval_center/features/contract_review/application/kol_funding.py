# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC lam "nguon chi phi" cua DNTT - cac ham `funding._SOURCES` goi theo ten.

Giu o module hop dong (khong o payment_request): quy tac tran chi la cua hop dong. Payment
request chi biet "nguon nay co ham tinh tong / ham xet da duyet", khong biet BBNT la gi.
"""
import re

import frappe
from frappe import _

from ecentric_workspace.approval_center.features.contract_review.application import (
    kol_acceptance, kol_lookup)
from ecentric_workspace.approval_center.features.contract_review.application.kol_service import (
    APPROVED, approval_status, creator_row, is_signed)
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
             "đã hoàn tất {4}), đã đề nghị {5}, còn {6}. {7}"
             ).format(kol.fmt_money(amount), name, kol.fmt_money(view["cap"]),
                      kol.fmt_money(view["advance"]), kol.fmt_money(view["accepted"]),
                      kol.fmt_money(view["used"]), kol.fmt_money(max(remaining, 0)),
                      _("Hợp đồng đã thanh lý: chỉ chi trong phần cọc + BBNT đã hoàn tất.") if doc.get("kol_closed_at")
                      else _("Phần còn lại chỉ chi sau khi BBNT hoàn tất."))


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
    # Tai khoan nhan = tai khoan creator (bat buoc khop - _check_payee). Dien san khi trong: dong doi cung
    # phong lap DNTT khong thay STK day du cua creator (QC ban do 17/11).
    # Chi dien cho nguoi duoc thay STK day du (Ke toan, nguoi tao creator, nguoi lap hop dong) - dong
    # doi khac luu nhap de "doc" STK la lo so bi che (QC he thong 17/11).
    creator = creator_row(doc.get("creator")) or {}
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    # Cung luat voi tai ban du (nguoi lap chi sau khi gui) + hop dong da duyet xong - khong de "lap nhap HD
    # chon creator bat ky -> nhap DNTT -> doc STK" (QC vong 4 17/11).
    may_see = funding_approved(name) and kol_access.can_download_full(doc, frappe.session.user)
    if may_see and (not pr.get("bank_account_number") or not pr.get("account_bank")):
        if not pr.get("bank_account_number") and creator.get("ec_bank_account_no"):
            pr.bank_account_number = creator.get("ec_bank_account_no")
        if not pr.get("account_bank") and creator.get("ec_bank_name"):
            pr.account_bank = creator.get("ec_bank_name")


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


def funding_so_can_view(pr, user):
    """Ai thay doi chieu doanh thu SO tren DNTT: nguoi lap (da thay luc chon SO), Ke toan va
    nguoi duyet cua chinh phieu do (PO 12/11). Nguoi chi xem duoc phieu (vd theo doi) thi khong."""
    if user == pr.get("requested_by") or kol_lookup.is_finance(user):
        return True
    ar = pr.get("approval_request")
    return bool(ar and frappe.db.exists("EC Approval Request Approver", {"approval_request": ar, "approver": user}))


# So HD dang tool cu / ERP: ddmmyyyy/HDDV/ECENTRIC-<doi tac>.<brand>[-n] (doi tac, brand co the co "-").
# So hop dong cu ky bang tool truoc ERP. Hai kieu dang co that (18/11, Linh - EC-PAYR-2026-00693):
#   "05112026/HDDV/ECENTRIC-NTP.FCV"  (ngay truoc HDDV, co ".mau")
#   "HDDV/09102026/DMG-ECENTRIC-MCTRANNGOC"  (HDDV truoc ngay, khong co ".mau", ten doi tac truoc ECENTRIC)
# Ban cu chi nhan kieu 1 -> kieu 2 bi bao "phai gan hop dong KOL" du da chon No + ghi so HD.
# Nhan ca HĐDV (co dau). Ky tu cuoi phai la chu/so: khong an ")" "." "-" dinh sau so HD.
_OLD_NUMBER = re.compile(r"(?<![\w/])(?:\d{8}/H[DĐ]DV|H[DĐ]DV/\d{8})/[A-Za-z0-9][A-Za-z0-9().\-]*[A-Za-z0-9]", re.I)
_RELEASED = ("Rejected", "Cancelled")


def legacy_contract_ref(pr):
    """PO 17/11: DNTT Booking KOL cho hop dong ky bang tool cu (truoc ERP) - "Khong" co chung tu nguon,
    ly do ghi so hop dong cu. Ke toan doi chieu luc duyet. MOI so trong ly do ma trung mot hop dong ERP
    CON HIEU LUC (da gui, khong bi tu choi / huy - ke ca dang cho duyet) thi phai dung hop dong ERP do
    (co tran chi) - QC 17/11 vong 2 + ban do."""
    if pr.get("has_purchase_request") != "No":
        return False
    found = old_numbers(pr.get("no_purchase_request_reason"))
    if not found:
        return False
    for no in found:
        hit = _live_erp_contract(no)
        if hit:
            name, number, status = hit
            if status == APPROVED:
                frappe.throw(_("Hợp đồng {0} đã có trên ERP ({1}): ở \"Khoản chi này có chứng từ mua hàng?\" chọn "
                               "Yes, rồi chọn hợp đồng {1}.").format(number, name))
            frappe.throw(_("Hợp đồng {0} đang duyệt trên ERP ({1}): chờ duyệt xong rồi lập đề nghị thanh toán "
                           "theo hợp đồng đó.").format(number, name))
    # Luu so HD cu len phieu: ngoai le KHONG co tran chi -> nguoi duyet can thay cac DNTT khac cung so (PO 20/11).
    _set(pr, "ec_legacy_contract_no", ", ".join(found))
    return True


def old_numbers(text):
    """Cac so hop dong tool cu nhan duoc trong mot doan chu (giu thu tu, bo trung)."""
    out = []
    for m in _OLD_NUMBER.finditer(str(text or "")):
        no = m.group(0).rstrip("-")
        if no.upper() not in {x.upper() for x in out}:
            out.append(no)
    return out


def _set(doc, field, value):
    if isinstance(doc, dict):
        doc[field] = value
    else:
        setattr(doc, field, value)


_PR_DT = "EC Payment Request"


def legacy_view(pr):
    """Khoi canh bao cho trang DNTT: so HD tool cu cua phieu + cac DNTT KHAC (da gui, khong bi tu choi /
    huy) ghi cung so. None khi phieu khong phai ngoai le. So HD va so tien DNTT khong phai thong tin rieng
    tu -> hien cho moi nguoi xem duoc phieu."""
    nos = [x.strip() for x in str(pr.get("ec_legacy_contract_no") or "").split(",") if x.strip()]
    if not nos:
        return None
    want = {x.upper() for x in nos}
    others = {}
    for no in nos:
        for r in frappe.get_all(_PR_DT, filters={"ec_legacy_contract_no": ["like", "%" + no + "%"],
                                                 "name": ["!=", pr.get("name") or ""],
                                                 "approval_request": ["is", "set"]},
                                fields=["name", "payment_amount", "approval_request", "ec_legacy_contract_no"],
                                limit_page_length=0):
            mine = {x.strip().upper() for x in str(r.get("ec_legacy_contract_no") or "").split(",")}
            if mine & want:          # "like" khop ca so dai hon ("...FCV" trong "...FCV2") - loc lai dung so
                others[r.get("name")] = r
    live = []
    for r in others.values():
        status = frappe.db.get_value("EC Approval Request", r.get("approval_request"), "approval_status")
        if status in _RELEASED:
            continue
        live.append({"name": r.get("name"), "amount": float(r.get("payment_amount") or 0), "status": status or ""})
    live.sort(key=lambda x: x["name"])
    return {"numbers": nos, "others": live, "others_total": sum(x["amount"] for x in live)}


def _live_erp_contract(no):
    """(phieu, so HD, trang thai) cua hop dong ERP con hieu luc co so = `no`, hoac `no` = so do + "-..."/"_..."
    (vd "...FCV-dot2"). So "...FCV-12" KHONG khop "...FCV-1"."""
    rows = frappe.get_all(kol_lookup.CR_DT, filters={"contract_no": ["like", no[:9] + "%"],
                                                     "approval_request": ["is", "set"]},
                          fields=["name", "contract_no", "approval_request"], limit_page_length=0,
                          ignore_permissions=True)
    for r in sorted(rows, key=lambda x: -len(x.contract_no or "")):
        c = (r.contract_no or "").upper()
        n = no.upper()                      # SQL like khong phan biet hoa thuong - so sanh cung vay
        if not c or not (n == c or n.startswith(c + "-") or n.startswith(c + "_")):
            continue
        status = frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
        if status not in _RELEASED:
            return r.name, r.contract_no, status
    return None


def funding_validate(pr, user):
    """Luc nop DNTT tu hop dong KOL: bat buoc SO doanh thu va nguoi lap duoc dung SO do."""
    so = (pr.get("ec_sales_order") or "").strip()
    if not so:
        frappe.throw(_("Chọn SO doanh thu (SO cung cấp dịch vụ cho brand) để Kế toán đối chiếu chi phí "
                       "với doanh thu."))
    row, err = kol_lookup.so_allowed(user, so)
    if err:
        frappe.throw(_(err), frappe.PermissionError)
    # Chi phi phai ve DUNG brand cua hop dong (PnL theo brand), SO doanh thu cung brand do (QC 15/11 C5:
    # truoc do DNTT doi sang brand B + SO cua B van qua, khong canh bao nao).
    contract_brand = frappe.db.get_value(kol_lookup.CR_DT, pr.get("funding_source_name"), "brand") \
        if pr.get("funding_source_name") else None
    if contract_brand:
        if not pr.get("ec_brand"):
            # Doi sang loai chi phi khong gan brand thi normalize xoa ec_brand -> lach chot duoi (vong 2).
            frappe.throw(_("Đề nghị thanh toán theo hợp đồng KOL phải gắn brand {0}: chọn loại chi phí có brand "
                           "(vd Booking KOL/KOC) và brand {0}.").format(contract_brand))
        if pr.ec_brand != contract_brand:
            frappe.throw(_("Brand trên đề nghị thanh toán phải trùng brand của hợp đồng ({0}).").format(contract_brand))
        so_brand = row.get("ec_brand") if row else None
        if so_brand and so_brand != contract_brand:
            frappe.throw(_("SO {0} thuộc brand {1}, hợp đồng thuộc brand {2}: chọn SO của brand {2}.").format(
                so, so_brand, contract_brand))
    _check_payee(pr)


def _check_payee(pr):
    """PO 17/11 (D) + QC 17/11: tien chi ra tai khoan GO TREN DNTT - phai la tai khoan creator dang
    luu, va neu tai khoan do doi sau khi ky thi Ke toan da xac nhan tren hop dong."""
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    name = pr.get("funding_source_name")
    if not name:
        return
    doc = _doc(name)
    creator = creator_row(doc.get("creator")) or {}
    if kol_access.payee_changed(doc, creator):
        frappe.throw(_("Tài khoản nhận tiền của creator (hợp đồng {0}) đã đổi sau khi gửi phiếu. Báo Kế toán "
                       "bấm \"Xác nhận tài khoản mới\" trên hợp đồng, rồi gửi lại đề nghị này.").format(name))
    typed = re.sub(r"\D", "", str(pr.get("bank_account_number") or ""))
    stored = re.sub(r"\D", "", str(creator.get("ec_bank_account_no") or ""))
    if not stored:
        frappe.throw(_("Creator của hợp đồng {0} chưa có số tài khoản. Nhờ người tạo creator hoặc Kế toán bổ "
                       "sung, rồi gửi lại đề nghị.").format(name))
    if typed and typed != stored:
        frappe.throw(_("Số tài khoản trên đề nghị khác số tài khoản creator trong hợp đồng {0}. Sửa cho đúng "
                       "(không biết số: hỏi người lập hợp đồng hoặc Kế toán). Creator đổi tài khoản thật: cập nhật "
                       "thông tin creator, chờ Kế toán xác nhận.").format(name))
    # Ngan hang di theo so tai khoan: lay tu creator, khong de go tay lech (PO 18/11). So sanh chi so
    # tai khoan ma ngan hang go khac thi UNC co the chuyen sai noi.
    bank = (creator.get("ec_bank_name") or "").strip()
    if bank and (pr.get("account_bank") or "").strip() != bank:
        pr.account_bank = bank
