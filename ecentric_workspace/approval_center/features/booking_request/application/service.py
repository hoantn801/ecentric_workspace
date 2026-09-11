# Copyright (c) 2026, eCentric and contributors
"""Booking Request - dieu phoi tren engine dung chung.

VI SAO CO FORM NAY (Hoan brief 11/09). Luong cu: brand can booking -> bao ban Account ->
Account nhan tin cho ban Booking. Khong co ho so nao ca, nen khong ai do duoc SLA, khong biet
viec dang nam o dau, va "quen" khong de lai dau vet. Tu day moi yeu cau la mot phieu.

Luong: Account dien phieu -> L1 Account Lead (quan ly truc tiep) duyet -> ban Booking phu
trach brand nhan xu ly, khai NGAY DU KIEN XONG, lam xong thi dinh kem ket qua.

Nguoi xu ly duoc lay tu chinh brand (`Brand.ec_booking_owner`) va CHEP XUONG PHIEU luc gui.
Chep chu khong tra cuu moi lan: brand doi nguoi phu trach ve sau thi phieu cu van giu dung
nguoi chiu trach nhiem luc do - bao cao va truy vet khong bi lech nguoc."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import getdate, now_datetime, today

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Booking Request"
APPROVAL_TYPE = "BOOKING_REQUEST"
BRAND_DT = "Brand"

CHI_DINH = "KOL/KOC Chỉ định"
MIDDLE = "Middle KOL/KOC"
MASSIVE = "Massive"
LOAI_HOP_LE = (CHI_DINH, MIDDLE, MASSIVE)

#: Han Booking cam ket phai truoc ngay hoat dong bat dau it nhat ngan nay ngay.
DEM_TRUOC_HOAT_DONG = 3
#: Vai tro luoi do: brand nao chua gan nguoi Booking thi phieu ve ca nhom.
FULFILLER_ROLE = "EC Booking"

MATERIAL_FIELDS = ["brand", "booking_type", "kol_count", "expected_budget",
                   "campaign_start_date", "campaign_end_date", "brand_brief"]
REQUIRED_AT_SUBMIT = ["request_title", "brand", "booking_type", "expected_budget",
                      "campaign_start_date", "brand_brief"]


def _signature(doc):
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


# --------------------------------------------------------------------------- #
# Brand + nguoi phu trach
# --------------------------------------------------------------------------- #
def brand_owners(brand):
    """(booking_owner, account_owner) cua mot brand. Brand khong ton tai -> (None, None).

    Doc bang db.get_value nen KHONG ap quyen - chap nhan duoc vi hai gia tri nay chi la
    email noi bo dung de giao viec, va ham nay chi duoc goi tu luong gui phieu cua chinh
    nguoi dung. Khong dung no de tra lo ra ngoai."""
    if not brand:
        return None, None
    row = frappe.db.get_value(BRAND_DT, brand,
                              ["ec_booking_owner", "ec_account_owner"], as_dict=True)
    if not row:
        return None, None
    return row.get("ec_booking_owner"), row.get("ec_account_owner")


def tao_brand_moi(ten, booking_owner, account_owner):
    """Tao ban ghi Brand cho brand ngoai do Account tu go, gan luon nguoi phu trach.

    Y Hoan 11/09: "khi nhap brand moi thi ban account se nhap luon nguoi booking phu trach
    va chung ta luu lai". Nho vay brand ngoai co nguoi phu trach ngay tu phieu dau tien,
    khong phai cho admin gan.

    `ec_can_chuan_hoa = 1` vi ten la do nguoi dung go: admin se ra lai chinh ta / gop trung
    roi tat co. Khong tu y sua ten cua ai o day.

    Tra ve TEN ban ghi Brand (= ma brand). Trung ten thi tra ban da co, khong tao ban thu hai."""
    ten = (ten or "").strip()
    if not ten:
        frappe.throw(_("Vui lòng nhập tên brand."))
    if frappe.db.exists(BRAND_DT, ten):
        return ten
    doc = frappe.new_doc(BRAND_DT)
    doc.brand = ten
    for truong, gia_tri in (("ec_brand_name", ten), ("ec_status", "Active"),
                            ("ec_brand_source", "External"), ("ec_can_chuan_hoa", 1),
                            ("ec_booking_owner", booking_owner),
                            ("ec_account_owner", account_owner)):
        if doc.meta.has_field(truong):
            doc.set(truong, gia_tri)
    doc.insert(ignore_permissions=True)
    return doc.name


# --------------------------------------------------------------------------- #
# Khoang ngay hop le cho han Booking cam ket
# --------------------------------------------------------------------------- #
def khoang_ngay_hop_le(campaign_start, hom_nay=None):
    """(ngay_som_nhat, ngay_muon_nhat, la_gap) cho o "ngay du kien xu ly xong".

    Luat Hoan chot: chon trong khoang tu ngay nhan viec den D-3 cua ngay hoat dong bat dau.

    Truong hop cua so RONG (hoat dong bat dau trong vong 3 ngay toi - yeu cau gap): neu chan
    thi ban Booking khong nhan viec duoc va se quay lai nhan tin tay, dung cai luong vua bo
    di. Nen thay vi chan, noi rong tran len chinh ngay hoat dong bat dau va danh dau `la_gap`
    de man hinh noi ro day la ngoai le. QUYET DINH NAY LA CUA CLAUDE, khong nam trong brief -
    neu muon chan han thi doi `la_gap` thanh mot frappe.throw o ham goi."""
    hom_nay = getdate(hom_nay or today())
    if not campaign_start:
        return hom_nay, None, False
    start = getdate(campaign_start)
    muon_nhat = frappe.utils.add_days(start, -DEM_TRUOC_HOAT_DONG)
    if getdate(muon_nhat) < hom_nay:
        return hom_nay, max(start, hom_nay), True
    return hom_nay, getdate(muon_nhat), False


def _kiem_ngay_cam_ket(expected_date, campaign_start):
    if not expected_date:
        frappe.throw(_("Vui lòng chọn ngày dự kiến xử lý xong trước khi nhận việc."))
    ngay = getdate(expected_date)
    som, muon, gap = khoang_ngay_hop_le(campaign_start)
    if ngay < som:
        frappe.throw(_("Ngày dự kiến xử lý xong không được nằm trong quá khứ."))
    if muon and ngay > getdate(muon):
        if gap:
            frappe.throw(_("Hoạt động bắt đầu ngày {0}. Ngày dự kiến xử lý xong không được "
                           "muộn hơn ngày đó.").format(frappe.utils.formatdate(campaign_start)))
        frappe.throw(_("Ngày dự kiến xử lý xong phải trước ngày hoạt động bắt đầu ít nhất "
                       "{0} ngày (chậm nhất {1}).").format(
            DEM_TRUOC_HOAT_DONG, frappe.utils.formatdate(muon)))
    return ngay


# --------------------------------------------------------------------------- #
# Gui / gui lai
# --------------------------------------------------------------------------- #
@frappe.whitelist(methods=["POST"])
def submit(name):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.approval_request:
        frappe.throw(_("Yêu cầu này đã được gửi."))
    if doc.requested_by and doc.requested_by != frappe.session.user \
            and "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Bạn chỉ có thể gửi yêu cầu của chính mình."))
    user = doc.requested_by or frappe.session.user
    doc.requested_by = user
    emp = _requester_context(user)
    if emp:
        doc.employee = emp.name
        doc.department = doc.department or emp.department
        doc.company = doc.company or emp.company

    missing = [f for f in REQUIRED_AT_SUBMIT if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc trước khi gửi."))
    if doc.booking_type not in LOAI_HOP_LE:
        frappe.throw(_("Loại booking không hợp lệ."))
    _kiem_noi_dung_theo_loai(doc)
    if doc.campaign_end_date and str(doc.campaign_end_date) < str(doc.campaign_start_date):
        frappe.throw(_("Ngày kết thúc hoạt động phải sau ngày bắt đầu."))
    if float(doc.expected_budget or 0) <= 0:
        frappe.throw(_("Ngân sách dự kiến phải lớn hơn 0."))

    _chot_brand_va_nguoi_phu_trach(doc, user)
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)

    req_name = engine.submit(BUSINESS_DT, doc.name, APPROVAL_TYPE, user)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    return req_name


def _kiem_noi_dung_theo_loai(doc):
    """Ba loai booking doi hoi thong tin khac nhau - kiem o SERVER, khong chi an/hien tren form.

    Form co the bi bo qua (goi thang API), va mot phieu Massive khong co so luong thi ban
    Booking khong bao gia duoc: no se quay ve nhan tin hoi - dung cai viec form nay sinh ra
    de bo."""
    if doc.booking_type == CHI_DINH:
        rows = [r for r in (doc.get("kol_list") or []) if (r.get("kol_name") or "").strip()]
        if not rows:
            frappe.throw(_("Loại “{0}” phải nêu ít nhất một KOL/KOC.").format(CHI_DINH))
        return
    if int(doc.kol_count or 0) <= 0:
        frappe.throw(_("Vui lòng nhập số lượng KOL/KOC dự kiến."))


def _chot_brand_va_nguoi_phu_trach(doc, user):
    """Chot ma brand + chep nguoi phu trach xuong phieu. Chay TRUOC khi gui di."""
    ten_go = (doc.brand_display_name or doc.brand or "").strip()
    if doc.brand_is_new:
        if not doc.booking_owner:
            frappe.throw(_("Brand mới: vui lòng chọn bạn Booking phụ trách brand này."))
        doc.brand = tao_brand_moi(ten_go, doc.booking_owner, doc.account_owner or user)
        doc.account_owner = doc.account_owner or user
    else:
        if not frappe.db.exists(BRAND_DT, doc.brand):
            frappe.throw(_("Brand không tồn tại trong danh mục."))
        booking, account = brand_owners(doc.brand)
        doc.booking_owner = booking
        doc.account_owner = account or user
    doc.brand_display_name = ten_go or doc.brand


@frappe.whitelist(methods=["POST"])
def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    _kiem_noi_dung_theo_loai(doc)
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user,
                    restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}


# --------------------------------------------------------------------------- #
# Buoc xu ly cua Booking
# --------------------------------------------------------------------------- #
def _duoc_nhan_viec(name, user):
    """Dung mot luat voi Payment Request: co ToDo mo cho minh, HOAC thuoc nhom Fulfiller
    cua luong dang chay, HOAC System Manager."""
    if frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                 "allocated_to": user, "status": "Open"}):
        return True
    if engine.is_active_process_fulfiller(APPROVAL_TYPE, user):
        return True
    return "System Manager" in frappe.get_roles(user)


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(name, user=None, expected_date=None):
    """Booking NHAN xu ly, kem NGAY DU KIEN XONG - bat buoc.

    Ngay nay la cam ket cua chinh ban Booking va la can cu DUY NHAT de nhac viec. Khong khai
    thi khong nhan duoc: mot han khong co can cu thi khong phai mot han."""
    user = user or frappe.session.user
    if not _duoc_nhan_viec(name, user):
        frappe.throw(_("Bạn không thuộc nhóm Booking xử lý yêu cầu này."), frappe.PermissionError)
    campaign_start = frappe.db.get_value(BUSINESS_DT, name, "campaign_start_date")
    ngay = _kiem_ngay_cam_ket(expected_date, campaign_start)
    # UPDATE co dieu kien: hai nguoi bam cung luc thi chi mot nguoi thang, va ngay cam ket ghi
    # TRONG CUNG lenh - khong bao gio ton tai trang thai "da nhan ma chua co han".
    frappe.db.sql(
        """update `tabEC Booking Request`
              set fulfillment_owner=%s, fulfillment_status='In Progress',
                  fulfillment_expected_date=%s, fulfillment_due_at=%s
            where name=%s and fulfillment_status='Assigned'""",
        (user, ngay, han_xu_ly(ngay), name))
    if not frappe.db.sql("select 1 from `tabEC Booking Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Yêu cầu này đã có người khác nhận xử lý."))
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Booking xử lý yêu cầu"), date=ngay)
    engine.log_action(doc.approval_request, "Started", user,
                      comment=_("Booking nhận xử lý, dự kiến xong {0}").format(
                          frappe.utils.formatdate(ngay)),
                      new_status="In Progress")
    engine.notify([doc.requested_by, doc.account_owner],
                  _("{0} đã nhận xử lý booking, dự kiến xong {1}: {2}").format(
                      user, frappe.utils.formatdate(ngay),
                      engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"owner": user, "expected_date": str(ngay)}


def han_xu_ly(expected_date):
    """Han = 17:00 ngay Booking cam ket. Khong co ngay -> None (khong bia han)."""
    if not expected_date:
        return None
    return "%s 17:00:00" % getdate(expected_date)


@frappe.whitelist(methods=["POST"])
def complete_fulfillment(name, user=None, payload=None):
    from ecentric_workspace.approval_center.shared.requests.command_service import attach_extra_files
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_status not in ("Assigned", "In Progress"):
        frappe.throw(_("Yêu cầu không ở bước Booking xử lý."))
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chỉ người đã nhận xử lý hoặc System Manager mới được hoàn tất."),
                     frappe.PermissionError)
    tom_tat = str(data.get("fulfillment_summary") or "").strip()[:1000]
    url = str(data.get("completed_attachment") or doc.completed_attachment or "").strip()
    # Ket qua booking co the la mot danh sach KOL go thang vao o ghi chu, khong nhat thiet la
    # file - nen KHONG bat buoc dinh kem nhu phieu chi (o do UNC la chung tu ke toan). Nhung
    # phai co IT NHAT mot trong hai, de "hoan tat" khong bao gio la mot o trong.
    if not tom_tat and not url:
        frappe.throw(_("Vui lòng ghi chú kết quả hoặc đính kèm file trước khi hoàn tất."))
    if url:
        if not url.startswith(("/files", "/private/files")):
            frappe.throw(_("File đính kèm không hợp lệ."))
        doc.completed_attachment = url
        attach_extra_files(doc, [url])
    doc.fulfillment_summary = tom_tat or None
    doc.fulfillment_status = "Completed"
    doc.fulfillment_owner = doc.fulfillment_owner or user
    doc.completed_by = user
    doc.completed_at = now_datetime()
    doc.save(ignore_permissions=True)
    engine.close_fulfillment_todos(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Completed", user,
                      comment=_("Đã xử lý booking") + ((": " + tom_tat) if tom_tat else ""),
                      new_status="Completed")
    engine.notify([doc.requested_by, doc.account_owner, doc.fulfillment_owner],
                  _("Đã xử lý xong booking: {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"completed": True}


# --------------------------------------------------------------------------- #
# Khoi doc them cho man hinh chi tiet
# --------------------------------------------------------------------------- #
def booking_block(business_doc, approval_request=None):
    """Ngu canh man hinh chi tiet can ma khong nam tren phieu: khoang ngay hop le cho o
    "ngay du kien xong".

    Tinh o SERVER chu khong de man hinh tu tinh: neu de JS tu tru 3 ngay thi luat song o hai
    noi, va cai o trinh duyet se lech ngay hom nao doi luat ma quen sua mot ben. CHI DOC."""
    doc = business_doc if hasattr(business_doc, "get") else {}
    som, muon, gap = khoang_ngay_hop_le(doc.get("campaign_start_date"))
    return {"booking": {
        "ngay_som_nhat": str(som) if som else None,
        "ngay_muon_nhat": str(muon) if muon else None,
        "la_gap": 1 if gap else 0,
        "dem_truoc_hoat_dong": DEM_TRUOC_HOAT_DONG,
    }}


# --------------------------------------------------------------------------- #
# Duyet xong -> chuyen Booking
# --------------------------------------------------------------------------- #
def on_final_approval(name):
    """Duyet xong thi giao viec. Giao DICH DANH cho ban Booking phu trach brand.

    Hai thu khac nhau, co y:
      * VIEC (ToDo + thong bao) di thang toi `booking_owner` - dung nguoi phu trach brand,
        dung y "nguoi xu ly specific theo tung brand" Hoan chot.
      * QUYEN NHAN viec thi rong hon: ca Role EC Booking. Neu chi mot nguoi nhan duoc thi
        ho nghi mot hom la phieu nam yen den het chien dich, va Account se quay lai nhan tin
        tay - dung cai luong form nay sinh ra de bo. Nguoi khac nhan ho thi audit ghi ro ai.

    Engine KHONG truyen ngu canh khi giai nguoi xu ly o muc process (`_resolve_fulfillers`
    goi `resolve_participants` khong kem context), nen KHONG the khai `booking_owner` bang
    mot dong participant kieu "Reference User Field" - do la ly do viec giao dich danh nam
    o day chu khong nam trong cau hinh."""
    doc = frappe.get_doc(BUSINESS_DT, name)
    frappe.db.set_value(BUSINESS_DT, name, {
        "fulfillment_status": "Assigned",
        "fulfillment_owner": None,          # chua ai nhan; nhan roi moi co chu
        "fulfillment_due_at": None,         # han chi co sau khi Booking cam ket ngay
    })
    nguoi_nhan = [u for u in (doc.booking_owner,) if u]
    if not nguoi_nhan:
        # Brand chua gan nguoi phu trach (ban ghi cu, hoac admin xoa): roi ve ca nhom.
        nguoi_nhan = _ca_nhom_booking(doc)
    if nguoi_nhan:
        engine.assign(BUSINESS_DT, name, nguoi_nhan, _("Booking xử lý yêu cầu"),
                      date=getdate(doc.campaign_start_date) if doc.campaign_start_date else None,
                      fulfillment=True)
    else:
        frappe.log_error(
            "Booking Request %s: brand %s chua gan ec_booking_owner va Role %s khong co ai"
            % (name, doc.brand, FULFILLER_ROLE), "booking_request.on_final_approval")
    engine.notify([doc.requested_by, doc.account_owner] + nguoi_nhan,
                  _("Đã duyệt — chuyển Booking xử lý (hoạt động bắt đầu {0}): {1}").format(
                      frappe.utils.formatdate(doc.campaign_start_date)
                      if doc.campaign_start_date else "—",
                      engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)


def _ca_nhom_booking(doc):
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    if not proc_name:
        return []
    proc = frappe.get_doc("EC Approval Process", proc_name)
    return [u for u, _lbl in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]
