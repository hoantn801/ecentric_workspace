# Copyright (c) 2026, eCentric and contributors
"""Contract Review orchestration over the shared engine (thay SharePoint Contract approval).

4 cấp: L1 Trưởng phòng (động theo department) -> L2 Finance Team -> L3 HOF -> L4 CEO.
request_kind quyết định số cấp — Hoàn chốt 2026-09-01: hợp đồng SẴN CÓ chỉ điều chỉnh
(số tiền / thời hạn / chi tiết) thì KHÔNG cần CEO duyệt, CEO chỉ nhận thông báo (CC);
hợp đồng hoặc phụ lục MỚI, hoặc sẵn-có-nhưng-đổi-nội-dung, đi đủ 4 cấp.
Deadline phản hồi tự tính theo ngày làm việc: sẵn có 1 ngày, mới 3 ngày.
No fulfillment (v1) — phần sign-off làm đợt sau."""
import hashlib
import json

import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.approval_center.features.contract_review.domain import esign_flow, kol
from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Contract Review Request"
APPROVAL_TYPE = "CONTRACT_REVIEW"
CEO_LEVEL_NO = 4

MATERIAL_FIELDS = ["request_kind", "previous_request", "contract_type", "request_type",
                   "brand", "justification", "contract_value", "contract_start_date",
                   "contract_end_date", "request_details"]
# `esign_flow` (quy trinh ky) KHONG nam trong chu ky: no khong doi noi dung da duyet, va them vao thi
# moi phieu cu (chu ky tinh khi chua co truong) gui lai deu bi duyet lai tu dau.
# KOL/KOC: doi creator / SO / tien / coc khi gui lai = duyet lai tu dau. CHI cong vao chu ky
# cua phieu KOL - cong cho moi phieu thi chu ky cua phieu cu dang "Can bo sung" doi theo va
# bi duyet lai tu dau du khong ai sua gi.
KOL_MATERIAL_FIELDS = ["sales_order", "creator", "payable_amount", "advance_amount",
                       "payment_schedule", "contract_file", "request_attachment",
                       "payment_term_days", "amount_type", "pit_rate", "vat_rate", "contract_date",
                       # Nguoi nhan link ky phia doi tac: doi email sau khi duyet = ky boi nguoi khac
                       # (QC 15/11 B-04). Chi phieu KOL (moi chay tu 12/11) nen khong lam phieu cu duyet lai.
                       "partner_signer_email"]
REQUIRED_AT_SUBMIT = ["request_title", "request_kind", "contract_type", "request_type",
                      "brand", "justification", "contract_value", "request_details"]
# Trường được phép lệch so với hợp đồng gốc mà vẫn coi là "chỉ điều chỉnh" (bỏ cấp CEO).
# Đổi bất kỳ trường NGOÀI danh sách này (loại HĐ, brand, mục đích...) = đổi nội dung -> đủ 4 cấp.
ADJUST_ONLY_FIELDS = {"contract_value", "contract_start_date", "contract_end_date",
                      "request_details", "request_title", "cc_to", "request_attachment"}
# So sánh với bản gốc trên các trường nghiệp vụ này (để highlight cho Finance + xét bỏ cấp).
DIFF_FIELDS = ["contract_type", "request_type", "brand", "justification", "contract_value",
               "contract_start_date", "contract_end_date", "request_details"]
RESPONSE_DAYS = {"Existing": 1, "New": 3}


def _signature(doc):
    fields = MATERIAL_FIELDS + (KOL_MATERIAL_FIELDS if kol.is_kol(doc) else [])
    vals = {f: str(doc.get(f) or "") for f in fields}
    if not kol.is_kol(doc):
        # PO 17/11: phieu thuong doi / them / bo tep hop dong luc bo sung = duyet lai tu dau. Chi tep
        # NGUOI GUI tai (tep he thong: ban ky, ban doi chung, tep nguoi duyet them - chu khac). KOL da
        # co contract_file / request_attachment trong chu ky rieng.
        vals["__files"] = ",".join(_requester_files(doc))
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


