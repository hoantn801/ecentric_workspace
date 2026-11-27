# Copyright (c) 2026, eCentric and contributors
"""Hop dong KOL/KOC tren form 27: tinh tien luc luu, chot luc gui, khoi chi tiet.

Moi con so (gross, TNCN, VAT, so tien tra, tien coc, gia tri hop dong) do SERVER tinh tu
`domain.kol.compute_amounts` - form chi hien lai. Nguoi dung sua DOM cung khong doi duoc so
tien di vao hop dong va DNTT.
"""
import datetime

import frappe
from frappe import _
from frappe.utils import now_datetime, today

from ecentric_workspace.approval_center.features.contract_review.application import kol_lookup
from ecentric_workspace.approval_center.features.contract_review.domain import kol
from ecentric_workspace.approval_center.features.contract_review.domain import (
    esign_flow, kol_calc, kol_texts, kol_values)
from ecentric_workspace.approval_center.shared.creators import domain as creators_domain
from ecentric_workspace.approval_center.shared.creators.repository import CreatorRepository

APPROVED = "Approved"


def creator_row(name):
    return CreatorRepository().get(name) if name else None


def prepare_draft(doc):
    """`draft_preparer` cua form 27: quy trinh ky mac dinh cho MOI loai; phan con lai chi lam
    viec voi phieu KOL, nuot loi tinh tien (nhap do)."""
    esign_flow.apply_default(doc)
    esign_flow.clean_labor(doc)
    esign_flow.clean_partner_sign_type(doc)
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    if not kol.is_kol(doc):
        doc.set("kol_channels", [])
        # Da tao hop dong / BBNT KOL (in CCCD, STK creator) thi khong doi sang loai khac: loai khac khong
        # che tep va lai len SharePoint chung (QC vong 4 17/11).
        if kol_access.has_kol_files(doc):
            frappe.throw(_("Phiếu đã tạo hợp đồng KOL (có CCCD, số tài khoản creator) nên không đổi sang loại "
                           "hợp đồng khác. Lập phiếu mới cho loại hợp đồng kia; phiếu này hủy đi (đang chờ "
                           "bổ sung thì nhờ người duyệt từ chối)."))
        return
    # Ban nhan ban (clone) con tro toi hop dong sinh tu mau cua phieu CU (tep gan phieu KHAC): bo, khi gui
    # se sinh lai (QC vong 4). Tep nguoi dung vua tai / da gan chinh phieu nay thi giu, du ten bat dau
    # HDDV_ / BBNT_ (QC vong cuoi 17/11 - truoc do xoa nham tep mau creator ten "HDDV_...").
    if kol_access.foreign_generated(doc, doc.get("request_attachment")):
        doc.request_attachment = None
    creator = creator_row(doc.get("creator"))
    doc.creator_name = creator.get("supplier_name") if creator else None
    doc.creator_type = creator.get("ec_cr_type") if creator else None
    snapshot_kols(doc, creator)
    _reset_partner_on_creator_change(doc)
    so = None
    if doc.get("sales_order"):
        # Kiem lai SO tren server KHI SO DOI: bo chon tren trang loc theo team, nhung save_draft
        # nhan thang ten SO - khong kiem thi doc duoc doanh thu SO cua team khac (QC 11/11).
        # SO khong doi thi khong kiem lai: nguoi da chuyen phong van gui lai / sao chep duoc.
        is_new = getattr(doc, "is_new", None)
        stored = frappe.db.get_value(kol_lookup.CR_DT, doc.name, "sales_order") \
            if doc.get("name") and not (callable(is_new) and is_new()) else None
        if doc.sales_order != stored:
            so, err = kol_lookup.so_allowed(frappe.session.user, doc.sales_order)
            if err:
                frappe.throw(_(err), frappe.PermissionError)
        so = so or kol_lookup.so_row(doc.sales_order)
    if so:
        doc.so_label = kol_lookup.so_label(so)
        doc.so_revenue = so.net_total
        # Phieu cu (truoc 12/11) da gan SO: brand chon tay tren phieu la chinh, SO chi dien khi trong.
        if so.ec_brand and not doc.get("brand"):
            doc.brand = so.ec_brand
    else:
        doc.so_label = doc.so_revenue = None
    _default_payment_days(doc)
    if doc.get("payment_schedule") == kol.PAY_ADVANCE and not doc.get("advance_percent"):
        doc.advance_percent = kol.DEFAULT_ADVANCE_PERCENT
    # O thue suat de trong: dung mac dinh NGAY TU LUC LUU. De "" thi Frappe luu thanh 0 va luc
    # gui tinh lai voi 0% - nhap thay 10% ma hop dong khong khau tru TNCN (QC 11/11).
    if doc.get("pit_rate") in (None, ""):
        doc.pit_rate = kol.DEFAULT_PIT_RATE
    if doc.get("vat_rate") in (None, ""):
        doc.vat_rate = kol.DEFAULT_VAT_RATE
    set_sign_date(doc)
    if not (doc.get("justification") or "").strip():
        doc.justification = ("Hoa hồng affiliate" if doc.get("service_type") == "Hoa hồng affiliate"
                             else "Booking KOL/KOC")
    apply_amounts(doc, strict=False)
    if not (doc.get("request_details") or "").strip():
        doc.request_details = summary_text(doc)


