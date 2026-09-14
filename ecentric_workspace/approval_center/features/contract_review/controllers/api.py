"""Stable compatibility API backed by the shared request application layer."""
import json

import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind
from ecentric_workspace.approval_center.shared.workflow.permissions import can_view_request

globals().update(bind("CONTRACT_REVIEW"))

_DT = "EC Contract Review Request"
_CODE = "CONTRACT_REVIEW"
_FILL_FIELDS = ["name", "request_title", "contract_type", "request_type", "brand",
                "justification", "contract_value", "contract_start_date",
                "contract_end_date", "request_details"]


@frappe.whitelist()
def search_previous_contracts(query=None):
    """Hợp đồng đã DUYỆT XONG của chính người dùng (hoặc mọi người nếu là SM) để chọn làm
    gốc điều chỉnh. Chỉ trả bản đã Approved — điều chỉnh một bản đang chờ duyệt là vô nghĩa."""
    user = frappe.session.user
    filters = [["approval_request", "is", "set"]]
    if "System Manager" not in frappe.get_roles(user):
        filters.append(["requested_by", "=", user])
    if query:
        filters.append(["request_title", "like", "%%%s%%" % query])
    rows = frappe.get_all(_DT, filters=filters,
                          fields=["name", "request_title", "brand", "contract_value",
                                  "approval_request"],
                          order_by="modified desc", limit_page_length=100)
    req_names = [r.approval_request for r in rows if r.approval_request]
    approved = set()
    if req_names:
        approved = {r.name for r in frappe.get_all(
            "EC Approval Request",
            filters={"name": ["in", req_names], "approval_status": "Approved"},
            fields=["name"])}
    out = [r for r in rows if r.approval_request in approved][:20]
    return {"rows": [{"value": r.name,
                      "label": "%s — %s (%s)" % (r.name, r.request_title or "", r.brand or "")}
                     for r in out]}


@frappe.whitelist()
def get_previous_contract(name):
    """Dữ liệu hợp đồng gốc để tự điền + đối chiếu highlight phía form.

    PHẢI kiểm quyền THỦ CÔNG. frappe.db.get_value bỏ qua toàn bộ permission, mà mã hồ sơ
    chạy TUẦN TỰ (EC-CTR-2026-00001, 00002...) — không kiểm thì bất kỳ nhân viên nào đã
    đăng nhập cũng đổi số trên URL để đọc hết giá trị + điều khoản hợp đồng của mọi phòng.
    Đúng lớp lỗi đã siết cho Đề nghị thanh toán 01/09 (xem chú thích dài trong
    workflow/permissions.py). Dùng hàm kiểm quyền CHUẨN của engine, không tự chế luật thứ hai."""
    row = frappe.db.get_value(
        _DT, name, _FILL_FIELDS + ["requested_by", "approval_request"], as_dict=True)
    if not row:
        frappe.throw(frappe._("Không tìm thấy hợp đồng gốc."))
    if not can_view_request(row.get("approval_request"), business_doctype=_DT,
                            requested_by=row.get("requested_by"),
                            approval_type=_CODE, business_name=name):
        frappe.throw(frappe._("Bạn không có quyền xem hợp đồng này."), frappe.PermissionError)
    # Hai trường này chỉ dùng để kiểm quyền, không đưa ra ngoài.
    row.pop("requested_by", None)
    row.pop("approval_request", None)
    return row
