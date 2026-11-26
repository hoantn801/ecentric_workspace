# Copyright (c) 2026, eCentric and contributors
"""API Cong cu dung chung - NOI DUY NHAT co @frappe.whitelist().

Moi ham: Ctx tu phien (KHONG nhan user tu tham so) -> service -> envelope {success, message, data}.
Trang /kalodata goi qua window.ecApi: GET de doc, POST cho ghi. Loi nghiep vu (QueueError) ->
success=false + thong diep tieng Viet; loi la -> rollback + Error Log + thong diep chung.
URL dang nhap Kalodata (open) chi nam trong response cua chinh nguoi bam, khong ghi log.
"""
import frappe

from ecentric_workspace.shared_tools import constants as C
from ecentric_workspace.shared_tools import exports as X
from ecentric_workspace.shared_tools import queue_rules as Q
from ecentric_workspace.shared_tools import service as S
from ecentric_workspace.shared_tools import views as V

MSG_UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."
MSG_LOGIN = "Bạn cần đăng nhập."


def _ctx():
    user = frappe.session.user
    if not user or user == "Guest":
        raise frappe.PermissionError(MSG_LOGIN)
    return S.Ctx(user, frappe.get_roles(user))


def _key(tool):
    return str(tool or C.TOOL_KALODATA).strip().lower()[:40]


def _run(fn):
    try:
        return {"success": True, "message": "", "data": fn(_ctx())}
    except Q.QueueError as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": None}
    except frappe.PermissionError:
        frappe.db.rollback()
        return {"success": False, "message": MSG_LOGIN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="shared_tools api")
        return {"success": False, "message": MSG_UNKNOWN, "data": None}


@frappe.whitelist(methods=["GET"])
def state(tool=None):
    return _run(lambda c: V.state(c, _key(tool)))


@frappe.whitelist(methods=["POST"])
def join(tool=None):
    return _run(lambda c: S.join(c, _key(tool)) and V.state(c, _key(tool)))


@frappe.whitelist(methods=["POST"])
def leave(tool=None):
    return _run(lambda c: S.leave(c, _key(tool)) and V.state(c, _key(tool)))


@frappe.whitelist(methods=["POST"])
def open_link(tool=None):
    return _run(lambda c: {"url": S.open_link(c, _key(tool))})


@frappe.whitelist(methods=["POST"])
def extend(tool=None):
    return _run(lambda c: S.extend(c, _key(tool)) and V.state(c, _key(tool)))


@frappe.whitelist(methods=["POST"])
def force_end(entry, tool=None):
    return _run(lambda c: S.force_end(c, _key(tool), str(entry or "")[:140]) and V.state(c, _key(tool)))


@frappe.whitelist(methods=["GET"])
def download(name):
    """Tra file truc tiep (khong envelope). Loi -> trang loi ngan, khong lo traceback."""
    try:
        fname, content = X.download(_ctx(), str(name or "")[:140])
    except (Q.QueueError, frappe.PermissionError) as e:
        frappe.db.rollback()
        frappe.throw(str(e) if isinstance(e, Q.QueueError) else MSG_LOGIN, frappe.PermissionError)
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