def snapshot_kols(doc, creator):
    """KOL / kenh phieu chon (PO 27/11, creator cong ty / ho KD co nhieu KOL). Client chi gui `kol_ref`;
    server CHUP LAI tu danh sach hien tai cua creator - client sua ten / ID trong DOM khong vao hop dong.
    Dong da ngung dung / cua creator khac (doi creator) bi bo."""
    refs = []
    for row in doc.get("kol_channels") or []:
        ref = str((row.get("kol_ref") if hasattr(row, "get") else "") or "").strip()
        if ref and ref not in refs:
            refs.append(ref)
    by_ref = {r.get("name"): r for r in (creator or {}).get("kols") or [] if not r.get("disabled")}
    doc.set("kol_channels", [])
    for ref in refs:
        r = by_ref.get(ref)
        if r:
            doc.append("kol_channels", dict({f: r.get(f) for f in creators_domain.KOL_FIELDS}, kol_ref=ref))


def kol_channel_error(doc, creator):
    """Creator co danh sach KOL dang dung ma phieu chua chon dong nao -> loi (tieng Viet), khong thi None."""
    active = [r for r in (creator or {}).get("kols") or [] if not r.get("disabled")]
    if active and not doc.get("kol_channels"):
        return "Creator %s có %d KOL / kênh: chọn ít nhất một KOL cho hợp đồng này." % (
            (creator or {}).get("supplier_name") or "", len(active))
    return None


def apply_amounts(doc, strict):
    try:
        amounts = kol.compute_amounts(doc.get("creator_type"), doc.get("amount_type"),
                                      doc.get("amount_input"), doc.get("pit_rate"), doc.get("vat_rate"))
        advance = kol.advance_amount(amounts, doc.get("creator_type"), doc.get("payment_schedule"),
                                     doc.get("advance_percent"))
        kol.payment_days(doc.get("payment_term_days"), doc.get("creator_type"), doc.get("platform"))
    except ValueError as e:
        if strict:
            frappe.throw(_(str(e)))
        # Nhap do: xoa HET so da tinh, ke ca gia tri hop dong - khong de lai so cu lech voi tien.
        doc.gross_amount = doc.pit_amount = doc.vat_amount = doc.payable_amount = None
        doc.advance_amount = doc.contract_value = None
        return
    doc.gross_amount, doc.pit_amount = amounts["gross"], amounts["pit"]
    doc.vat_amount, doc.payable_amount = amounts["vat"], amounts["payable"]
    doc.contract_value = amounts["contract_value"]
    doc.advance_amount = advance
    if doc.get("payment_schedule") != kol.PAY_ADVANCE:
        doc.advance_percent = None


def _stored(doc, fields):
    is_new = getattr(doc, "is_new", None)
    if not doc.get("name") or (callable(is_new) and is_new()):
        return {}
    return frappe.db.get_value(kol_lookup.CR_DT, doc.get("name"), fields, as_dict=True) or {}


def _default_payment_days(doc):
    """So ngay thanh toan mac dinh theo tool cu (ca nhan 35, cong ty / HKD 30, Shopee 15).

    Doi loai creator / nen tang ma o nay van dang la MAC DINH cua lua chon cu -> doi theo mac dinh
    moi; nguoi dung da go so khac thi giu nguyen."""
    current = doc.get("payment_term_days")
    want = kol.default_payment_days(doc.get("creator_type"), doc.get("platform"))
    try:
        current = None if current in (None, "") else int(float(current))
    except (TypeError, ValueError):
        frappe.throw(_("Số ngày thanh toán phải là số."))
    if current is None:
        doc.payment_term_days = want
        return
    old = _stored(doc, ["creator_type", "platform"])
    if old and (old.get("creator_type"), old.get("platform")) != (doc.get("creator_type"), doc.get("platform")):
        if current == kol.default_payment_days(old.get("creator_type"), old.get("platform")):
            doc.payment_term_days = want


