# Copyright (c) 2026, eCentric and contributors
"""Cua HTTP DUY NHAT cua Gop y cong ty. Moi ham:
  * lay nguoi dung tu PHIEN - khong nhan tham so `user` (whitelist + tham so nguoi thao tac =
    mao danh duoc);
  * ghi bang POST (GET cua Frappe khong commit);
  * tra {success, message, data} - loi nguoi dung la success False + thong diep doc duoc,
    khong de traceback lot ra trinh duyet.
"""
import base64
import json

import frappe
from frappe import _

from ecentric_workspace.feedback import handler_service as H
from ecentric_workspace.feedback import service as S


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
    except S.Forbidden as e:
        return _fail(str(e) or _("Bạn không có quyền làm việc này."), 403)
    except S.NotFound:
        return _fail(_("Không tìm thấy góp ý."), 404)
    except S.FeedbackError as e:
        return _fail(str(e))
    except frappe.PermissionError:
        frappe.clear_last_message()
        return _fail(_("Bạn không có quyền làm việc này."), 403)
    except frappe.ValidationError as e:
        frappe.clear_last_message()
        return _fail(str(e).replace("<br>", "\n"))


def _me():
    return frappe.session.user


def _json(data):
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except ValueError:
            raise S.FeedbackError(_("Dữ liệu gửi lên không hợp lệ."))
    if not isinstance(data, dict):
        raise S.FeedbackError(_("Dữ liệu gửi lên không hợp lệ."))
    return data


def _files(raw):
    """[{name, data: base64}] -> [{name, content, size}]. Kiem loai / dung luong o domain.check_files."""
    out = []
    for f in raw or []:
        if not isinstance(f, dict):
            raise S.FeedbackError(_("Tệp đính kèm không hợp lệ."))
        try:
            content = base64.b64decode((f.get("data") or "").split(",")[-1], validate=True)
        except (ValueError, TypeError):
            raise S.FeedbackError(_("Tệp đính kèm không đọc được: {0}").format(f.get("name") or "?"))
        name = (f.get("name") or "tep").replace("/", "_").replace("\\", "_")[:120]
        out.append({"name": name, "content": content, "size": len(content)})
    return out


def _submit(data):
    data = _json(data)
    return S.submit(_me(), data, _files(data.get("files")))


@frappe.whitelist(methods=["POST"])
def submit(data):
    """Gui gop y. data = JSON {title, body, topic, kind, is_anonymous, files: [{name, data(base64)}]}."""
    return _run(_submit, data)


@frappe.whitelist(methods=["POST"])
def send_message(feedback, message):
    return _run(S.send_message, _me(), str(feedback or ""), str(message or ""))


@frappe.whitelist(methods=["POST"])
def reopen(feedback, message):
    return _run(S.reopen, _me(), str(feedback or ""), str(message or ""))


@frappe.whitelist(methods=["POST"])
def mark_read(feedback):
    return _run(S.mark_read, _me(), str(feedback or ""))


@frappe.whitelist(methods=["POST"])
def toggle_vote(feedback):
    return _run(S.toggle_vote, _me(), str(feedback or ""))


@frappe.whitelist(methods=["POST"])
def mark_viewing(feedback):
    return _run(H.mark_viewing, _me(), str(feedback or ""))


@frappe.whitelist(methods=["POST"])
def act(feedback, status="", message="", internal=0):
    return _run(H.act, _me(), str(feedback or ""), str(status or ""), str(message or ""),
                str(internal) in ("1", "true", "True"))


@frappe.whitelist(methods=["POST"])
def set_topic(feedback, topic):
    return _run(H.set_topic, _me(), str(feedback or ""), str(topic or ""))


@frappe.whitelist(methods=["POST"])
def publish(feedback, on=1, title="", answer=""):
    return _run(H.publish, _me(), str(feedback or ""), on, str(title or ""), str(answer or ""))


@frappe.whitelist(methods=["POST"])
def mark_duplicate(feedback, of="", spam=0, message=""):
    return _run(H.mark_duplicate, _me(), str(feedback or ""), str(of or ""), spam, str(message or ""))


@frappe.whitelist(methods=["POST"])
def summarize_now(month=""):
    return _run(H.summarize_now, _me(), str(month or ""))


@frappe.whitelist()
def download(feedback, idx=0):
    """Tai tep dinh kem (private) theo THU TU trong gop y. Nguoi gui hoac nguoi xu ly. Tep KHONG mo
    qua /private/files duoc vi DocType chi System Manager doc - day la duong tai duy nhat."""
    try:
        fname, content = S.download(_me(), str(feedback or ""), idx)
    except (S.Forbidden, frappe.PermissionError):
        return _fail(_("Bạn không có quyền tải tệp này."), 403)
    except S.NotFound:
        return _fail(_("Không tìm thấy tệp."), 404)
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "attachment"
