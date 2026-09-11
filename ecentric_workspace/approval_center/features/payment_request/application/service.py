"""Business rules owned by the payment_request module."""
from ecentric_workspace.approval_center.shared.finance_support import _, frappe, getdate
from ecentric_workspace.approval_center.features.payment_request.application import funding


def payment_title(doc):
    """User-entered title wins; auto-generated 'Payment Request - payee - amount' only when
    the title is left blank (2026-08-23: the form now has an explicit title field, which also
    feeds eContract docTitle via the profile's title_source)."""
    manual = _strip_installment_suffix((doc.get("request_title") or "").strip())
    if manual:
        return _with_installment_suffix(doc, manual)
    amount = doc.get("payment_amount")
    amount = "%.0f" % float(amount) if amount not in (None, "") else "?"
    return _with_installment_suffix(
        doc, "Payment Request - %s - %s" % (doc.get("payee_full_name") or "?", amount))


_INST_SUFFIX_RE = None


def _strip_installment_suffix(title):
    """Bo hau to " — Đợt k" (chep tu phieu dot truoc) de khong thanh "Đợt 1 — Đợt 2"."""
    import re
    global _INST_SUFFIX_RE
    if _INST_SUFFIX_RE is None:
        _INST_SUFFIX_RE = re.compile(r"\s*[—-]\s*Đợt\s+\d+\s*$")
    return _INST_SUFFIX_RE.sub("", title or "").strip()


def _with_installment_suffix(doc, title):
    """Phieu chia dot: tieu de mang so dot de 5 nguoi ky va ke toan nhin ra ngay day la khoan
    nao trong chuoi (tieu de cung la docTitle tren eContract)."""
    if (doc.get("payment_mode") or "Full") == "Installment" and int(doc.get("installment_no") or 0) > 0:
        suffix = " — Đợt %d" % int(doc.get("installment_no"))
        return (title[:180 - len(suffix)] + suffix)
    return title[:180]

def normalize_payment(doc):
    doc.details_and_attachments_correct = ("Yes" if doc.details_and_attachments_correct is True
        or str(doc.details_and_attachments_correct or "").strip().lower() in ("yes", "1", "true") else "No")
    _sync_funding_aliases(doc)


def _sync_funding_aliases(doc):
    """Keep the legacy `purchase_request` field and the generic funding pair in step.

    `purchase_request` predates the generic pair and is still read by older code paths and by
    historical records, so we dual-write instead of dropping it. The generic pair is canonical;
    the legacy field mirrors it only when the source IS an EC Purchase Request.
    """
    src_dt = (doc.get("funding_source_doctype") or "").strip()
    src_name = (doc.get("funding_source_name") or "").strip()
    legacy = (doc.get("purchase_request") or "").strip()
    if src_dt and src_name:
        doc.purchase_request = src_name if src_dt == "EC Purchase Request" else None
    # Brand chi co nghia voi loai chi phi gan brand. Doi loai xong ma con gia tri cu thi bao
    # cao theo brand nhan mot khoan khong thuoc ve no - cung kieu bay voi funding_source khi
    # doi has_purchase_request sang "No".
    category = (doc.get("ec_loai_chi_phi") or "").strip()
    if not category or not frappe.db.get_value("EC Loai Chi Phi", category, "can_brand"):
        doc.ec_brand = None
        # Doi sang loai khong gan brand thi bo luon phan "brand moi", neu khong mot phieu
        # thue van phong van co the tao ra mot ban ghi Brand rac luc gui di.
        doc.ec_brand_moi = 0
        doc.ec_brand_ten = None
    elif legacy:
        # Older client (or historical draft) only set the legacy field -> promote it.
        doc.funding_source_doctype = "EC Purchase Request"
        doc.funding_source_name = legacy

BRAND_DT = "Brand"


