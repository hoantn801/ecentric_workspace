# Copyright (c) 2026, eCentric and contributors
"""API trang /khuon-mat (ec-face-photo-v1). Moi ham deu bat buoc dang nhap."""
import frappe

from ecentric_workspace.hr.face_photo import service
from ecentric_workspace.hr.face_photo.imaging import PhotoError


def _b64(s):
    import base64
    s = str(s or "")
    if "," in s[:100]:
        s = s.split(",", 1)[1]
    try:
        return base64.b64decode(s, validate=False) if s else b""
    except Exception:
        return b""


def _user():
    u = frappe.session.user
    if not u or u == "Guest":
        frappe.throw("Bạn cần đăng nhập.", frappe.PermissionError)
    return u


@frappe.whitelist(methods=["GET"])
def my_status():
    return service.status(_user())


@frappe.whitelist(methods=["POST"])
def upload(image="", consent=0, force=0):
    """`image` = data URL / base64 JPEG (trinh duyet da thu nho bang canvas).

    AI che anh -> tra {"rejected": 1, "problems": [...]} (KHONG luu). `force=1` = nguoi gui
    xac nhan anh dung -> luu, danh dau cho HR xem lai."""
    u = _user()
    raw = _b64(image)
    try:
        return service.save(u, raw, consent, force)
    except PhotoError as e:
        frappe.throw(str(e))
    except service.Forbidden as e:
        frappe.throw(str(e), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def overview():
    try:
        return service.overview(_user())
    except service.Forbidden as e:
        frappe.throw(str(e), frappe.PermissionError)


@frappe.whitelist(methods=["GET"])
def export_zip():
    try:
        data, n, total = service.build_zip(_user())
    except service.Forbidden as e:
        frappe.throw(str(e), frappe.PermissionError)
    frappe.local.response.filename = "anh_khuon_mat_%s_%d-%d.zip" % (frappe.utils.nowdate(), n, total)
    frappe.local.response.filecontent = data
    frappe.local.response.type = "download"


@frappe.whitelist(methods=["POST"])
def remind():
    try:
        return service.remind_missing(_user())
    except service.Forbidden as e:
        frappe.throw(str(e), frappe.PermissionError)