def _today():
    return datetime.date.fromisoformat(str(today())[:10])


def service_dates_or_none(doc, ref=None):
    """Ngay thuc hien. Nam doan theo ngay TAO phieu (on dinh qua cac lan luu / gui lai), khong
    theo hom nay va khong theo ngay ky."""
    try:
        return kol.service_dates(doc, ref or ref_day(doc))
    except ValueError:
        return []


def ref_day(doc):
    created = doc.get("creation")
    return datetime.date.fromisoformat(str(created)[:10]) if created else _today()


def _auto_sign(air_dates, doc):
    dates = service_dates_or_none({"air_dates": air_dates}, ref_day(doc))
    return str(kol_texts.business_day_before(None, dates[0], kol_lookup.holidays())) if dates else None


def set_sign_date(doc):
    """Ngay ky = 1 ngay lam viec TRUOC buoi thuc hien dau (tool cu, bo T7/CN/ngay nghi).

    Nguoi dung TU CHON ngay (khac ngay he thong tu tinh lan truoc) va ngay do truoc buoi dau thi
    giu; chon ngay >= buoi dau thi lui ve truoc buoi dau. Ngay dang la ngay TU TINH (hoac ngay mac
    dinh hom nay khi chua co lich) thi doi lich la tinh lai - khong "dinh" ngay cu (QC 12/11)."""
    dates = service_dates_or_none(doc)
    if not dates:
        if not doc.get("contract_date"):
            doc.contract_date = today()
        return
    chosen = _user_sign_date(doc, doc.get("contract_date"))
    doc.contract_date = str(kol_texts.business_day_before(chosen, dates[0], kol_lookup.holidays()))


def _user_sign_date(doc, chosen):
    """Ngay ky NGUOI DUNG tu chon (date) hoac None = de he thong tu tinh.

    Gia tri dang luu ma lan truoc la ngay TU TINH (hoac phieu chua co lich / lich doc khong duoc,
    khi do ngay ky la ngay mac dinh hom nay) thi coi la tu dong - doi lich la tinh lai (QC 12/11)."""
    chosen = str(chosen or "")[:10] or None
    old = _stored(doc, ["air_dates", "contract_date", "creation"])
    if chosen and old and chosen == str(old.get("contract_date") or "")[:10]:
        auto = _auto_sign(old.get("air_dates"), doc) if old.get("air_dates") else None
        if auto is None or chosen == auto:
            chosen = None
    return datetime.date.fromisoformat(chosen) if chosen else None


def expected_bbnt_date(doc):
    """Ngay BBNT du kien tren HDDV = 1 ngay lam viec SAU buoi thuc hien cuoi (tool cu AFTER_SERVICE).
    BBNT that thi dung ngay nghiem thu cua tung dot."""
    dates = service_dates_or_none(doc)
    return kol_texts.business_day_after(None, dates[-1], kol_lookup.holidays()) if dates else None


def preview_dates(air_dates, contract_date=None, creator=None, brand=None, name=None, user=None):
    """Form goi khi go "Ngay thuc hien": ngay doc duoc, ngay ky du kien, so HD du kien - de
    nguoi dung thay ngay he thong hieu sai (vd thieu nam) TRUOC khi tao hop dong (QC 12/11).

    `name` chi dung khi `user` quan ly duoc phieu do (nguoi lap / Ke toan): khong cho doc lich /
    ngay ky cua phieu nguoi khac qua endpoint nay (QC3)."""
    if name:
        own = frappe.db.get_value(kol_lookup.CR_DT, name, ["requested_by", "creation"], as_dict=True)
        if not own or (user and own.get("requested_by") != user and not kol_lookup.is_finance(user)):
            name = None
    created = own.get("creation") if name else None
    ref = datetime.date.fromisoformat(str(created)[:10]) if created else _today()
    try:
        picked = datetime.date.fromisoformat(str(contract_date)[:10]) if contract_date else None
    except ValueError:
        picked, contract_date = None, None
    try:
        dates = kol.service_dates({"air_dates": air_dates}, ref)
    except ValueError as e:
        return {"ok": False, "error": str(e)}
    if not dates:
        return {"ok": True, "dates": []}
    # Cung luat voi luc luu (set_sign_date): ngay dang la ngay tu tinh thi xem truoc theo lich moi.
    chosen = _user_sign_date({"name": name, "creation": created}, contract_date) if name else picked
    sign = kol_texts.business_day_before(chosen, dates[0], kol_lookup.holidays())
    out = {"ok": True, "dates": [d.strftime("%d/%m/%Y") for d in dates], "sign_date": sign.strftime("%d/%m/%Y")}
    row = creator_row(creator) if creator else None
    if row and brand:
        party = kol_texts.party_code(row.get("ec_cr_type"), row.get("supplier_name"), row.get("ec_cr_party_code"))
        try:
            out["contract_no"] = kol.number_base(dates[0], party, kol_lookup.brand_code(brand))
        except ValueError as e:
            out["number_note"] = str(e)
    return out