def chot_brand_ngoai(doc):
    """Brand ngoai do nguoi lap tu go -> tao ban ghi Brand roi gan vao phieu.

    Hoan chot 12/09: "brand external thi theo booking request". Lam dung khuon
    booking_request.tao_brand_moi, ke ca co `ec_can_chuan_hoa = 1` de admin ra lai chinh ta
    va gop trung - ten la do nguoi dung go nen khong tu y sua o day.

    KHAC booking o mot diem co chu dich: KHONG bat chon nguoi phu trach. De nghi thanh toan
    khong biet ai phu trach brand, bat them chi khien nguoi ta chon bua. Doi lai brand tao tu
    day se thieu ma Fabric va dong phi - giong het VNS-VN va FCV-VN dang nam im trong danh
    muc - nen co `ec_can_chuan_hoa` de con loc ra ma don.

    Trung ten thi dung lai ban da co, khong tao ban thu hai.
    """
    if not frappe.utils.cint(doc.get("ec_brand_moi")):
        return
    ten = (doc.get("ec_brand_ten") or "").strip()
    if not ten:
        frappe.throw(_("Brand chưa có trong danh mục: vui lòng nhập tên brand."))
    if frappe.db.exists(BRAND_DT, ten):
        doc.ec_brand = ten
        return
    b = frappe.new_doc(BRAND_DT)
    b.brand = ten
    for truong, gia_tri in (("ec_brand_name", ten), ("ec_status", "Active"),
                            ("ec_brand_source", "External"), ("ec_can_chuan_hoa", 1)):
        if b.meta.has_field(truong):
            b.set(truong, gia_tri)
    b.insert(ignore_permissions=True)
    doc.ec_brand = b.name


def validate_payment(doc):
    required = ("reason", "payment_date", "payee_full_name", "account_bank", "bank_account_number",
                "has_purchase_request", "is_cost_valid", "request_attachment",
                # 09/09: bat buoc phan loai. Khong bat buoc thi khong ai chon, va PnL mu tro
                # lai nhu truoc - mot con so "Payment Request" khong noi len duoc dieu gi.
                "ec_loai_chi_phi",
                # 12/09: ky ghi nhan chi phi = THANG HOAT DONG, khong phai thang tra tien.
                # Truoc do PnL quy ky theo payment_date nen chi phi luon lech pha mot thang so
                # voi doanh thu: 49/49 phieu dau tien deu roi vao thang 9 du nhieu khoan la cua
                # thang 8. Form tu dien san theo ngay thanh toan nen bat buoc khong ton them thao tac.
                "ec_ky_chi_phi")
    if any(not str(doc.get(f) or "").strip() for f in required) or doc.payment_amount is None:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    try:
        if float(doc.payment_amount) <= 0: frappe.throw(_("Số tiền thanh toán phải lớn hơn 0."))
    except (TypeError, ValueError): frappe.throw(_("Số tiền thanh toán phải là số."))
    normalize_payment(doc)
    chot_brand_ngoai(doc)
    category = (doc.get("ec_loai_chi_phi") or "").strip()
    if category and frappe.db.get_value("EC Loai Chi Phi", category, "can_brand") \
            and not (doc.get("ec_brand") or "").strip():
        frappe.throw(_("Loại chi phí này gắn với một brand — vui lòng chọn brand, "
                       "hoặc tích “Brand chưa có trong danh mục” và nhập tên."))
    if doc.details_and_attachments_correct != "Yes": frappe.throw(_("Vui lòng tích xác nhận thông tin và tệp đính kèm là chính xác trước khi gửi."))
    if doc.has_purchase_request == "Yes":
        if not (doc.get("funding_source_doctype") or "").strip() or not (doc.get("funding_source_name") or "").strip():
            frappe.throw(_("Vui lòng chọn chứng từ nguồn (ĐNMH hoặc PO) cho khoản thanh toán này."))
    elif doc.has_purchase_request == "No":
        if not (doc.no_purchase_request_reason or "").strip():
            frappe.throw(_("Vui lòng nhập lý do không có Purchase Request khi chọn 'No'."))
        # "No" must not smuggle a source through a stale draft value.
        doc.funding_source_doctype = None
        doc.funding_source_name = None
        doc.purchase_request = None
    # Single guard for every source type: exists + approved + does not exceed the remainder.
    funding.validate_funding(doc)
    validate_installment(doc)


