# Copyright (c) 2026, eCentric and contributors
"""Cua HTTP DUY NHAT cua Thu vien tai lieu ISO. Moi ham:
  * lay nguoi dung tu PHIEN - khong nhan tham so `user`;
  * ghi bang POST;
  * tra {success, message, data}; loi nguoi dung -> success False + thong diep doc duoc.
Doc trang thi di qua www/tai_lieu/*.py (server ve san), khong qua day.
"""
import base64
import json

import frappe

from ecentric_workspace.iso_docs import manage as M
from ecentric_workspace.iso_docs.errors import DocError, Forbidden, NotFound


def _ok(data=None, message=""):
    return {"success": True, "message": message, "data": data}


def _fail(message, status=None):
    try:
        frappe.db.rollback()
    except Exception:
        pass
    if status:
        frappe.local.response["http_status_code"] = status
    return {"success": False, "message": message, "data": None}


def _run(fn, *args, **kwargs):
    try:
        return _ok(fn(*args, **kwargs))
    except Forbidden as e:
        return _fail(str(e) or "Bạn không có quyền làm việc này.", 403)
    except NotFound:
        return _fail("Không tìm thấy tài liệu.", 404)
    except DocError as e:
        return _fail(str(e))
    except frappe.PermissionError:
        frappe.clear_last_message()
        return _fail("Bạn không có quyền làm việc này.", 403)
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        return _fail(str(e).replace("<br>", "\n"))


def _blob(f):
    """{name, data: base64} -> {name, content} | None."""
    if not f:
        return None
    if not isinstance(f, dict):
        raise DocError("Tệp không hợp lệ.")
    try:
        content = base64.b64decode((f.get("data") or "").split(",")[-1], validate=True)
    except (ValueError, TypeError):
        raise DocError("Tệp %s không đọc được." % (f.get("name") or "?"))
    return {"name": str(f.get("name") or "tep"), "content": content}


@frappe.whitelist(methods=["POST"])
def action(code, action, note=""):
    """Bam mot buoc Workflow (Gui / Dong y / Tra lai / Ban hanh / ...). Tra lai bat buoc co ly do."""
    return _run(M.do_action, frappe.session.user, str(code or ""), str(action or ""), str(note or ""))


def _import(data):
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except ValueError:
            raise DocError("Dữ liệu gửi lên không hợp lệ.")
    if not isinstance(data, dict):
        raise DocError("Dữ liệu gửi lên không hợp lệ.")
    forms = [_blob(f) for f in data.get("forms") or []]
    return M.import_package(frappe.session.user, data.get("goi") or "", str(data.get("code") or ""),
                            _blob(data.get("pdf")), _blob(data.get("docx")), [f for f in forms if f])


@frappe.whitelist(methods=["POST"])
def import_package(data):
    """Nhap goi tu chat Claude. data = JSON {goi: noi dung goi.json, code, pdf, docx, forms: [{name, data}]}.
    Chi Ban ISO / TGD / SM. Tao hoac ghi de BAN NHAP, khong ban hanh."""
    return _run(_import, data)