#: Tep he thong tao duoi ten nguoi dung (ban ky / ban review cua nen tang ky, ban doi chung SharePoint
#: chup duoi ten nguoi vua quyet dinh - co the chinh la nguoi lap neu ho cung duyet mot cap): KHONG tinh.
_SYSTEM_FILE_PREFIXES = ("SIGNED-", "REVIEW-", "[Đối chứng]")


def _requester_files(doc):
    if not doc.get("name") or not doc.get("requested_by"):
        return []
    rows = frappe.get_all("File", filters={"attached_to_doctype": BUSINESS_DT, "attached_to_name": doc.name,
                                           "owner": doc.requested_by},
                          fields=["file_url", "file_name"], limit_page_length=0, ignore_permissions=True)
    return sorted({r.get("file_url") for r in rows
                   if r.get("file_url") and not str(r.get("file_name") or "").startswith(_SYSTEM_FILE_PREFIXES)})


def _requester_context(user):
    return frappe.db.get_value("Employee", {"user_id": user},
                               ["name", "department", "company"], as_dict=True)


def changed_vs_previous(doc, prev):
    """Trường nghiệp vụ lệch so với hợp đồng gốc — nguồn duy nhất cho cả highlight lẫn xét bỏ cấp."""
    return [f for f in DIFF_FIELDS if str(doc.get(f) or "") != str(prev.get(f) or "")]


def skip_ceo(doc, changed):
    """CEO chỉ CC khi là hợp đồng sẵn có VÀ mọi thay đổi đều thuộc nhóm điều chỉnh."""
    if doc.get("request_kind") != "Existing" or not doc.get("previous_request"):
        return False
    if kol.is_kol(doc):
        # KOL: doi creator / so tien tra / coc nam ngoai DIFF_FIELDS -> "chi dieu chinh" lach CEO
        # duoc (QC 15/11 R1). Phu luc KOL chua co thiet ke rieng: luon du 4 cap.
        return False
    return all(f in ADJUST_ONLY_FIELDS for f in changed)


def business_deadline(kind, start=None):
    """Hạn phản hồi theo NGÀY LÀM VIỆC (bỏ T7/CN): sẵn có 1 ngày, mới 3 ngày."""
    from datetime import timedelta
    d = (start or now_datetime()).date()
    left = RESPONSE_DAYS.get(kind, 3)
    while left > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            left -= 1
    return d


def _require_approved_previous(previous_request, user=None):
    """Hợp đồng gốc phải là bản ĐÃ DUYỆT — chốt ở server (BUG-4, E2E 01/09).

    Ô tìm kiếm trên form chỉ trả bản Approved, nhưng API nhận chuỗi bất kỳ: trỏ vào
    bản nháp tự tạo là ghép được luồng 3 cấp không CEO cho nội dung chưa ai duyệt."""
    row = frappe.db.get_value(BUSINESS_DT, previous_request, ["approval_request", "requested_by"],
                              as_dict=True) or {}
    req = row.get("approval_request")
    status = req and frappe.db.get_value("EC Approval Request", req, "approval_status")
    if status != "Approved":
        frappe.throw(_("Hợp đồng gốc phải là yêu cầu đã được duyệt xong."))
    # Cung luat xem voi get_previous_contract: goi thang API khong lay duoc HD phong khac lam goc (R1).
    from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request
    if not can_view_request(req, user=user or frappe.session.user, business_doctype=BUSINESS_DT,
                            requested_by=row.get("requested_by"), approval_type=APPROVAL_TYPE,
                            business_name=previous_request):
        frappe.throw(_("Bạn không có quyền dùng hợp đồng gốc này."), frappe.PermissionError)