def creator_gaps(creator, platform=None):
    """Thong tin creator con thieu cho hop dong (nhan tieng Viet, KHONG tra gia tri)."""
    row = creator_row(creator)
    if not row:
        return {"labels": []}
    ctype = row.get("ec_cr_type")
    values = kol_values.contract_values({"creator_type": ctype, "platform": platform or "TikTok",
                                         "service_type": "Livestream"}, row, "", None, [_today()])
    need = (set(kol_values.REQUIRED_WHEN_USED["_all"]) | set(kol_values.REQUIRED_WHEN_USED.get(ctype, ()))) \
        & set(kol_values.CREATOR_FIELDS)
    missing = sorted(k for k in need if not str(values.get(k) or "").strip())
    return {"labels": kol_values.missing_labels(missing)}


def summary_text(doc):
    parts = [doc.get("service_type") or "", doc.get("platform") or "",
             ("%s buổi/video" % doc.quantity) if doc.get("quantity") else "",
             doc.get("duration") or "", doc.get("air_dates") or ""]
    return "Creator %s - %s" % (doc.get("creator_name") or "?", ", ".join(p for p in parts if p))


def fill_partner_signer(doc, creator):
    """Nguoi ky phia doi tac (cong ky so gui email moi ky - THIETKE K6): o nao trong thi lay tu
    creator. Ca nhan: chinh creator; cong ty / ho KD: nguoi dai dien (khong co thi ten don vi).
    Chi dien voi quy trinh co doi tac ky tren cong; nguoi lap sua tay duoc."""
    if not creator or not esign_flow.needs_partner(doc.get("esign_flow")):
        return
    person = creator.get("ec_cr_type") == "Cá nhân"
    name = creator.get("supplier_name") if person else (
        creator.get("ec_cr_representative_name") or creator.get("supplier_name"))
    for field, value in (("partner_signer_name", name), ("partner_signer_email", creator.get("ec_cr_email")),
                         ("partner_signer_phone", creator.get("ec_phone"))):
        if not (doc.get(field) or "").strip() and value:
            doc.set(field, str(value).strip()[:140])


PARTNER_FIELDS = ("partner_signer_name", "partner_signer_email", "partner_signer_phone", "partner_signer_identity")
IDENTITY_FIELD = "partner_signer_identity"
_CREATOR_ID_FIELDS = ["ec_cr_type", "supplier_name", "ec_cr_email", "ec_cr_cccd", "ec_cr_cccd_issue_place",
                      "ec_cr_cccd_issue_date", "ec_cr_dob", "tax_id"]


def _norm_id(value):
    """CCCD / MST: bo khoang trang, cham; giu chu so, chu cai va '-' (MST chi nhanh 0101234567-001)."""
    return "".join(ch for ch in str(value or "") if ch.isalnum() or ch == "-").strip("-")


def _norm_name(value):
    return " ".join(str(value or "").split()).casefold()


def _fmt_day(value):
    if not value:
        return ""
    s = str(value)[:10]
    try:
        y, m, d = s.split("-")
        return "%s/%s/%s" % (d, m, y)
    except ValueError:
        return s


def _signer_is_creator(doc, cr):
    """Nguoi ky phia doi tac la CHINH creator ca nhan: trung email, hoac (creator chua co email) trung ten."""
    email = (doc.get("partner_signer_email") or "").strip().lower()
    cr_email = (cr.get("ec_cr_email") or "").strip().lower()
    if email and cr_email:
        return email == cr_email
    return _norm_name(doc.get("partner_signer_name")) == _norm_name(cr.get("supplier_name"))


