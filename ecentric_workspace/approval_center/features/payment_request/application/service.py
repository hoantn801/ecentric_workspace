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
    elif legacy:
        # Older client (or historical draft) only set the legacy field -> promote it.
        doc.funding_source_doctype = "EC Purchase Request"
        doc.funding_source_name = legacy

def validate_payment(doc):
    required = ("reason", "payment_date", "payee_full_name", "account_bank", "bank_account_number",
                "has_purchase_request", "is_cost_valid", "request_attachment")
    if any(not str(doc.get(f) or "").strip() for f in required) or doc.payment_amount is None:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc (bao gồm tệp đính kèm) trước khi gửi."))
    try:
        if float(doc.payment_amount) <= 0: frappe.throw(_("Số tiền thanh toán phải lớn hơn 0."))
    except (TypeError, ValueError): frappe.throw(_("Số tiền thanh toán phải là số."))
    normalize_payment(doc)
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


def claim_fulfillment(name, user=None):
    engine = _engine()
    user = user or frappe.session.user
    if not frappe.db.exists("ToDo", {"reference_type": BUSINESS_DT, "reference_name": name,
                                     "allocated_to": user, "status": "Open"}) \
            and not engine.is_active_process_fulfiller(APPROVAL_TYPE, user) \
            and "System Manager" not in frappe.get_roles(user):
        frappe.throw(_("Bạn không thuộc nhóm Finance xử lý UNC."), frappe.PermissionError)
    # UPDATE co dieu kien: hai nguoi bam cung luc thi chi mot nguoi thang.
    frappe.db.sql(
        """update `tabEC Payment Request` set fulfillment_owner=%s, fulfillment_status='In Progress'
           where name=%s and fulfillment_status='Assigned'""", (user, name))
    if not frappe.db.sql("select 1 from `tabEC Payment Request` where name=%s and fulfillment_owner=%s",
                         (name, user)):
        frappe.throw(_("Phiếu này đã có người khác nhận xử lý."))
    doc = frappe.get_doc(BUSINESS_DT, name)
    engine.ensure_sole_todo(BUSINESS_DT, name, user, _("Finance xử lý UNC"),
                            date=getdate(doc.payment_date) if doc.payment_date else None)
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

