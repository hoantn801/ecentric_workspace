"""Stable compatibility API backed by the shared request application layer."""
import json

import frappe

from ecentric_workspace.approval_center.shared.api_adapter import bind

globals().update(bind("CONTRACT_REVIEW"))

_DT = "EC Contract Review Request"
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
    """Dữ liệu hợp đồng gốc để tự điền + đối chiếu highlight phía form."""
    row = frappe.db.get_value(_DT, name, _FILL_FIELDS, as_dict=True)
    if not row:
        frappe.throw(frappe._("Không tìm thấy hợp đồng gốc."))
    return row
