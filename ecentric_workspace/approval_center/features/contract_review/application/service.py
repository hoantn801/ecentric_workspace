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

from ecentric_workspace.approval_center.shared.workflow import transitions as engine

BUSINESS_DT = "EC Contract Review Request"
APPROVAL_TYPE = "CONTRACT_REVIEW"
CEO_LEVEL_NO = 4

MATERIAL_FIELDS = ["request_kind", "previous_request", "contract_type", "request_type",
                   "brand", "justification", "contract_value", "contract_start_date",
                   "contract_end_date", "request_details"]
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
    vals = {f: str(doc.get(f) or "") for f in MATERIAL_FIELDS}
    return hashlib.sha1(json.dumps(vals, sort_keys=True).encode("utf-8")).hexdigest()


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
    if doc.request_kind == "Existing" and not doc.previous_request:
        frappe.throw(_("Vui lòng chọn hợp đồng sẵn có cần điều chỉnh."))
    if doc.contract_start_date and doc.contract_end_date \
            and str(doc.contract_end_date) < str(doc.contract_start_date):
        frappe.throw(_("Ngày kết thúc hợp đồng phải sau ngày bắt đầu."))

    changed = []
    if doc.previous_request:
        prev = frappe.db.get_value(BUSINESS_DT, doc.previous_request, DIFF_FIELDS, as_dict=True)
        if not prev:
            frappe.throw(_("Không tìm thấy hợp đồng gốc đã chọn."))
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
    return req_name


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


@frappe.whitelist(methods=["POST"])
def resubmit(name, actor=None):
    doc = frappe.get_doc(BUSINESS_DT, name)
    if not doc.approval_request:
        frappe.throw(_("Yêu cầu chưa được gửi."))
    new_sig = _signature(doc)
    material_changed = new_sig != (doc.material_signature or "")
    engine.resubmit(doc.approval_request, actor=actor or frappe.session.user, restart=material_changed)
    frappe.db.set_value(BUSINESS_DT, doc.name, "material_signature", new_sig)
    return {"restarted": material_changed}
