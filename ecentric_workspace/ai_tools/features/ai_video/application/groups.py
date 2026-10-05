# Copyright (c) 2026, eCentric and contributors
"""Prompt theo NHOM san pham (05/10/2026). Quan tri (role EC AI Video Admin) sua vai cau
them vao prompt chung cho tung nhom (sua hop/vi, sua lon, chai...); worker luu ban + lich su.
Nguoi lam lo chi xem va gui "yeu cau nhom moi" -> tao viec (ToDo) cho quan tri.

Noi dung nhom chi la phan THEM vao prompt chung, khong thay the: sai cung khong pha luong."""

import frappe

from ecentric_workspace.ai_tools.features.ai_video.application import service as svc
from ecentric_workspace.ai_tools.features.ai_video.domain import flow
from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client as wc

ADMIN_ROLE = "EC AI Video Admin"
REQUEST_FIELDS = {"name": 80, "sku": 140, "hold": 600, "ref": 300}


def groups_get():
    r = wc.call("groups_get")
    return {"groups": r.get("groups") or {}, "history": r.get("history") or {}, "can_edit": svc.is_admin()}


def _cat(cat):
    if cat not in flow.CATEGORIES:
        raise frappe.ValidationError("Nhóm sản phẩm không hợp lệ.")
    return cat


def groups_set(data):
    svc.check_admin()
    d = svc._j(data)
    if not isinstance(d, dict) or not isinstance(d.get("data") or {}, dict):
        raise frappe.ValidationError("Dữ liệu nhóm không hợp lệ.")
    cat = _cat(d.get("cat"))
    try:
        clean = flow.clean_group(d.get("data") or {})
    except ValueError as e:
        raise frappe.ValidationError(str(e))
    return wc.call("groups_set", cat=cat, data=clean, by=frappe.session.user, note=str(d.get("note") or "")[:200])


def groups_rollback(cat, v):
    svc.check_admin()
    try:
        v = int(v)
    except (TypeError, ValueError):
        raise frappe.ValidationError("Phiên bản không hợp lệ.")
    return wc.call("groups_rollback", cat=_cat(cat), v=v, by=frappe.session.user)


def _admins():
    users = frappe.get_all("Has Role", filters={"role": ADMIN_ROLE, "parenttype": "User"}, pluck="parent")
    users = [u for u in users if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")]
    return sorted(set(users))


def group_request(data):
    """Bat ky ai co quyen trang: gui yeu cau nhom moi -> 1 ToDo cho moi quan tri."""
    d = svc._j(data)
    if not isinstance(d, dict):
        raise frappe.ValidationError("Dữ liệu yêu cầu không hợp lệ.")
    f = {k: str(d.get(k) or "").strip()[:n] for k, n in REQUEST_FIELDS.items()}
    if not f["name"] or not f["hold"]:
        raise frappe.ValidationError("Cần tên nhóm và mô tả cách cầm.")
    admins = _admins()
    if not admins:
        raise frappe.ValidationError("Chưa có ai giữ role %s để nhận yêu cầu. Báo IT gán role trước." % ADMIN_ROLE)
    desc = ("<b>[AI Video] Yêu cầu nhóm sản phẩm mới</b><br>Nhóm: %s<br>SKU mẫu: %s<br>Cách cầm mong muốn: %s<br>"
            "Tham khảo: %s<br>Người gửi: %s") % tuple(frappe.utils.escape_html(x) for x in (
                f["name"], f["sku"] or "-", f["hold"], f["ref"] or "-", frappe.session.user))
    for u in admins:
        frappe.get_doc({"doctype": "ToDo", "allocated_to": u, "description": desc, "priority": "Medium",
                        "status": "Open", "assigned_by": frappe.session.user}).insert(ignore_permissions=True)
    return {"sent_to": len(admins)}
