# Copyright (c) 2026, eCentric and contributors
"""API module Ky luat - NOI DUY NHAT co @frappe.whitelist() cua module.

Moi ham: Ctx tu phien (client khong truyen user) -> service -> envelope {success, message, data}.
Ghi = POST (Frappe hoan tac moi ghi trong GET). Tham so dict den nguyen kieu hoac chuoi JSON.

  GET  get_notice(name) / get_case(name) / check_case(name, on_day) / employee_discipline(employee)
  POST issue_notice(payload) / notice_read(name) / notice_reply(name, message) / notice_cancel(name, reason)
  POST propose_case(payload) / create_case(payload) / update_case(name, payload) / cancel_case(name, reason)
  POST postpone_case(name, block_reason, block_from, block_to, note) / resume_case(name)
  POST notify_meeting(name, meeting_date, place) / confirm_attendance(name, attend, note)
  POST record_meeting(name, payload) / submit_to_ceo(name, payload) / resubmit_to_ceo(name, payload)
  POST sync_case(name) / expunge_case(name, note)
  POST notice_retitle(name, title) / case_retitle(name, title)   (sua tieu de, co nhat ky)
"""
import frappe
from frappe.utils import strip_html

from ecentric_workspace.hr.ky_luat.application import (
    case_service, decision_service, notice_service, procedure_service, views)
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatError
from ecentric_workspace.hr.ky_luat.infrastructure.repository import Repository

MSG_UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo HR / IT."
MSG_LOGIN = "Bạn cần đăng nhập."


def _ctx(repo):
    user = frappe.session.user
    if not user or user == "Guest":
        raise frappe.PermissionError(MSG_LOGIN)
    return views.make_ctx(repo, user)


def _run(fn):
    repo = Repository()
    try:
        return {"success": True, "message": "", "data": fn(repo, _ctx(repo))}
    except FieldErrors as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": {"errors": e.errors}}
    except KyLuatError as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": None}
    except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
        frappe.db.rollback()
        return {"success": False, "message": strip_html(str(e)) or MSG_UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ky_luat api")
        return {"success": False, "message": MSG_UNKNOWN, "data": None}


def _obj(v):
    if isinstance(v, str):
        try:
            return frappe.parse_json(v) or {}
        except Exception:
            return {}
    return v or {}


# ------------------------------------------------------------------------------ doc --
@frappe.whitelist(methods=["GET"])
def get_notice(name: str):
    return _run(lambda r, c: views.notice_detail(r, c, str(name)))


@frappe.whitelist(methods=["GET"])
def get_case(name: str):
    return _run(lambda r, c: views.case_detail(r, c, str(name)))


@frappe.whitelist(methods=["GET"])
def check_case(name: str, on_day: str = None):
    return _run(lambda r, c: case_service.check(r, c, str(name), on_day))


@frappe.whitelist(methods=["GET"])
def employee_discipline(employee: str):
    return _run(lambda r, c: views.employee_discipline(r, c, str(employee)))


# ------------------------------------------------------------------------- the vang --
@frappe.whitelist(methods=["POST"])
def issue_notice(payload=None):
    return _run(lambda r, c: notice_service.issue(r, c, _obj(payload)))


@frappe.whitelist(methods=["POST"])
def notice_read(name: str):
    return _run(lambda r, c: notice_service.mark_read(r, c, str(name)))


@frappe.whitelist(methods=["POST"])
def notice_reply(name: str, message: str = ""):
    return _run(lambda r, c: notice_service.reply(r, c, str(name), message))


@frappe.whitelist(methods=["POST"])
def notice_cancel(name: str, reason: str = ""):
    return _run(lambda r, c: notice_service.cancel(r, c, str(name), reason))


@frappe.whitelist(methods=["POST"])
def notice_retitle(name: str, title: str = ""):
    return _run(lambda r, c: notice_service.retitle(r, c, str(name), title))


# ------------------------------------------------------------------------ ho so do/den --
@frappe.whitelist(methods=["POST"])
def propose_case(payload=None):
    return _run(lambda r, c: case_service.propose(r, c, _obj(payload)))


@frappe.whitelist(methods=["POST"])
def create_case(payload=None):
    return _run(lambda r, c: case_service.create(r, c, _obj(payload)))


@frappe.whitelist(methods=["POST"])
def update_case(name: str, payload=None):
    return _run(lambda r, c: case_service.update(r, c, str(name), _obj(payload)))


@frappe.whitelist(methods=["POST"])
def cancel_case(name: str, reason: str = ""):
    return _run(lambda r, c: case_service.cancel(r, c, str(name), reason))


@frappe.whitelist(methods=["POST"])
def case_retitle(name: str, title: str = ""):
    return _run(lambda r, c: case_service.retitle(r, c, str(name), title))


@frappe.whitelist(methods=["POST"])
def postpone_case(name: str, block_reason: str = "", block_from: str = "", block_to: str = "", note: str = ""):
    return _run(lambda r, c: case_service.postpone(r, c, str(name), block_reason, block_from, block_to, note))


@frappe.whitelist(methods=["POST"])
def resume_case(name: str):
    return _run(lambda r, c: case_service.resume(r, c, str(name)))


@frappe.whitelist(methods=["POST"])
def notify_meeting(name: str, meeting_date: str = "", place: str = ""):
    return _run(lambda r, c: procedure_service.notify_meeting(r, c, str(name), meeting_date, place))


@frappe.whitelist(methods=["POST"])
def confirm_attendance(name: str, attend=0, note: str = ""):
    return _run(lambda r, c: procedure_service.confirm_attendance(r, c, str(name), attend, note))


@frappe.whitelist(methods=["POST"])
def record_meeting(name: str, payload=None):
    return _run(lambda r, c: procedure_service.record_meeting(r, c, str(name), _obj(payload)))


@frappe.whitelist(methods=["POST"])
def submit_to_ceo(name: str, payload=None):
    return _run(lambda r, c: procedure_service.submit_to_ceo(r, c, str(name), _obj(payload)))


@frappe.whitelist(methods=["POST"])
def resubmit_to_ceo(name: str, payload=None):
    return _run(lambda r, c: procedure_service.resubmit_to_ceo(r, c, str(name), _obj(payload)))


@frappe.whitelist(methods=["POST"])
def sync_case(name: str):
    """Sau khi CEO bam tren trang quyet dinh: dong bo ho so ngay (khong doi job). Ai xem duoc
    ho so thi goi duoc - ham chi doc trang thai phieu engine roi ghi theo."""
    def run(r, c):
        views.case_detail(r, c, str(name))           # kiem quyen xem
        return {"status": decision_service.reconcile(r, str(name))}
    return _run(run)


@frappe.whitelist(methods=["POST"])
def expunge_case(name: str, note: str = ""):
    return _run(lambda r, c: decision_service.expunge_manual(r, c, str(name), note))


# --------------------------------------------------------------- job (hooks.py) --
def daily_job():
    """09:00 ngay lam viec - xem application/jobs.py."""
    from ecentric_workspace.hr.ky_luat.application import jobs
    if frappe.conf.get("ec_ky_luat_jobs_disabled"):
        return
    frappe.logger("ky_luat").info("ky_luat.daily_job start")
    out = jobs.daily(Repository())
    frappe.db.commit()
    frappe.logger("ky_luat").info("ky_luat.daily_job done %s" % out)
    return out


def on_decision_approved(case_name):
    """Goi tu approval feature discipline_decision khi CEO duyet (cung giao dich engine)."""
    return decision_service.on_ceo_approved(Repository(), case_name)