def partner_identity(doc):
    """Dinh danh nguoi ky phia doi tac cho cong ky CMC (BAT BUOC voi moi hop dong co doi tac ky - chat Ky so
    24/11) -> (truong gui cong {identity, identity_place?, identity_date?, dob?}, loi tieng Viet hoac None).

      * O "CCCD / MST nguoi ky phia doi tac" co gia tri -> dung no (nguoi ky la nguoi dai dien / nguoi khac).
      * Hop dong KOL, o trong: creator ca nhan ky chinh minh -> CCCD (+ noi cap, ngay cap, ngay sinh);
        creator ca nhan nhung nguoi ky la nguoi khac -> phai nhap CCCD nguoi ky; cong ty / ho kinh doanh ->
        MST (ho kinh doanh chua co MST thi CCCD chu ho).
      * Hop dong khac, o trong -> loi (khong co nguon du lieu doi tac).
    KHONG ghi log gia tri nao (PII)."""
    manual = _norm_id(doc.get(IDENTITY_FIELD))
    if manual:
        if len(manual) < 9:
            return {}, _("\"CCCD / MST người ký phía đối tác\" không hợp lệ - nhập đủ số CCCD (12 số) hoặc MST.")
        return {"identity": manual}, None
    if not (kol.is_kol(doc) and doc.get("creator")):
        return {}, _("Nhập \"CCCD / MST người ký phía đối tác\" (CCCD với cá nhân, MST với công ty / hộ kinh doanh) "
                     "- cổng ký số bắt buộc.")
    cr = frappe.db.get_value("Supplier", doc.creator, _CREATOR_ID_FIELDS, as_dict=True) or {}
    kind = cr.get("ec_cr_type")
    if kind == "Cá nhân":
        if not _signer_is_creator(doc, cr):
            return {}, _("Người ký phía đối tác không phải chính creator: nhập CCCD của người ký vào ô \"CCCD / MST "
                         "người ký phía đối tác\" - cổng ký số bắt buộc.")
        cccd = _norm_id(cr.get("ec_cr_cccd"))
        if not cccd:
            return {}, _("Creator chưa có CCCD - bổ sung trong thông tin creator (cổng ký số bắt buộc).")
        out = {"identity": cccd}
        for key, value in (("identity_place", cr.get("ec_cr_cccd_issue_place")),
                           ("identity_date", _fmt_day(cr.get("ec_cr_cccd_issue_date"))),
                           ("dob", _fmt_day(cr.get("ec_cr_dob")))):
            if value:
                out[key] = str(value).strip()
        return out, None
    tax = _norm_id(cr.get("tax_id")) or (_norm_id(cr.get("ec_cr_cccd")) if kind == "Hộ kinh doanh" else "")
    if not tax:
        return {}, _("Creator ({0}) chưa có MST - bổ sung trong thông tin creator, hoặc nhập vào ô \"CCCD / MST "
                     "người ký phía đối tác\" (cổng ký số bắt buộc).").format(kind or "công ty")
    return {"identity": tax}, None


def partner_identity_error(doc):
    """Loi thieu dinh danh doi tac (None khi du / quy trinh khong co doi tac ky tren cong)."""
    if not esign_flow.needs_partner(doc.get("esign_flow")):
        return None
    return partner_identity(doc)[1]


def _reset_partner_on_creator_change(doc):
    """Doi creator (bo sung / sao chep phieu): xoa nguoi ky phia doi tac cua creator CU de luc gui
    dien lai theo creator moi (QC 15/11 B-05). O nao nguoi lap vua sua tay trong lan luu nay thi giu."""
    stored = _stored(doc, ["creator"] + list(PARTNER_FIELDS))
    if not stored or stored.get("creator") == doc.get("creator"):
        return
    for field in PARTNER_FIELDS:
        if (doc.get(field) or "") == (stored.get(field) or ""):
            doc.set(field, None)


def partner_signer_errors(doc):
    """Quy trinh co doi tac ky tren cong: thieu ten / email thi cong khong gui duoc link (QC 15/11
    A13, B-05); email la tai khoan noi bo = nhan vien ky thay creator (B-04)."""
    if not esign_flow.needs_partner(doc.get("esign_flow")):
        return []
    email = (doc.get("partner_signer_email") or "").strip().lower()
    if not (doc.get("partner_signer_name") or "").strip() or not email:
        return [_("Nhập tên và email người ký phía đối tác (ô \"Người ký phía đối tác\") - creator chưa có email, "
                  "hoặc bổ sung email trong thông tin creator.")]
    if frappe.db.exists("User", {"name": email, "user_type": "System User"}):
        return [_("Email người ký phía đối tác đang là tài khoản nội bộ - nhập email của creator.")]
    return []


