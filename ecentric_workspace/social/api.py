# Copyright (c) 2026, eCentric and contributors
"""Cua HTTP DUY NHAT cua Bang tin + Cau lac bo. Moi ham:
  * lay nguoi dung tu PHIEN - khong nhan tham so `user`;
  * ghi bang POST (GET cua Frappe khong commit);
  * tra {success, message, data}; loi nguoi dung = success False + thong diep doc duoc.
Thao tac tren mot bai tra lai the bai VE SAN (cung macro voi trang) - JS chi thay khoi HTML.
"""
import base64
import json

import frappe
from frappe import _

from ecentric_workspace.internal_posts import comments as engine
from ecentric_workspace.internal_posts.errors import Forbidden as CmtForbidden
from ecentric_workspace.internal_posts.errors import NotFound as CmtNotFound
from ecentric_workspace.internal_posts.errors import PostError
from ecentric_workspace.social import clubs, feed
from ecentric_workspace.social import comments_subject as CS
from ecentric_workspace.social import service as S
from ecentric_workspace.social.domain import Forbidden, NotFound, SocialError

ITEMS_TEMPLATE = "templates/includes/social/items.html"
COMMENTS_TEMPLATE = "templates/includes/social/comments.html"


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
    except (Forbidden, CmtForbidden) as e:
        return _fail(str(e) or _("Bạn không có quyền làm việc này."), 403)
    except (NotFound, CmtNotFound) as e:
        return _fail(str(e) or _("Không tìm thấy."), 404)
    except (SocialError, PostError) as e:
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
            raise SocialError(_("Dữ liệu gửi lên không hợp lệ."))
    if not isinstance(data, dict):
        raise SocialError(_("Dữ liệu gửi lên không hợp lệ."))
    return data


def _files(raw):
    out = []
    for f in raw or []:
        if not isinstance(f, dict):
            raise SocialError(_("Ảnh không hợp lệ."))
        try:
            content = base64.b64decode((f.get("data") or "").split(",")[-1], validate=True)
        except (ValueError, TypeError):
            raise SocialError(_("Ảnh không đọc được: {0}").format(f.get("name") or "?"))
        name = (f.get("name") or "anh").replace("/", "_").replace("\\", "_")[:120]
        out.append({"name": name, "content": content})
    return out


def _card(card):
    """The bai -> {html, name} (cung macro voi trang)."""
    return {"name": card["name"], "html": frappe.render_template(ITEMS_TEMPLATE, {"items": [dict(card, type="post")]})}


def _flag(v):
    return str(v) in ("1", "true", "True")


# ------------------------------------------------------------------ bai --------------
@frappe.whitelist(methods=["POST"])
def create(data):
    """data = JSON {body, club, dept_only, kudos_to, kudos_value, mentions[], event_title, event_start,
    event_place, files: [{name, data(base64)}]}."""
    def run():
        d = _json(data)
        return _card(S.create(_me(), d, _files(d.get("files"))))
    return _run(run)


@frappe.whitelist(methods=["POST"])
def edit(post, body=""):
    return _run(lambda: _card(S.edit(_me(), str(post or ""), str(body or "")[:20000])))


@frappe.whitelist(methods=["POST"])
def delete(post):
    return _run(S.delete, _me(), str(post or ""))


@frappe.whitelist(methods=["POST"])
def react(post="", moment=""):
    if moment:
        return _run(S.react_moment, _me(), str(moment))
    return _run(S.react, _me(), str(post or ""))


@frappe.whitelist(methods=["POST"])
def rsvp(post, answer):
    return _run(lambda: _card(S.rsvp(_me(), str(post or ""), str(answer or ""))))


@frappe.whitelist(methods=["POST"])
def report(post, reason=""):
    return _run(S.report, _me(), str(post or ""), str(reason or "")[:2000])


@frappe.whitelist(methods=["POST"])
def hide(post, hidden=1, reason=""):
    return _run(lambda: _card(S.hide(_me(), str(post or ""), _flag(hidden), str(reason or "")[:2000])))


@frappe.whitelist(methods=["POST"])
def dismiss(post):
    return _run(S.dismiss_reports, _me(), str(post or ""))


