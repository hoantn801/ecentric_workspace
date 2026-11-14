# Copyright (c) 2026, eCentric and contributors
"""API cua module Dao tao + Quiz truc tiep - NOI DUY NHAT co @frappe.whitelist().

Moi ham: Ctx tu phien -> goi service -> envelope {success, message, data}. Trang goi qua
window.ecApi (public/js/ec_api.js): GET cho doc, POST JSON cho ghi (tham so payload den nguyen
kieu dict/list - KHONG chu thich kieu `str` cho chung).
Bat loi thi rollback (Frappe khong tu rollback khi ham whitelist tu bat exception).
"""
import frappe
from frappe.utils import strip_html

from ecentric_workspace.dao_tao.application import (draw_service, learn_service, play_service,
                                                    quiz_service, room_service)
from ecentric_workspace.dao_tao.application.access import Ctx
from ecentric_workspace.dao_tao.domain.errors import FieldErrors, QuizError
from ecentric_workspace.dao_tao.infrastructure import store as repo

MSG_UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."
MSG_LOGIN = "Bạn cần đăng nhập."


def _ctx():
    user = frappe.session.user
    if not user or user == "Guest":
        raise frappe.PermissionError(MSG_LOGIN)
    return Ctx(user, frappe.get_roles(user))


def _run(fn, write=False):
    """write=True cho cac ham GET co the GHI (tu khoa cau het gio, danh dau "da xem bai"): Frappe
    chi tu commit sau POST, nen GET phai tu commit - khong thi lan khoa bi bo khi het request."""
    try:
        data = fn(_ctx())
        if write:
            frappe.db.commit()
        return {"success": True, "message": "", "data": data}
    except FieldErrors as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": {"errors": e.errors}}
    except QuizError as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": None}
    except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
        frappe.db.rollback()
        return {"success": False, "message": strip_html(str(e)) or MSG_UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="dao_tao api")
        return {"success": False, "message": MSG_UNKNOWN, "data": None}


def _b(v):
    return str(v).lower() in ("1", "true", "yes")


def _obj(v):
    """Tham so dict/list: may goi bang form-encoded (app cu, curl) gui chuoi JSON -> doi lai."""
    if isinstance(v, str):
        try:
            return frappe.parse_json(v) or {}
        except Exception:
            return {}
    return v or {}


# ------------------------------------------------------------------- nguoi choi quiz --

@frappe.whitelist(methods=["GET"])
def quiz_home():
    return _run(lambda c: {"rooms": play_service.lobby_rooms(c, repo), "can_host": c.can_host,
                           **play_service.history(c, repo)})


@frappe.whitelist(methods=["GET"])
def live_card():
    return _run(lambda c: play_service.live_card(c, repo))


@frappe.whitelist(methods=["GET"])
def my_profile():
    return _run(lambda c: play_service.my_profile(c, repo))


@frappe.whitelist(methods=["POST"])
def join(code, device="", automation=0):
    return _run(lambda c: play_service.join(c, repo, code, device, _b(automation)))


@frappe.whitelist(methods=["POST"])
def set_profile(code, nickname=None, avatar=None):
    return _run(lambda c: play_service.set_profile(c, repo, code, nickname, avatar))


@frappe.whitelist(methods=["GET"])
def state(code, device=""):
    return _run(lambda c: play_service.state(c, repo, code, device), write=True)


@frappe.whitelist(methods=["GET"])
def result(session):
    return _run(lambda c: play_service.ended_state(c, repo, session))


@frappe.whitelist(methods=["POST"])
def answer(code, qid=None, payload=None, device=""):
    return _run(lambda c: play_service.answer(c, repo, code, qid, _obj(payload), device))


@frappe.whitelist(methods=["POST"])
def power_pick(code, power="", device=""):
    return _run(lambda c: play_service.pick_power(c, repo, code, power, device))


@frappe.whitelist(methods=["POST"])
def power_use(code, power="", device=""):
    return _run(lambda c: play_service.use_power(c, repo, code, power, device))


@frappe.whitelist(methods=["POST"])
def report(code, kind=""):
    return _run(lambda c: play_service.report(c, repo, code, kind))


# ------------------------------------------------------------------- nguoi dan quiz --