# --------------------------------------------------------------------------- #
# Thanh toan chia dot (07/09, Hoan): MOI DOT = MOT PHIEU rieng (duyet + 5 chu ky rieng, vi ke
# toan can ban de nghi ky dung so tien chi). Chuoi noi bang installment_of = phieu dot 1;
# installment_no = so dot. Khong ep 50/50: tong, so tien dot nay, so tien dot ke (mac dinh =
# con lai). "Khoi nhap lai" = create_next_installment: clone phieu dot truoc sau khi dot do
# da chi UNC (fulfillment Completed).
# --------------------------------------------------------------------------- #
INSTALLMENT = "Installment"


def _money(v):
    try:
        return float(v or 0)
    except (TypeError, ValueError):
        return 0.0


def installment_root(doc):
    return doc.get("installment_of") or doc.get("name")


def installment_chain(root):
    """Cac phieu trong chuoi (ke ca phieu goc), theo so dot. Chi doc cot can cho man hinh."""
    if not root:
        return []
    rows = frappe.get_all(BUSINESS_DT,
                          filters=[["name", "=", root]],
                          fields=["name", "installment_no", "payment_amount", "payment_date",
                                  "approval_request", "fulfillment_status", "completed_at",
                                  "next_installment_amount", "next_installment_date", "docstatus"])
    rows += frappe.get_all(BUSINESS_DT,
                           filters=[["installment_of", "=", root]],
                           fields=["name", "installment_no", "payment_amount", "payment_date",
                                   "approval_request", "fulfillment_status", "completed_at",
                                   "next_installment_amount", "next_installment_date", "docstatus"])
    seen, out = set(), []
    for r in rows:
        if r.name in seen:
            continue
        seen.add(r.name)
        out.append(r)
    for r in out:
        r["approval_status"] = (frappe.db.get_value("EC Approval Request", r.approval_request, "approval_status")
                                if r.approval_request else "Draft")
    out.sort(key=lambda r: (int(r.installment_no or 0), r.name))
    return out


def _live(r):
    """Phieu con hieu luc trong chuoi: khong bi tu choi/huy."""
    return r.get("approval_status") not in ("Rejected", "Cancelled")


def paid_before(doc):
    """Tong so tien cac dot TRUOC dot nay (phieu con hieu luc). Dot 1 -> 0."""
    no = int(doc.get("installment_no") or 1)
    if no <= 1:
        return 0.0
    return sum(_money(r.payment_amount) for r in installment_chain(installment_root(doc))
               if _live(r) and int(r.installment_no or 0) < no and r.name != doc.get("name"))


def validate_installment(doc):
    """Chay luc GUI (Submitter). Dot 1 (chua co installment_of) tu nhan so 1."""
    if (doc.get("payment_mode") or "Full") != INSTALLMENT:
        doc.payment_mode = "Full"
        doc.total_amount = None
        doc.installment_no = None
        doc.installment_of = None
        doc.next_installment_amount = None
        doc.next_installment_date = None
        return
    if not doc.get("installment_of"):
        doc.installment_no = 1
    total, this = _money(doc.get("total_amount")), _money(doc.get("payment_amount"))
    if total <= 0:
        frappe.throw(_("Thanh toán chia đợt: vui lòng nhập Tổng giá trị."))
    before = paid_before(doc)
    remaining = round(total - before - this, 2)
    if this <= 0 or remaining < 0:
        frappe.throw(_("Số tiền đợt này ({0}) vượt phần còn lại của tổng giá trị ({1}).").format(
            "%.0f" % this, "%.0f" % max(total - before, 0)))
    if remaining == 0:
        # Dot cuoi: khong con dot ke.
        doc.next_installment_amount = None
        doc.next_installment_date = None
        return
    nxt = _money(doc.get("next_installment_amount")) or remaining
    if nxt > remaining + 0.005:
        frappe.throw(_("Số tiền đợt kế ({0}) vượt phần còn lại ({1}).").format("%.0f" % nxt, "%.0f" % remaining))
    doc.next_installment_amount = nxt
    if not doc.get("next_installment_date"):
        frappe.throw(_("Vui lòng nhập Ngày dự kiến thanh toán đợt kế."))
    if getdate(doc.next_installment_date) <= getdate(doc.payment_date):
        frappe.throw(_("Ngày dự kiến đợt kế phải sau ngày thanh toán đợt này."))


