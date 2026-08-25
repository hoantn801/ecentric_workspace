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
                "naming_series", "employee", "company"}
_SKIP_TYPES = {"Section Break", "Column Break", "Tab Break", "HTML", "Button", "Table",
               "Attach", "Attach Image", "Text Editor", "Code"}


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
        out.append({"label": df.label or df.fieldname, "value": value,
                    "fieldtype": df.fieldtype})
    return out


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