@frappe.whitelist(methods=["GET"])
def quiz_list():
    return _run(lambda c: quiz_service.list_quizzes(c, repo))


@frappe.whitelist(methods=["GET"])
def quiz_get(name=None, template=None):
    return _run(lambda c: quiz_service.get(c, repo, name) if name else quiz_service.new(c, repo, template))


@frappe.whitelist(methods=["POST"])
def quiz_save(quiz=None):
    return _run(lambda c: quiz_service.save(c, repo, _obj(quiz)))


@frappe.whitelist(methods=["POST"])
def quiz_archive(name):
    return _run(lambda c: quiz_service.archive(c, repo, name))


@frappe.whitelist(methods=["POST"])
def quiz_import(file_url):
    return _run(lambda c: quiz_service.import_file(c, repo, file_url))


@frappe.whitelist(methods=["POST"])
def room_open(quiz):
    return _run(lambda c: room_service.open_room(c, repo, quiz))


@frappe.whitelist(methods=["GET"])
def room_state(session):
    return _run(lambda c: room_service.host_state(c, repo, session), write=True)


@frappe.whitelist(methods=["POST"])
def room_act(session, action, version=None):
    return _run(lambda c: room_service.act(c, repo, session, action, version))


@frappe.whitelist(methods=["POST"])
def room_player(session, user, op, nickname=None):
    return _run(lambda c: room_service.manage_player(c, repo, session, user, op, nickname))


# ---------------------------------------------------------------------------- hoc --

@frappe.whitelist(methods=["GET"])
def learn_hub():
    return _run(lambda c: learn_service.hub(c, repo))


@frappe.whitelist(methods=["GET"])
def lesson(name):
    return _run(lambda c: learn_service.lesson_detail(c, repo, name), write=True)


@frappe.whitelist(methods=["POST"])
def lesson_quiz(name, answers=None):
    return _run(lambda c: learn_service.submit_quiz(c, repo, name, _obj(answers)))


@frappe.whitelist(methods=["POST"])
def lesson_practice(name, text="", link=""):
    return _run(lambda c: learn_service.submit_practice(c, repo, name, text, link))


@frappe.whitelist(methods=["POST"])
def topic_propose(topic=None):
    return _run(lambda c: learn_service.propose_topic(c, repo, _obj(topic)))


@frappe.whitelist(methods=["POST"])
def topic_vote(topic, on=1):
    return _run(lambda c: learn_service.vote(c, repo, topic, _b(on)))


@frappe.whitelist(methods=["GET"])
def draw_hub():
    return _run(lambda c: draw_service.hub(c, repo), write=True)


@frappe.whitelist(methods=["POST"])
def draw_pick(number=None):
    return _run(lambda c: draw_service.pick(c, repo, number))


@frappe.whitelist(methods=["POST"])
def draw_release(number):
    return _run(lambda c: draw_service.release(c, repo, number))


@frappe.whitelist(methods=["GET"])
def draw_admin():
    return _run(lambda c: draw_service.admin_get(c, repo), write=True)


@frappe.whitelist(methods=["POST"])
def draw_save(draw=None):
    return _run(lambda c: draw_service.admin_save(c, repo, _obj(draw)))


@frappe.whitelist(methods=["POST"])
def draw_now():
    return _run(lambda c: draw_service.draw_now(c, repo))


@frappe.whitelist(methods=["GET"])
def lesson_admin():
    return _run(lambda c: learn_service.admin_list(c, repo))


@frappe.whitelist(methods=["GET"])
def lesson_admin_get(name):
    return _run(lambda c: learn_service.admin_get(c, repo, name))


@frappe.whitelist(methods=["POST"])
def lesson_save(lesson=None):
    return _run(lambda c: learn_service.admin_save(c, repo, _obj(lesson)))


@frappe.whitelist(methods=["GET"])
def lesson_submissions(name):
    return _run(lambda c: learn_service.admin_submissions(c, repo, name))


@frappe.whitelist(methods=["POST"])
def lesson_review(name, user, verdict):
    return _run(lambda c: learn_service.admin_review(c, repo, name, user, verdict))


@frappe.whitelist(methods=["POST"])
def topic_status(topic, status, lesson=None):
    return _run(lambda c: learn_service.admin_topic(c, repo, topic, status, lesson))