def installments_block(business, request):
    """detail["extra"]["installments"] cho form + hub: chuoi cac dot, con lai, dot ke, co tao
    duoc dot ke khong. Phieu 100% -> None."""
    if (business.get("payment_mode") or "Full") != INSTALLMENT:
        return {"installments": None}
    root = installment_root(business)
    chain = installment_chain(root)
    me = business.get("name")
    total = _money(business.get("total_amount"))
    paid = sum(_money(r.payment_amount) for r in chain if _live(r) and r.fulfillment_status == "Completed")
    approved_or_pending = sum(_money(r.payment_amount) for r in chain if _live(r))
    next_req = next((r for r in chain if int(r.installment_no or 0) == int(business.get("installment_no") or 0) + 1
                     and _live(r)), None)
    remaining_after_me = round(total - sum(_money(r.payment_amount) for r in chain
                                           if _live(r) and int(r.installment_no or 0) <= int(business.get("installment_no") or 0)), 2)
    user = frappe.session.user
    can_create = bool(
        (business.get("requested_by") == user or "System Manager" in frappe.get_roles(user))
        and business.get("fulfillment_status") == "Completed"
        and remaining_after_me > 0 and not next_req)
    return {"installments": {
        "root": root, "installment_no": int(business.get("installment_no") or 1),
        "total_amount": total, "paid_amount": paid, "committed_amount": approved_or_pending,
        "remaining_after_this": remaining_after_me,
        "next_expected": {"amount": _money(business.get("next_installment_amount")) or None,
                          "date": business.get("next_installment_date")} if remaining_after_me > 0 else None,
        "next_request": next_req.name if next_req else None,
        "can_create_next": can_create,
        "chain": [{"name": r.name, "installment_no": int(r.installment_no or 0),
                   "payment_amount": _money(r.payment_amount), "payment_date": r.payment_date,
                   "approval_status": r.approval_status, "fulfillment_status": r.fulfillment_status,
                   "completed_at": r.completed_at, "is_current": r.name == me} for r in chain],
    }}