def _check_submittable(doc):
    """Chot chung cua submit VA resubmit (QC 15/11 B-02: truoc do gui lai sau "Can bo sung" bo qua
    het - xoa trang ly do / quy trinh ky / brand, hay doi KOL -> Mua vao van qua)."""
    esign_flow.apply_default(doc)
    esign_flow.clean_labor(doc)
    if not doc.get("esign_flow"):
        # Nen tang ky so chon ho so theo truong nay (chot 12/11): loai khong co mac dinh phai chon
        # luc gui duyet - sau khi duyet xong phieu khoa, khong con cho chon (QC7).
        frappe.throw(_("Chọn Quy trình ký (chọn \"Không ký trên cổng\" nếu ký ngoài)."))
    # Hop dong lao dong (12/11): khong gan brand, khong bat nhap gia tri (luong nam trong tep).
    need = [f for f in REQUIRED_AT_SUBMIT
            if not (f == "brand" and not esign_flow.needs_brand(doc.get("contract_type")))
            and not (f == "contract_value" and not esign_flow.needs_value(doc.get("contract_type")))]
    missing = [f for f in need if not doc.get(f)]
    if missing:
        frappe.throw(_("Vui lòng nhập đầy đủ các trường bắt buộc trước khi gửi."))
    if doc.request_kind == "Existing" and not doc.previous_request:
        frappe.throw(_("Vui lòng chọn hợp đồng sẵn có cần điều chỉnh."))
    if doc.contract_start_date and doc.contract_end_date \
            and str(doc.contract_end_date) < str(doc.contract_start_date):
        frappe.throw(_("Ngày kết thúc hợp đồng phải sau ngày bắt đầu."))


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
    if kol.is_kol(doc):
        # Hop dong KOL/KOC (11/11/2026): tinh lai tien, chot so HD, canh bao doanh thu SO.
        # Nap tre: module KOL keo creator repository + lookup, phieu thuong khong can.
        from ecentric_workspace.approval_center.features.contract_review.application import kol_service
        kol_service.validate_submit(doc)
    _check_submittable(doc)

    changed = []
    if doc.previous_request:
        prev = frappe.db.get_value(BUSINESS_DT, doc.previous_request, DIFF_FIELDS, as_dict=True)
        if not prev:
            frappe.throw(_("Không tìm thấy hợp đồng gốc đã chọn."))
        _require_approved_previous(doc.previous_request)
        changed = changed_vs_previous(doc, prev)
    doc.changed_fields = json.dumps(changed)
    doc.expected_response_date = business_deadline(doc.request_kind)
    doc.submitted_at = now_datetime()
    doc.material_signature = _signature(doc)
    doc.save(ignore_permissions=True)

    skip = skip_ceo(doc, changed)
    req_name = engine.submit(
        BUSINESS_DT, doc.name, APPROVAL_TYPE, user,
        skip_level_nos=(CEO_LEVEL_NO,) if skip else None,
        skip_reason="Hợp đồng sẵn có, chỉ điều chỉnh — CEO nhận thông báo, không cần duyệt" if skip else None)
    frappe.db.set_value(BUSINESS_DT, doc.name, "approval_request", req_name)
    if skip:
        _notify_ceo_cc(req_name, doc)
    _soi_guong_sharepoint(doc.name)
    return req_name


def _soi_guong_sharepoint(name):
    """Dua dinh kem len SharePoint de nguoi duyet mo bang Word Online.

    CHAY NEN, va nuot moi loi: Microsoft co su co thi phieu VAN phai gui duoc. Nguoi dung da
    bam gui va da thay ket qua - khong co ly do gi de mot lan goi mang ra ngoai bien cong ty
    lam hong giao dich do. Hong thi tep van con nguyen trong Frappe, va chay lai `dong_bo_phieu`
    la khoi phuc duoc (ham do idempotent).

    Cung la ly do dung `enqueue` chu khong goi thang: tai mot tep .docx vai MB len Graph co the
    mat vai giay, nhan len so tep thi man hinh gui phieu treo bang do."""
    if _is_labor(name):
        return
    try:
        frappe.enqueue(
            "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror.dong_bo_nen",
            queue="long", business_doctype=BUSINESS_DT, business_name=name,
            # SAU commit (09/10/2026): truoc day job chay ngay, doc phieu khi `approval_request`
            # chua ghi xong -> chi cap quyen cho nguoi gui. EC-CTR-2026-00036: 8 nguoi duyet
            # bam "Mo online" deu an "You need access".
            enqueue_after_commit=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "enqueue soi guong SharePoint %s" % name)


