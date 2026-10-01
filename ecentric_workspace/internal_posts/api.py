# Copyright (c) 2026, eCentric and contributors
"""Cua HTTP DUY NHAT cua Tin noi bo. Moi ham:
  * lay nguoi dung tu PHIEN - khong nhan tham so `user` (A66 §7: whitelist + tham so nguoi
    thao tac = mao danh duoc);
  * ghi bang POST (GET cua Frappe khong commit);
  * tra {success, message, data} - loi nguoi dung (thieu truong, het luot AI, khong co quyen)
    la success False + thong diep doc duoc, khong de traceback lot ra trinh duyet.
"""
import json

import frappe
from frappe import _

from ecentric_workspace.internal_posts import cover_ai, editor_service, service
from ecentric_workspace.internal_posts.service import Forbidden, NotFound, PostError


def _ok(data=None, message=""):
    return {"success": True, "message": message, "data": data}


def _fail(message, status=None):
    # Loi giua chung -> bo moi ghi do dang cua request nay (Frappe commit cuoi request POST
    # thanh cong, ma ham nay "thanh cong" ve mat HTTP).
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
        return _fail(str(e) or _("Bạn không có quyền làm việc này."), 403)
    except NotFound:
        return _fail(_("Không tìm thấy bài."), 404)
    except PostError as e:
        return _fail(str(e))
    except frappe.PermissionError:
        frappe.clear_last_message()
        return _fail(_("Bạn không có quyền làm việc này."), 403)
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        return _fail(str(e).replace("<br>", "\n"))
    except frappe.DuplicateEntryError:
        frappe.clear_last_message()
        return _fail(_("Đường dẫn bài đã có bài khác dùng. Đổi tiêu đề hoặc đường dẫn rồi lưu lại."))


def _me():
    return frappe.session.user


@frappe.whitelist(methods=["POST"])
def mark_seen(post):
    """Nguoi dang dang nhap vua mo bai -> ghi luot xem (mo bai = da xem, PO chot 01/10)."""
    return _run(service.mark_seen, _me(), str(post or ""))


@frappe.whitelist(methods=["POST"])
def toggle_reaction(post, kind):
    return _run(service.toggle_reaction, _me(), str(post or ""), str(kind or ""))


@frappe.whitelist(methods=["POST"])
def save_post(data, action="save"):
    """Luu / dang / go tu trang viet bai. data = JSON cac truong (xem editor_service.save)."""
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except ValueError:
            return _fail(_("Dữ liệu gửi lên không hợp lệ."))
    if not isinstance(data, dict):
        return _fail(_("Dữ liệu gửi lên không hợp lệ."))
    return _run(editor_service.save, _me(), data, str(action or "save"))


@frappe.whitelist(methods=["POST"])
def unpublish(post):
    return _run(editor_service.unpublish, _me(), str(post or ""))


@frappe.whitelist(methods=["POST"])
def delete_draft(post):
    return _run(editor_service.delete_draft, _me(), str(post or ""))


@frappe.whitelist(methods=["POST"])
def cover_ai_start(post, title="", summary="", content=""):
    """HR bam "Tao anh bia" (AI). Gioi han 5 lan / bai / ngay. title/summary/content = cai dang
    nhap tren trang (AI doc thang, khong can luu truoc)."""
    return _run(cover_ai.start, _me(), str(post or ""), str(title or "")[:200], str(summary or "")[:400],
                str(content or "")[:200000])


@frappe.whitelist()
def cover_ai_status(job):
    return _run(cover_ai.status, _me(), str(job or ""))