def create_next_installment(name):
    """Tao phieu NHAP dot ke tu phieu dot truoc. Dieu kien: chu phieu (hoac SM); phieu dot
    truoc da chi UNC (fulfillment Completed); con phan chua chi; chua co phieu dot ke con hieu
    luc (co roi thi tra ve phieu do - idempotent)."""
    from ecentric_workspace.approval_center.shared.requests import command_service
    from ecentric_workspace.approval_center.shared.registry import get_definition
    user = frappe.session.user
    src = frappe.get_doc(BUSINESS_DT, name)
    if src.requested_by != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Bạn chỉ có thể tạo đợt tiếp theo cho yêu cầu của chính mình."), frappe.PermissionError)
    if (src.payment_mode or "Full") != INSTALLMENT:
        frappe.throw(_("Phiếu này thanh toán 100%, không có đợt tiếp theo."))
    if src.fulfillment_status != "Completed":
        frappe.throw(_("Đợt {0} chưa được Finance xử lý UNC xong. Tạo đợt kế sau khi đợt này đã chi.").format(
            src.installment_no or 1))
    block = installments_block(src, None)["installments"]
    if block["next_request"]:
        return {"name": block["next_request"], "existing": True}
    if block["remaining_after_this"] <= 0:
        frappe.throw(_("Tổng giá trị đã thanh toán đủ, không còn đợt tiếp theo."))
    remaining = block["remaining_after_this"]
    nxt_amount = min(_money(src.next_installment_amount) or remaining, remaining)
    nxt_no = int(src.installment_no or 1) + 1
    root = installment_root(src)

    def prepare(target, source):
        target.payment_mode = INSTALLMENT
        target.total_amount = source.total_amount
        target.installment_of = root
        target.installment_no = nxt_no
        target.payment_amount = nxt_amount
        target.payment_date = source.next_installment_date
        target.next_installment_amount = None
        target.next_installment_date = None
        target.request_title = source.request_title      # title_builder tu doi hau to " — Đợt k"
        # Ngu canh cho 5 nguoi ky: dong dau ly do noi ro dot may / tong / dot truoc da chi.
        head = _("[Đợt {0} — tổng {1} VND; đợt {2} ({3}) đã thanh toán UNC ngày {4}]").format(
            nxt_no, "{:,.0f}".format(_money(source.total_amount)), source.installment_no or 1,
            source.name, frappe.utils.formatdate(source.completed_at) if source.completed_at else "—")
        body = _strip_installment_head(source.reason or "")
        target.reason = (head + "\n" + body).strip()
    out = command_service.clone_followup(get_definition(APPROVAL_TYPE), name, prepare)
    out["installment_no"] = nxt_no
    return out


def _strip_installment_head(reason):
    """Bo dong ngu canh "[Đợt k — ...]" cua dot truoc de khong chong nhieu dong."""
    lines = (reason or "").splitlines()
    while lines and lines[0].startswith("[Đợt "):
        lines = lines[1:]
    return "\n".join(lines).strip()


# --------------------------------------------------------------------------- #
# Buoc 6 - Finance xu ly UNC (07/09, Hoan). Engine fulfillment dung chung: sau cap duyet
# cuoi, engine.complete_approval goi on_final_approval (dang ky o transitions._FULFILLMENT_
# HANDLERS). Ca phong Finance (Fulfiller = Role EC Finance tren process) nhan ToDo; ai ranh
# bam "Nhan xu ly"; hoan tat = dinh kem file UNC. Han xu ly = NGAY THANH TOAN cua phieu
# (khong phai SLA gio), nhac tu D-3 (reminders.remind_unc_due).
# --------------------------------------------------------------------------- #
BUSINESS_DT = "EC Payment Request"
APPROVAL_TYPE = "PAYMENT_REQUEST"
#: Gio "het ngay lam viec" dung lam han xu ly UNC trong ngay thanh toan.
UNC_DUE_HOUR = 17


def _engine():
    from ecentric_workspace.approval_center.shared.workflow import transitions
    return transitions


def unc_due_at(payment_date):
    """Han xu ly UNC = 17:00 ngay thanh toan. Khong co ngay -> None (khong bia han)."""
    if not payment_date:
        return None
    from datetime import datetime, time
    return datetime.combine(getdate(payment_date), time(UNC_DUE_HOUR, 0))


def _claim_dates(payment_date, unc_date):
    """Hai ngay Finance khai luc nhan viec. Ca hai BAT BUOC, phai doc duoc thanh ngay.

    KHONG ep `unc_date >= payment_date`: nghe thi hop ly, nhung chua ai xac nhan la khong
    bao gio co ca nguoc lai, va dat mot rang buoc SAI vao cho chan nguoi dung thi phien hon
    la thieu no. Khi nao co ca thuc te thi them.
    """
    thieu = [nhan for nhan, gt in ((_("ngày thanh toán"), payment_date),
                                   (_("ngày có UNC"), unc_date)) if not gt]
    if thieu:
        frappe.throw(_("Nhận xử lý UNC cần khai đủ: {0}.").format(", ".join(thieu)))
    try:
        return getdate(payment_date), getdate(unc_date)
    except Exception:
        frappe.throw(_("Ngày không hợp lệ - dùng định dạng ngày của hệ thống."))