#: Loai hop dong KHONG dua len thu vien SharePoint chung (nhom Operation Members ghi duoc):
#: lao dong mang luong (QC7) + KOL/KOC mang CCCD/STK creator (PO 17/11, quyet dinh B).
_KHONG_LEN_SHAREPOINT = (esign_flow.LABOR_CONTRACT_TYPE, esign_flow.KOL_CONTRACT_TYPE)


def _is_labor(name):
    """Hop dong mang du lieu rieng tu (lao dong / KOL): KHONG dua len thu vien SharePoint chung.
    Nguoi duyet mo tep tren ERP. Ten ham giu nguyen cho cac test/goi cu.
    Loi khi hoi -> coi nhu KHONG duoc len (fail-closed: thieu ban Word Online con hon lo CCCD)."""
    try:
        return frappe.db.get_value(BUSINESS_DT, name, "contract_type") in _KHONG_LEN_SHAREPOINT
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SharePoint: khong hoi duoc loai hop dong %s" % name)
        return True


def on_decision(name, approval_request, approval_action, action):
    """Nguoi nghe quyet dinh cua engine (`transitions._DECISION_OBSERVERS`), 16/10/2026.

    Moi lan Duyet / Tu choi / Yeu cau bo sung / hoan tat duyet: chup lai tep hop dong tren
    SharePoint NGUYEN TRANG luc do (ban doi chung). Ly do + thiet ke: docstring dau
    `shared/integrations/sharepoint_snapshot.py`.

    Chay GIUA giao dich duyet nen CHI xep viec: tai tep tu Graph mat vai giay, va mot su co cua
    Microsoft khong duoc lam hong lan duyet. SAU commit: job doc dong EC Approval Action vua ghi
    - chay truoc commit thi dong do chua ton tai. Giao dich rollback thi Frappe huy luon viec
    da xep, khong co ban chup ma."""
    if _is_labor(name):
        return
    try:
        frappe.enqueue(
            "ecentric_workspace.approval_center.shared.integrations.sharepoint_snapshot.chup_nen",
            queue="long", approval_action=approval_action, enqueue_after_commit=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "enqueue ban doi chung %s" % name)


def _notify_ceo_cc(req_name, doc):
    """CEO vẫn phải BIẾT về điều chỉnh dù không duyệt — gửi qua đúng pipeline thông báo
    (in-app + Teams) mà engine dùng, không tự chế kênh riêng. Lỗi thông báo không được
    làm hỏng việc gửi yêu cầu."""
    try:
        ceo = _process_level_users(doc, CEO_LEVEL_NO)
        if ceo:
            # Cap quyen doc TRUOC khi gui link, neu khong thi thong bao co ma quyen
            # khong co: cap CEO bi loai khoi snapshot (`skip_level_nos`) nen KHONG co
            # dong `EC Approval Request Approver` nao, ma `permissions.can_view_request`
            # chi cong nhan bon tu cach - System Manager / nguoi de nghi / approver CO
            # DONG / fulfiller. "Participant cua Approval Process" khong tinh. Ket qua:
            # CEO bam vao deep link trong DM la 403.
            # `_engine_grant_read` la dung ham dung cho viec nay: chia se doc CHI mot
            # chung tu nay, khong dung ToDo (CEO khong phai lam gi - day la ban CC).
            for u in ceo:
                engine._engine_grant_read(BUSINESS_DT, doc.name, u)
            engine.notify(ceo, _("[CC] Điều chỉnh hợp đồng: {0}").format(doc.request_title),
                          BUSINESS_DT, doc.name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "contract_review ceo cc notify failed")