def validate_submit(doc):
    """Chot truoc khi vao luong duyet - goi tu service.submit VA service.resubmit (phieu KOL).

    Mau EC: sinh lai hop dong neu du lieu da doi tu lan tao tep (dau van tay lech), de van ban
    gui ky luon khop so tien / creator / SO dang duyet."""
    creator = creator_row(doc.get("creator"))
    errors = kol.validate_kol(doc, creator and creator.get("ec_cr_type"), ref_day(doc))
    if not creator:
        errors.append("Creator không tồn tại hoặc không thuộc danh sách creator.")
    elif creator.get("disabled"):
        # Danh sach chon da an creator ngung dung, nhung phieu nhap cu / goi API van mang ten (QC 15/11 A10).
        errors.append("Creator này đã ngừng sử dụng - chọn creator khác.")
    if doc.get("request_type") == kol.TEMPLATE_PARTNER and not doc.get("request_attachment"):
        errors.append("Tải lên hợp đồng theo mẫu của creator trước khi gửi.")
    if doc.get("request_kind") == "Existing":
        # PO 17/11: thuc te it lam phu luc tang tien; phu luc KOL chua noi vao HD goc (so moi, tran
        # DNTT rieng -> hai tran chong nhau). Tang tien = lap hop dong moi.
        errors.append("Hợp đồng KOL/KOC không làm phụ lục điều chỉnh - chọn \"Hợp đồng / phụ lục MỚI\" (cần tăng "
                      "tiền thì lập hợp đồng mới).")
    if errors:
        frappe.throw(_(" ".join(errors)))
    prepare_draft(doc)
    kol_err = kol_channel_error(doc, creator)
    if kol_err:
        frappe.throw(_(kol_err))
    apply_amounts(doc, strict=True)
    fill_partner_signer(doc, creator)
    # PO 17/11 (D): chot van tay STK nhan tien theo creator luc gui - hop dong sinh ra in STK nay.
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    kol_access.snapshot_payee(doc, creator)
    signer_errors = partner_signer_errors(doc)
    if signer_errors:
        frappe.throw(" ".join(signer_errors))
    if doc.get("request_type") == kol.TEMPLATE_EC:
        from ecentric_workspace.approval_center.features.contract_review.application import kol_files
        kol_files.build_contract(doc)
    else:
        # Doi tu mau EC sang mau creator: ket qua dien mau EC cu khong con ap dung (QC 12/11).
        doc.missing_placeholders = doc.contract_fingerprint = doc.generated_template = None
        assign_number(doc, creator)
    if doc.get("missing_placeholders"):
        names = _split(doc.missing_placeholders)
        hint = (_("Bấm Sửa thông tin creator để bổ sung (hoặc nhờ người tạo creator / Kế toán)")
                if kol_values.missing_is_creator(names) else _("Bổ sung trên phiếu"))
        frappe.throw(_("Hợp đồng còn thiếu: {0}. {1} rồi gửi lại.").format(
            ", ".join(kol_values.missing_labels(names)), hint))
    # Doi chieu doanh thu SO chuyen sang DNTT (12/11). Phieu cu da gan SO thi van canh bao.
    if doc.get("sales_order"):
        committed = kol_lookup.committed_on_so(doc.sales_order, exclude=doc.name)
        doc.revenue_warning = kol.revenue_warning(doc.so_revenue, committed, doc.contract_value) or None
    else:
        doc.revenue_warning = None


def assign_number(doc, creator):
    """Cap / cap lai so hop dong. So dang co ma khong con khop ngay thuc hien dau / ma doi tac /
    ma brand (doi creator, brand, ngay sau lan tao dau) thi cap lai - so sai di vao van ban phap ly.

    Ma doi tac: Ke toan dien tay (ec_cr_party_code) thi dung, khong thi suy tu ten nhu tool cu
    (ca nhan = chu cai dau, cong ty / HKD = viet tat bo "Cong ty TNHH..."); ngay = buoi dau tien."""
    dates = service_dates_or_none(doc)
    number_date = dates[0] if dates else (doc.contract_date or today())
    party = kol_texts.party_code(creator.get("ec_cr_type"), creator.get("supplier_name"),
                                 creator.get("ec_cr_party_code"))
    try:
        base = kol.number_base(number_date, party, kol_lookup.brand_code(doc.get("brand")))
    except ValueError as e:
        frappe.throw(_(str(e)))
    existing = _numbers_in_use(base, doc.name)
    if kol.number_fits(doc.get("contract_no"), base) and doc.contract_no not in existing:
        return
    doc.contract_no = kol.contract_number(number_date, party, kol_lookup.brand_code(doc.get("brand")), existing)


_RELEASED = ("Rejected", "Cancelled")