def on_final_approval(name):
    engine = _engine()
    doc = frappe.get_doc(BUSINESS_DT, name)
    proc_name = frappe.db.get_value("EC Approval Request", doc.approval_request, "approval_process")
    proc = frappe.get_doc("EC Approval Process", proc_name)
    fulfillers = [u for u, _lbl in engine.resolve_participants(
        [p for p in proc.participants if p.participant_purpose == "Fulfiller"], doc.requested_by)]
    due = unc_due_at(doc.payment_date)
    frappe.db.set_value(BUSINESS_DT, name, {
        "fulfillment_status": "Assigned",
        "fulfillment_owner": None,
        "fulfillment_due_at": due,
    })
    if fulfillers:
        # ToDo.date = ngay thanh toan -> Nhac viec xep vao "sap toi / hom nay / qua han".
        engine.assign(BUSINESS_DT, name, fulfillers, _("Finance xử lý UNC"),
                      date=getdate(doc.payment_date) if doc.payment_date else None,
                      fulfillment=True)
    else:
        # Khong co ai trong nhom Finance: phieu van Assigned (hub SM thay), ghi log de sua config.
        frappe.log_error("Payment Request %s: process %s khong co Fulfiller nao" % (name, proc_name),
                         "payment_request.on_final_approval")
    engine.notify([doc.requested_by] + fulfillers,
                  _("Đã duyệt xong — chuyển Finance xử lý UNC (hạn {0}): {1}").format(
                      frappe.utils.formatdate(doc.payment_date) if doc.payment_date else "—",
                      engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)


def claim_fulfillment(name, user=None, payment_date=None, unc_date=None):
    """Finance NHAN xu ly UNC, kem HAI ngay cam ket.

    Y Hoan 09/09: bam "Nhan xu ly" xong moi hien phan hoan tat, va luc nhan thi phai khai
    hai ngay KHAC NHAU:
      * `payment_date` - ngay tien thuc su ra khoi tai khoan -> dung de NHAC VIEC;
      * `unc_date`     - ngay co chung tu UNC -> dung de tinh QUA HAN, vi buoc nay hoan tat
                         bang viec dinh kem UNC chu khong phai bang viec chuyen tien.

    HAI NGAY NAY LA TRUONG RIENG, KHONG ghi de `payment_date` cua nguoi de nghi: ngay do da
    di qua ca bon cap duyet, ghi de la xoa mat thu moi nguoi da dong y ma khong ai biet no
    tung la gi. Giu ca hai thi con so duoc cam ket voi thuc te.

    Ca hai BAT BUOC. Khong khai thi khong nhan viec duoc - mot han xu ly khong co can cu thi
    khong phai mot han.
    """
    engine = _engine()
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and not engine.is_active_process_fulfiller(APPROVAL_TYPE, user) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Bạn không thuộc nhóm Finance xử lý UNC."), frappe.PermissionError)
    ngay_tt, ngay_unc = _claim_dates(payment_date, unc_date)
    # UPDATE co dieu kien: hai nguoi bam cung luc thi chi mot nguoi thang. Hai ngay ghi
    # TRONG CUNG lenh do - khong bao gio co trang thai "da nhan ma chua co han".
    frappe.db.sql(
        """update `tabEC Payment Request`
              set fulfillment_owner=%s, fulfillment_status='In Progress',
                  fulfillment_payment_date=%s, fulfillment_unc_date=%s, fulfillment_due_at=%s
            where name=%s and fulfillment_status='Assigned'""",
        (user, ngay_tt, ngay_unc, unc_due_at(ngay_unc), name))
    if not frappe.db.sql("select 1 from `tabEC Payment Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Phiếu này đã có người khác nhận xử lý."))
    doc = frappe.get_doc(BUSINESS_DT, name)
    # ToDo.date = ngay THANH TOAN (moc nhac viec), khong phai moc qua han.
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Finance xử lý UNC"), date=ngay_tt)
    engine.log_action(doc.approval_request, "Started", user, comment=_("Finance nhận xử lý UNC"),
                      new_status="In Progress")
    engine.notify([doc.requested_by],
                  _("{0} đã nhận xử lý UNC: {1}").format(user, engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"owner": user}


def complete_fulfillment(name, user=None, payload=None):
    engine = _engine()
    from ecentric_workspace.approval_center.shared.requests.command_service import attach_extra_files
    user = user or frappe.session.user
    data = frappe.parse_json(payload) if isinstance(payload, str) else (payload or {})
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_status not in ("Assigned", "In Progress"):
        frappe.throw(_("Phiếu không ở bước Finance xử lý UNC."))
    if doc.fulfillment_owner != user and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Chỉ người đã nhận xử lý hoặc System Manager mới được hoàn tất."),
                     frappe.PermissionError)
    url = str(data.get("completed_attachment") or doc.completed_attachment or "").strip()
    if not url.startswith(("/files", "/private/files")):
        frappe.throw(_("Vui lòng đính kèm file UNC trước khi hoàn tất."))
    doc.completed_attachment = url
    doc.fulfillment_summary = str(data.get("fulfillment_summary") or "").strip()[:500] or None
    # File UNC duoc tai len KHONG kem doctype/docname (nhan vien thuong khong co DocPerm
    # chuan) -> la File mo coi; gan vao phieu TRUOC khi save de hook attach_files cua Frappe
    # thay da co, khong tao dong thu hai.
    attach_extra_files(doc, [url])
    doc.fulfillment_status = "Completed"
    doc.fulfillment_owner = doc.fulfillment_owner or user
    doc.completed_by = user
    doc.completed_at = frappe.utils.now_datetime()
    doc.save(ignore_permissions=True)
    engine.close_fulfillment_todos(BUSINESS_DT, name)
    engine.log_action(doc.approval_request, "Completed", user,
                      comment=_("Đã xử lý UNC") + (": " + doc.fulfillment_summary if doc.fulfillment_summary else ""),
                      new_status="Completed")
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Đã thanh toán (UNC): {0}").format(engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"completed": True}


