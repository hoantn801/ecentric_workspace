# Copyright (c) 2026, eCentric and contributors
"""API cua module Khao sat - NOI DUY NHAT co @frappe.whitelist().

Moi ham: dung Ctx tu phien -> goi service -> boc envelope {success, message, data}.
Trang goi qua window.ecApi (public/js/ec_api.js): GET cho doc, POST cho ghi (POST JSON nen
tham so dang dict/list den nguyen kieu - KHONG chu thich kieu `str` cho cac tham so payload,
Frappe v15+ se tu choi vi lech kieu).

VI SAO rollback khi bat loi: bat exception trong ham whitelist thi Frappe khong tu rollback
nua; khong rollback thi mot lan nop loi giua chung (da chen phieu, chua chen nguoi tham gia)
se duoc commit.
"""
import frappe
from frappe.utils import strip_html

from ecentric_workspace.surveys.application import (builder_service, draw_feed, draw_service,
                                                    publish_service, respond_service,
                                                    results_service, submit_reward)
from ecentric_workspace.surveys.application.access import Ctx
from ecentric_workspace.surveys.domain.errors import AnswerErrors, SurveyError
from ecentric_workspace.surveys.infrastructure import repository as repo

MSG_UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."
MSG_LOGIN = "Bạn cần đăng nhập."


def _ctx():
    user = frappe.session.user
    if not user or user == "Guest":
        raise frappe.PermissionError(MSG_LOGIN)
    return Ctx(user, frappe.get_roles(user))


def _run(fn):
    try:
        return {"success": True, "message": "", "data": fn(_ctx())}
    except AnswerErrors as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": {"errors": e.errors}}
    except SurveyError as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": None}
    except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
        frappe.db.rollback()
        return {"success": False, "message": strip_html(str(e)) or MSG_UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="surveys api")
        return {"success": False, "message": MSG_UNKNOWN, "data": None}


# ----------------------------------------------------------------- nguoi tra loi --

@frappe.whitelist(methods=["GET"])
def hub():
    return _run(lambda c: respond_service.hub(c))


@frappe.whitelist(methods=["GET"])
def get_form(name, preview=0):
    return _run(lambda c: respond_service.get_form(c, name, preview=str(preview) == "1"))


@frappe.whitelist(methods=["POST"])
def submit(name, answers=None):
    return _run(lambda c: respond_service.submit(c, name, answers or {}))


@frappe.whitelist(methods=["POST"])
def spin(name):
    return _run(lambda c: submit_reward.spin(c, name, repo))


@frappe.whitelist(methods=["POST"])
def pick_number(name, number=0):
    return _run(lambda c: submit_reward.pick_number(c, name, number, repo))


@frappe.whitelist(methods=["GET"])
def number_board(name):
    return _run(lambda c: submit_reward.board(c, name, repo))


@frappe.whitelist(methods=["GET"])
def home_draws():
    """Quay so / dua ve dich cho popup trang chu (lam moi luc dang quay)."""
    return _run(lambda c: draw_feed.for_user(c.user, repo))


@frappe.whitelist(methods=["GET"])
def draw_result(name):
    """Mot luot quay (popup hoi trong luc cho chot ket qua)."""
    return _run(lambda c: draw_feed.one(c.user, name, repo))


@frappe.whitelist(methods=["GET"])
def public_summary(name):
    return _run(lambda c: respond_service.public_summary(c, name))


# ---------------------------------------------------------------------- nguoi soan --

@frappe.whitelist(methods=["GET"])
def manage_list():
    return _run(lambda c: builder_service.list_mine(c))


@frappe.whitelist(methods=["GET"])
def directory():
    return _run(lambda c: builder_service.directory(c))


@frappe.whitelist(methods=["POST"])
def create(template="blank", source=None):
    return _run(lambda c: builder_service.create(c, template=template, source=source))


@frappe.whitelist(methods=["GET"])
def get_builder(name):
    return _run(lambda c: builder_service.get(c, name))


@frappe.whitelist(methods=["POST"])
def save(name, payload=None):
    return _run(lambda c: builder_service.save(c, name, payload or {}))


@frappe.whitelist(methods=["POST"])
def delete(name):
    return _run(lambda c: builder_service.delete(c, name))


@frappe.whitelist(methods=["POST"])
def publish(name):
    return _run(lambda c: publish_service.publish(c, name))


@frappe.whitelist(methods=["POST"])
def close(name):
    return _run(lambda c: publish_service.close(c, name))


@frappe.whitelist(methods=["POST"])
def reopen(name):
    return _run(lambda c: publish_service.reopen(c, name))


@frappe.whitelist(methods=["POST"])
def remind(name):
    return _run(lambda c: publish_service.remind(c, name))


@frappe.whitelist(methods=["POST"])
def draw(name):
    return _run(lambda c: draw_service.draw_now(c, name, repo))


# ------------------------------------------------------------------------- ket qua --

@frappe.whitelist(methods=["GET"])
def results_overview(name):
    return _run(lambda c: results_service.overview(c, name))


@frappe.whitelist(methods=["GET"])
def results_response(name, index=0):
    return _run(lambda c: results_service.response_at(c, name, index))


@frappe.whitelist(methods=["GET"])
def results_participation(name):
    return _run(lambda c: results_service.participation(c, name))


@frappe.whitelist(methods=["GET"])
def export_xlsx(name):
    """Tai file Excel - tra file, khong tra envelope. Loi -> frappe.throw (trang loi chuan)."""
    from frappe.utils.xlsxutils import make_xlsx
    try:
        fname, rows = results_service.export(_ctx(), name)
    except SurveyError as e:
        frappe.throw(str(e))
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = make_xlsx(rows, "Ket qua").getvalue()
    frappe.local.response.type = "download"


@frappe.whitelist(methods=["GET"])
def download_file(name, url):
    try:
        content, fname = results_service.file_for_download(_ctx(), name, url)
    except SurveyError as e:
        frappe.throw(str(e))
    frappe.local.response.filename = fname
    frappe.local.response.filecontent = content
    frappe.local.response.type = "download"
