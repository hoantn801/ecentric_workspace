# Copyright (c) 2026, eCentric and contributors
"""Cross-form actions for the 'Tất cả yêu cầu' hub.

The per-form pages expose approve/reject/claim under their own namespace
(ecentric_workspace.approval_center.api.<form>.*), which the hub cannot use because it
lists every form at once. This module resolves the form from the request itself
(EC Approval Request.approval_type -> registry definition) and delegates to the SAME
facade the form pages use, so authority, transitions and audit are unchanged -- this is a
router, never a second implementation of the rules.
"""
import frappe
from frappe import _

from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
from ecentric_workspace.approval_center.shared.registry import get_definition


def _resolve(request_name):
    """EC Approval Request name -> (definition, business_name)."""
    row = frappe.db.get_value("EC Approval Request", request_name,
                              ["approval_type", "reference_doctype", "reference_name"], as_dict=True)
    if not row or not row.approval_type or not row.reference_name:
        frappe.throw(_("Không tìm thấy yêu cầu."), frappe.DoesNotExistError)
    try:
        definition = get_definition(row.approval_type)
    except KeyError:
        frappe.throw(_("Loại yêu cầu {0} chưa được đăng ký.").format(row.approval_type))
    return definition, row.reference_name


@frappe.whitelist(methods=["POST"])
def approve(request_name, comment=None):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.approve(definition, name, comment)


@frappe.whitelist(methods=["POST"])
def reject(request_name, comment=None):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.reject(definition, name, comment)


@frappe.whitelist(methods=["POST"])
def request_information(request_name, comment=None):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.request_information(definition, name, comment)


@frappe.whitelist(methods=["POST"])
def claim_fulfillment(request_name):
    definition, name = _resolve(request_name)
    return APPROVAL_FACADE.claim_fulfillment(definition, name)

# --- chi tiết xuyên form cho popup của hub -----------------------------------------
_SKIP_FIELDS = {"name", "owner", "creation", "modified", "modified_by", "docstatus", "idx",
                "approval_request", "approval_type", "reference_key", "amended_from",
                "naming_series", "employee", "company",
                # đã hiện ở đầu popup — lặp lại chỉ làm dài thêm
                "request_title", "department", "requested_by", "requester", "requested_by_name",
                "fulfillment_status", "fulfillment_owner", "approval_status", "final_status",
                "status", "current_level", "current_level_name", "submitted_at"}
_SKIP_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table",
               "Attach", "Attach Image", "Text Editor", "Code"}

# Nhãn meta của các DocType là tiếng Anh; popup dùng chung cho 26 form nên dịch tập trung
# tại đây thay vì sửa nhãn từng DocType (đổi nhãn DocType ảnh hưởng cả Desk và báo cáo).
_LABEL_VI = {
    "Request Type": "Loại yêu cầu", "Asset Type": "Loại tài sản", "Quantity": "Số lượng",
    "Specifications": "Cấu hình / quy cách", "Justification": "Lý do",
    "Purpose of Request": "Mục đích", "Purpose (Other)": "Mục đích (khác)",
    "Requested Needed Date": "Ngày cần có", "Required Date": "Ngày cần có",
    "Needed Date": "Ngày cần có", "Start Date": "Từ ngày", "End Date": "Đến ngày",
    "Amount": "Số tiền", "Estimated Cost": "Chi phí dự kiến", "Total Amount": "Tổng tiền",
    "Budget": "Ngân sách", "Currency": "Đơn vị tiền", "Vendor": "Nhà cung cấp",
    "Supplier": "Nhà cung cấp", "Brand": "Brand", "Project": "Dự án", "Platform": "Sàn",
    "Description": "Mô tả", "Notes": "Ghi chú", "Note": "Ghi chú", "Remarks": "Ghi chú",
    "Reason": "Lý do", "Priority": "Mức ưu tiên", "Category": "Nhóm",
    "Leave Type": "Loại nghỉ", "From Date": "Từ ngày", "To Date": "Đến ngày",
    "Employee Name": "Nhân viên", "Position": "Vị trí", "Location": "Địa điểm",
    "Payment Method": "Hình thức thanh toán", "Bank Account": "Tài khoản ngân hàng",
    "Contract Type": "Loại hợp đồng", "Client": "Khách hàng", "Service": "Dịch vụ",
}
# Cặp "chọn Other rồi nhập tay": gộp thành một dòng để bớt nhiễu.
_OTHER_SUFFIX = (" (Other)", " (other)", " Other")