@frappe.whitelist()
def people():
    return _run(S.people, _me())


@frappe.whitelist()
def more(loc="", before="", club="", tab=""):
    """Trang tiep theo cua bang tin / trang CLB -> {html, next}."""
    def run():
        if club:
            ctx = clubs.club_page(_me(), str(club), str(tab or "bai-viet"), str(before or ""))
        else:
            ctx = feed.page(_me(), str(loc or ""), str(before or ""))
        return {"html": frappe.render_template(ITEMS_TEMPLATE, {"items": ctx["items"]}), "next": ctx["next"]}
    return _run(run)


@frappe.whitelist()
def image(post, i=0):
    """Anh cua bai (private). Nguoi xem phai thay bai - day la duong xem anh duy nhat."""
    try:
        fname, content = S.image(_me(), str(post or ""), i)
    except (Forbidden, frappe.PermissionError):
        return _fail(_("Bạn không xem được ảnh này."), 403)
    except (NotFound, SocialError):
        return _fail(_("Không tìm thấy ảnh."), 404)
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
    frappe.local.response.display_content_as = "inline"


# ------------------------------------------------------------------ binh luan --------
def _comments(fn, *args, **kwargs):
    def run():
        view = CS.decorate(fn(*args, **kwargs))
        return {"post": view["post"], "count": view["count"],
                "html": frappe.render_template(COMMENTS_TEMPLATE, {"cm": view})}
    return _run(run)


@frappe.whitelist()
def comments(post, ref=""):
    """ref="hr": binh luan cua bai Tin noi bo (the nhung tren Bang tin)."""
    if ref == "hr":
        return _comments(lambda: CS.hr_view(_me(), str(post or "")))
    return _comments(lambda: CS.view(_me(), str(post or "")))


@frappe.whitelist(methods=["POST"])
def comment_add(post="", content="", parent="", moment="", ref=""):
    def add():
        if ref == "hr":
            name = str(post or "")
        else:
            name = str(post or "") or CS.ensure_moment(_me(), str(moment or ""))
        return engine.add(_me(), name, str(content or "")[:20000], str(parent or "") or None,
                          subject=CS.subject_for(ref))
    return _comments(add)


# Thao tac theo ma binh luan: loai bai (Bang tin / Tin noi bo) lay tu chinh binh luan.
@frappe.whitelist(methods=["POST"])
def comment_edit(comment, content=""):
    c = str(comment or "")
    return _comments(engine.edit, _me(), c, str(content or "")[:20000], subject=CS.subject_of_comment(c))


@frappe.whitelist(methods=["POST"])
def comment_delete(comment):
    c = str(comment or "")
    return _comments(engine.delete, _me(), c, subject=CS.subject_of_comment(c))


@frappe.whitelist(methods=["POST"])
def comment_hide(comment, hidden=1):
    c = str(comment or "")
    return _comments(engine.hide, _me(), c, _flag(hidden), subject=CS.subject_of_comment(c))


@frappe.whitelist(methods=["POST"])
def comment_like(comment):
    c = str(comment or "")
    return _comments(engine.like, _me(), c, subject=CS.subject_of_comment(c))


# ------------------------------------------------------------------ CLB --------------
@frappe.whitelist(methods=["POST"])
def club_join(club):
    return _run(clubs.join, _me(), str(club or ""))


@frappe.whitelist(methods=["POST"])
def club_leave(club):
    return _run(clubs.leave, _me(), str(club or ""))


@frappe.whitelist(methods=["POST"])
def club_propose(data):
    return _run(lambda: clubs.propose(_me(), _json(data)))


@frappe.whitelist(methods=["POST"])
def club_decide(club, approve=1, note=""):
    return _run(clubs.decide, _me(), str(club or ""), _flag(approve), str(note or "")[:2000])


@frappe.whitelist(methods=["POST"])
def club_lead(club, lead):
    return _run(clubs.set_lead, _me(), str(club or ""), str(lead or ""))


@frappe.whitelist(methods=["POST"])
def club_status(club, active=0):
    return _run(clubs.set_status, _me(), str(club or ""), _flag(active))