def _numbers_in_use(base, exclude):
    """So HD dang giu cho (cung goc). Phieu bi Tu choi / Huy NHA so de phieu lam lai dung lai - khong
    co hop dong that nao mang so do (PO 17/11; truoc ra "...-2" ma khong co "-1")."""
    rows = frappe.get_all(kol_lookup.CR_DT,
                          filters={"contract_no": ["like", base + "%"], "name": ["!=", exclude]},
                          fields=["contract_no", "approval_request"], limit_page_length=0,
                          ignore_permissions=True)
    reqs = [r.approval_request for r in rows if r.approval_request]
    released = set(frappe.get_all("EC Approval Request", filters={"name": ["in", reqs],
                                                                  "approval_status": ["in", _RELEASED]},
                                  pluck="name", limit_page_length=0, ignore_permissions=True)) if reqs else set()
    return {r.contract_no for r in rows if r.approval_request not in released}


def can_manage(doc, user):
    return doc.requested_by == user or kol_lookup.is_finance(user)


def is_approver(doc, user):
    return bool(doc.get("approval_request") and frappe.db.exists(
        "EC Approval Request Approver", {"approval_request": doc.approval_request, "approver": user}))


def approval_status(doc):
    if not doc.get("approval_request"):
        return None
    return frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_status")


def is_signed(doc):
    return doc.get("signing_status") == kol.SIGN_DONE


def mark_signed(name, signed_file, user):
    """Tam thoi (truoc giai doan 4 SCTS): ky tren cong roi tai ban da ky len. KHONG tu nhan la
    ky du: may kiem ban ky (kol_verify), khong dat thi cho Ke toan xac nhan (anh Hoan 11/11)."""
    doc = frappe.get_doc(kol_lookup.CR_DT, name)
    if not kol.is_kol(doc) or not can_manage(doc, user):
        frappe.throw(_("Chỉ người tạo hợp đồng hoặc Kế toán được tải bản ký."), frappe.PermissionError)
    if approval_status(doc) != APPROVED:
        frappe.throw(_("Hợp đồng phải được duyệt xong trước khi tải bản đã ký."))
    if is_signed(doc):
        frappe.throw(_("Hợp đồng đã được xác nhận ký đủ."))
    # Thanh ly truoc khi ky: tai ban ky len sau do se mo tien coc cho mot hop dong da dung (QC 17/11).
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    if kol_access.is_closed(doc):
        frappe.throw(_("Hợp đồng đã thanh lý - không nhận bản ký mới."))
    if not (signed_file or "").lower().endswith(".pdf"):
        frappe.throw(_("Bản đã ký phải là tệp PDF."))
    if signed_file in {doc.get("request_attachment"), doc.get("contract_file"), doc.get("sign_pdf")}:
        # Cung chot voi hook ky so: ban CHUA ky dem di ky khong phai ban ky (vong 2).
        frappe.throw(_("Đây là bản hợp đồng chưa ký - tải lên bản đã ký đủ chữ ký."))
    from ecentric_workspace.approval_center.features.contract_review.application import kol_verify
    from ecentric_workspace.approval_center.features.contract_review.application.kol_files import claim_upload
    doc.signed_file = claim_upload(doc, signed_file, user)
    doc.signed_at = now_datetime()
    doc.signed_marked_by = user
    findings = kol_verify.apply_contract_check(doc)
    doc.save(ignore_permissions=True)
    doc.add_comment("Info", _("Tải bản hợp đồng đã ký. Máy kiểm: đạt, xác nhận ký đủ.") if not findings
                    else _("Tải bản hợp đồng đã ký - chờ Kế toán kiểm: {0}").format("; ".join(findings)))
    return {"signing_status": doc.signing_status, "findings": findings}


def detail_extra(business, request):
    """`detail_extender`: khoi KOL tren trang chi tiet (khong co PII creator). Hop dong lao dong: chi o
    "Ban PDF de ky" (chat Ky so 24/11, WF03). Moi loai: `esign_wait` = buoc "Duyet & Ky" cua NGUOI DANG
    XEM dang cho cong xac nhan (25/11) - trang an nut ngay tu lan ve dau, ke ca sau Ctrl+Shift+R."""
    from ecentric_workspace.approval_center.features.contract_review.application import esign_gate
    out = _detail_extra(business, request)
    wait = esign_gate.in_flight(request, frappe.session.user)
    if wait:
        out = dict(out or {})
        out["esign_wait"] = wait
    return out