def _display_fields(definition, business):
    """Các trường nghiệp vụ kèm NHÃN để popup hiển thị mà không cần biết form nào.

    Hub liệt kê mọi loại yêu cầu nên không thể hard-code layout của 26 form. Lấy nhãn từ meta
    và chỉ hiện trường có giá trị; bỏ trường hệ thống, khối bố cục và Attach (đã có mục Đính
    kèm riêng). Thứ tự theo đúng thứ tự trường trong DocType nên vẫn đọc tự nhiên."""
    out = []
    try:
        meta = frappe.get_meta(definition.business_doctype)
    except Exception:
        return out
    allowed = set(getattr(definition, "editable_fields", ()) or ()) | \
              set(getattr(definition, "my_request_fields", ()) or ())
    for df in meta.fields:
        if df.fieldtype in _SKIP_TYPES or df.fieldname in _SKIP_FIELDS:
            continue
        if allowed and df.fieldname not in allowed:
            continue
        value = business.get(df.fieldname)
        if value in (None, "", 0) and df.fieldtype not in ("Check",):
            continue
        if df.fieldtype == "Check":
            value = "Có" if value else "Không"
        label = df.label or df.fieldname
        out.append({"label": _LABEL_VI.get(label, label), "value": value,
                    "fieldtype": df.fieldtype, "raw_label": label})
    return _merge_other_pairs(out)


def _merge_other_pairs(fields):
    """Gộp 'Purpose of Request: Other' + 'Purpose (Other): Trả laptop' thành một dòng.

    Form nào có Select kèm ô nhập tay đều sinh ra 2 dòng, trong đó dòng đầu chỉ nói 'Other'
    — không mang thông tin. Nhãn hai trường thường không trùng hẳn ('Purpose of Request' vs
    'Purpose (Other)') nên khớp theo tiền tố, và chỉ gộp khi trường gốc đúng là 'Other'."""
    drop = set()
    for extra in fields:
        raw = (extra.get("raw_label") or "").strip()
        prefix = ""
        for suffix in _OTHER_SUFFIX:
            if raw.endswith(suffix):
                prefix = raw[: -len(suffix)].strip()
                break
        if not prefix:
            continue
        for base in fields:
            if base is extra or not (base.get("raw_label") or "").startswith(prefix):
                continue
            if str(base.get("value")).strip().lower() not in ("other", "khác", "khac"):
                continue
            base["value"] = extra.get("value")
            drop.add(id(extra))
            break
    return [f for f in fields if id(f) not in drop]


@frappe.whitelist()
def get_request_detail(request_name):
    """Chi tiết một yêu cầu bất kỳ cho popup trên trang 'Tất cả yêu cầu'.

    Router thuần: resolve loại yêu cầu -> gọi ĐÚNG facade.detail của form đó (đã kiểm quyền
    xem bên trong), rồi bổ sung display_fields + đường dẫn mở trang đầy đủ."""
    definition, name = _resolve(request_name)
    data = APPROVAL_FACADE.detail(definition, name) or {}
    data["display_fields"] = _display_fields(definition, data.get("business") or {})
    data["business_name"] = name
    data["type_title"] = frappe.db.get_value("EC Approval Type", definition.code, "approval_title") \
        or definition.code
    route = frappe.db.get_value("EC Approval Type", definition.code, "route")
    if route:
        data["detail_route"] = ("/" + route.lstrip("/")) + "?id=" + name
    return data