#: Ly do thay UNC phai la mot cau, khong phai mot chu. Cung nguong voi cac duong sua tay khac.
MIN_UNC_FIX_REASON = 10


def superseded_unc_files(business):
    """Danh sach URL cac file UNC tung duoc gan roi bi thay. Doc duoc ca doc lan dong get_all."""
    raw = business.get("unc_superseded_files") if hasattr(business, "get") \
        else getattr(business, "unc_superseded_files", None)
    return [u.strip() for u in str(raw or "").splitlines() if u.strip()]


def can_replace_unc(business, user=None):
    """Ai duoc thay file UNC: nguoi da nhan xu ly, hoac System Manager. Dung quyen voi nut
    "Hoan tat" - ai lam nham thi nguoi do sua."""
    user = user or frappe.session.user
    if (business.get("fulfillment_status") if hasattr(business, "get")
            else getattr(business, "fulfillment_status", None)) != "Completed":
        return False
    owner = business.get("fulfillment_owner") if hasattr(business, "get") \
        else getattr(business, "fulfillment_owner", None)
    return bool(owner == user or "System Manager" in frappe.get_roles(user))


def replace_unc_attachment(name, url, reason, summary=None, user=None):
    """Ke toan dinh NHAM file UNC roi da bam Hoan tat -> cho thay file, phieu VAN Hoan tat.

    Vi sao khong mo lai phieu ve "Dang xu ly": `fulfillment_status == "Completed"` la dieu
    kien de TAO PHIEU DOT KE. Mot phieu chia dot da hoan tat co the da sinh ra phieu dot 2
    dang chay; keo trang thai nguoc lai chi vi mot cai file la lam chuoi dot mat can cu, va
    con so "da chi" trong installments_block tut xuong trong khi tien thi da ra khoi tai
    khoan that. Buoc 6 hoan tat bang viec CO chung tu UNC - thay dung chung tu khong lam
    viec do chua xong.

    File cu KHONG bi xoa va KHONG bi go khoi phieu (nguyen tac: khong xoa gi tren
    production). No chuyen vao `unc_superseded_files` de man hinh danh dau "da thay", va
    con nguyen trong danh sach dinh kem de doi chieu ve sau.

    Ly do BAT BUOC: day la duong sua mot ban ghi da chot va da bao cho nguoi de nghi. Khong
    co ly do thi ba thang sau khong ai biet vi sao phieu nay co hai file UNC.
    """
    engine = _engine()
    from ecentric_workspace.approval_center.shared.requests.command_service import attach_extra_files
    user = user or frappe.session.user
    doc = frappe.get_doc(BUSINESS_DT, name)
    if doc.fulfillment_status != "Completed":
        frappe.throw(_("Chỉ thay được file UNC trên phiếu đã hoàn tất. "
                       "Phiếu đang ở bước '{0}'.").format(doc.fulfillment_status or "—"))
    if not can_replace_unc(doc, user):
        frappe.throw(_("Chỉ người đã xử lý phiếu này (hoặc System Manager) mới được thay file UNC."),
                     frappe.PermissionError)
    url = str(url or "").strip()
    if not url.startswith(("/files", "/private/files")):
        frappe.throw(_("Vui lòng tải lên file UNC đúng trước khi thay."))
    cu = str(doc.completed_attachment or "").strip()
    if url == cu:
        frappe.throw(_("File mới trùng với file đang gắn — không có gì để thay."))
    reason = str(reason or "").strip()
    if len(reason) < MIN_UNC_FIX_REASON:
        frappe.throw(_("Ghi rõ lý do thay file UNC (ít nhất {0} ký tự) — lý do này vào lịch sử phiếu.")
                     .format(MIN_UNC_FIX_REASON))
    da_thay = superseded_unc_files(doc)
    if cu and cu not in da_thay:
        da_thay.append(cu)
    doc.unc_superseded_files = "\n".join(da_thay)
    doc.completed_attachment = url
    if summary is not None:
        doc.fulfillment_summary = str(summary).strip()[:500] or None
    # Nhu luc hoan tat: file duoc tai len KHONG kem doctype/docname, la File mo coi -> gan
    # vao phieu TRUOC khi save de hook attach_files cua Frappe khong tao dong thu hai.
    attach_extra_files(doc, [url])
    doc.save(ignore_permissions=True)
    # `completed_by` / `completed_at` GIU NGUYEN: viec hoan tat da xay ra that vao luc do.
    # Ai thay va thay luc nao nam o lich su phe duyet ngay duoi day.
    engine.log_action(doc.approval_request, "Commented", user,
                      comment=_("Thay file UNC (đính nhầm) — lý do: {0}").format(reason))
    engine.notify([doc.requested_by, doc.fulfillment_owner],
                  _("Đã thay file UNC ({0}): {1}").format(reason, engine.request_label(BUSINESS_DT, name)),
                  BUSINESS_DT, name)
    return {"replaced": True, "completed_attachment": url,
            "superseded": superseded_unc_files(doc)}


def unc_fix_block(business, request=None):
    """detail["extra"]["unc_fix"] — RIENG cua phieu thanh toan.

    Khong nhet vao `capabilities.derive`: ham do dung chung cho 8 form, them mot khoa chi
    mot form can vao do la keo khai niem cua rieng minh vao code chung."""
    return {"unc_fix": {
        "can_replace": can_replace_unc(business),
        "superseded": superseded_unc_files(business),
        "min_reason_len": MIN_UNC_FIX_REASON,
    }}


def detail_extra(business, request):
    """detail_extender cua phieu thanh toan: chuoi chia dot + duong thay file UNC."""
    out = dict(installments_block(business, request))
    out.update(unc_fix_block(business, request))
    return out