def _detail_extra(business, request):
    if not kol.is_kol(business):
        if business.get("contract_type") == esign_flow.LABOR_CONTRACT_TYPE:
            from ecentric_workspace.approval_center.features.contract_review.application import kol_sign_pdf
            return {"sign_pdf": kol_sign_pdf.view(business, frappe.session.user)}
        return {}
    from ecentric_workspace.approval_center.features.contract_review.application import (
        kol_acceptance, kol_access, kol_sign_pdf)
    user = frappe.session.user
    status = (request or {}).get("approval_status") if isinstance(request, dict) else getattr(request, "approval_status", None)
    return {"kol": {
        "can_manage": can_manage(business, user),
        "can_ai": can_manage(business, user) or is_approver(business, user),
        "is_finance": kol_lookup.is_finance(user),
        # Tach nhiem vu: Ke toan nhung la nguoi lap / nguoi tai ban ky thi khong xac nhan duoc (khop
        # kol_verify._not_own) - an nut thay vi de bam roi bao loi (QC 18/11).
        "can_verify_sign": kol_lookup.is_finance(user) and user not in {
            business.get("requested_by"), business.get("owner"), business.get("signed_marked_by")},
        "approved": status == APPROVED,
        "signed": is_signed(business),
        "acceptances": _rows_for(business, user, kol_acceptance.rows_view(business)),
        # PO 17/11: ban du PII chi nguoi lap + nguoi tao creator + Ke toan tai (kol_access); thanh ly; STK doi.
        "can_download_full": kol_access.can_download_full(business, user),
        # PO 26/11: nut "Mo online (Word)" - cung nhom tren VA hop dong da co ban SharePoint (thu muc han che).
        "can_open_online": kol_access.can_open_online(business, user),
        # Ban da che: nguoi lap / nguoi duyet / Ke toan (khop kol_preview._load) - QC 17/11.
        "can_preview": can_manage(business, user) or is_approver(business, user),
        "payee_changed": kol_access.payee_changed(business),
        "payee_was_empty": business.get("kol_payee_fp") == kol_access.NO_ACCOUNT,
        # Ai doi STK (de Ke toan khac xac nhan) - QC 18/11 tach nhiem vu. Chi tinh khi dang co canh bao.
        "payee_change_by": sorted(kol_access.payee_changers(business)) if kol_access.payee_changed(business) else [],
        "can_confirm_payee": kol_access.can_confirm_payee(business, user) if kol_access.payee_changed(business) else False,
        "closed": {"at": str(business.get("kol_closed_at") or ""), "by": business.get("kol_closed_by") or "",
                   "reason": business.get("kol_close_reason") or ""} if kol_access.is_closed(business) else None,
        "acceptance_remaining": kol_acceptance.acceptance_remaining(business),
        "funding": kol_acceptance.funding_view(business),
        "missing_labels": kol_values.missing_labels(_split(business.get("missing_placeholders"))),
        "missing_creator": kol_values.missing_is_creator(_split(business.get("missing_placeholders"))),
        # Bang tinh tung buoc cho Ke toan soat (PO 12/11) - dien giai so da luu, khong tinh khac.
        "calc": kol_calc.contract_steps(business),
        # Ngay theo gio site (khong theo dong ho may nguoi dung) cho o ngay BBNT - QC6.
        "today": str(today()),
        # O "Ban PDF de ky" + ky so tren cong (ban giao chat Ky so 23/11, B1).
        "sign_pdf": kol_sign_pdf.view(business, user),
    }}


def _rows_for(business, user, rows):
    """An URL BBNT du PII voi nguoi khong duoc tai (PO 17/11 A)."""
    from ecentric_workspace.approval_center.features.contract_review.application import kol_access
    fin = kol_lookup.is_finance(user)
    own = {business.get("requested_by"), business.get("owner")}
    for r in rows:
        r["has_signed"] = bool(r.get("signed_file"))
        r["can_verify"] = bool(fin and user not in own | {r.get("completed_by")})
    if kol_access.can_download_full(business, user):
        return rows
    # Nguoi duyet dot (KTTH, KTT, CEO) thay nut tai ban du cua DOT HO DUYET (PO 24/11 cau 3).
    mine = kol_access.round_approver_files(business, user)
    for r in rows:
        if kol_access.is_generated(r.get("bbnt_file")) and r.get("bbnt_file") not in mine:
            r["bbnt_file"] = None
        if r.get("signed_file") and r.get("signed_file") not in mine:
            r["signed_file"] = None
    return rows


def _split(text):
    return [x.strip() for x in (text or "").split(",") if x.strip()]