def _process_level_users(doc, level_no):
    process = engine.resolve_process(APPROVAL_TYPE, None)
    for lvl in engine.resolve_levels(process.name):
        if lvl.level_no == level_no:
            users = engine.resolve_participants(
                [p for p in lvl.participants if p.participant_purpose == "Approver"],
                doc.requested_by,
                context={"reference_doctype": BUSINESS_DT, "reference_name": doc.name})
            return [u for u, _label in users]
    return []


def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    _guard_resubmit_needs_ceo(doc)
    if kol.is_kol(doc):
        # Gui lai sau "Can bo sung" cung qua DUNG phep chot nhu luc gui: tinh lai tien, sinh lai
        # hop dong neu du lieu doi, canh bao doanh thu SO (QC 11/11 - truoc do bo qua het).
        from ecentric_workspace.approval_center.features.contract_review.application import kol_service
        kol_service.validate_submit(doc)
    _check_submittable(doc)
    doc.save(ignore_permissions=True)
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    res = engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    # Gui lai thuong di kem THAY tep dinh kem - phai soi guong lai, neu khong nguoi duyet se
    # mo ra ban cu tren SharePoint trong khi ERP da co ban moi.
    _soi_guong_sharepoint(doc.name)
    # Tra ca ket qua ky so cua engine cho lop tren (QC 15/11 B-12 - truoc do bo mat).
    return {"restarted": material_changed, "esign": res.get("esign") if isinstance(res, dict) else None}


def _guard_resubmit_needs_ceo(doc):
    """Chặn lách CEO qua resubmit (BUG-3, E2E 01/09 — đã tái hiện được trên prod).

    Snapshot cấp duyệt chốt LÚC GỬI; engine.resubmit chỉ reset các cấp có sẵn, không dựng
    lại. Hồ sơ gửi dạng 'chỉ điều chỉnh' (3 cấp) mà lúc bổ sung lại đổi NỘI DUNG (brand,
    loại HĐ, mục đích...) thì bây giờ CẦN CEO nhưng snapshot không có cấp 4 -> nếu cho qua,
    hồ sơ đổi nội dung sẽ được duyệt xong không bao giờ tới CEO.
    Chiều ngược (snapshot có CEO nhưng giờ hết cần) vô hại — CEO duyệt thừa còn hơn thiếu."""
    changed = []
    if doc.previous_request:
        # previous_request sua duoc luc bo sung: doi sang phieu nhap / phong khac co noi dung giong het la
        # "khong doi gi" -> lach CEO (QC 15/11 vong 4). Cung chot voi luc gui.
        _require_approved_previous(doc.previous_request)
        prev = frappe.db.get_value(BUSINESS_DT, doc.previous_request, DIFF_FIELDS, as_dict=True)
        if prev:
            changed = changed_vs_previous(doc, prev)
        # Chi gan len doc: resubmit luu doc ngay sau. Ghi thang DB o day doi `modified` -> doc.save() sau do
        # nem TimestampMismatchError (QC 15/11 vong 2).
        doc.changed_fields = json.dumps(changed)
    needs_ceo = not skip_ceo(doc, changed)
    if not needs_ceo:
        return
    has_ceo_level = bool(frappe.db.exists(
        "EC Approval Request Level",
        {"approval_request": doc.approval_request, "level_no": CEO_LEVEL_NO}))
    if not has_ceo_level and kol.is_kol(doc):
        frappe.throw(_("Hợp đồng KOL/KOC điều chỉnh nay phải qua CEO duyệt, nhưng yêu cầu này đã gửi theo luồng "
                       "không có cấp CEO. Vui lòng hủy yêu cầu này và tạo yêu cầu mới."))
    if not has_ceo_level:
        frappe.throw(_(
            "Thay đổi này đụng đến nội dung hợp đồng (loại hợp đồng / brand / mục đích) nên "
            "cần CEO duyệt, nhưng yêu cầu này đã gửi theo luồng điều chỉnh không có cấp CEO. "
            "Vui lòng hủy yêu cầu này và tạo yêu cầu mới."))
