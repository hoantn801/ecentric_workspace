# Copyright (c) 2026, eCentric and contributors
"""API cua module tai san - NOI DUY NHAT co @frappe.whitelist().

Moi ham: Ctx tu phien (KHONG nhan tham so user / actor - bai hoc F15) -> service -> envelope
{success, message, data}. Trang goi qua window.ecApi: GET de doc, POST cho ghi.
Loi nghiep vu (TransitionError / AccessDenied) -> success=false + thong diep tieng Viet; loi la
-> rollback + Error Log + thong diep chung.
"""
import frappe
from frappe.utils import strip_html

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import component_service as CS
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import count_service as KK
from ecentric_workspace.tai_san import flows as F
from ecentric_workspace.tai_san import lifecycle as L
from ecentric_workspace.tai_san import repair_service as RS
from ecentric_workspace.tai_san import repository as R
from ecentric_workspace.tai_san import service as S
from ecentric_workspace.tai_san import views as V

MSG_UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."
MSG_LOGIN = "Bạn cần đăng nhập."
CHECK_ACTIONS = {True: C.A_CHECK_PASS, False: C.A_CHECK_FAIL}


def _ctx():
    user = frappe.session.user
    if not user or user == "Guest":
        raise frappe.PermissionError(MSG_LOGIN)
    return A.Ctx(user, frappe.get_roles(user), R.employee_of_user(user), R.departments_managed_by(user))


def _json(v, default=None):
    if v in (None, ""):
        return default
    return frappe.parse_json(v) if isinstance(v, str) else v


def _bool(v):
    return str(v).lower() in ("1", "true", "yes", "on")


def _run(fn):
    try:
        return {"success": True, "message": "", "data": fn(_ctx())}
    except A.AccessDenied as e:
        frappe.db.rollback()
        # data.denied: trang biet day la "khong co quyen" (vd /tai-san -> chuyen sang Tai san cua toi).
        return {"success": False, "message": str(e), "data": {"denied": True}}
    except L.TransitionError as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": None}
    except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
        frappe.db.rollback()
        return {"success": False, "message": strip_html(str(e)) or MSG_UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="tai_san api")
        return {"success": False, "message": MSG_UNKNOWN, "data": None}


# ------------------------------------------------------------------- doc ----
@frappe.whitelist(methods=["GET"])
def dashboard(month=None, department=None, category=None):
    return _run(lambda c: V.dashboard(c, month, department, category))


@frappe.whitelist(methods=["GET"])
def list_assets(filters=None):
    return _run(lambda c: V.list_assets(c, _json(filters, {})))


@frappe.whitelist(methods=["GET"])
def asset_detail(name):
    return _run(lambda c: V.asset_detail(c, name))


@frappe.whitelist(methods=["GET"])
def my_assets():
    return _run(V.my_assets)


@frappe.whitelist(methods=["GET"])
def board():
    return _run(V.board)


@frappe.whitelist(methods=["GET"])
def repairs(status=None):
    return _run(lambda c: V.repairs_view(c, status))


@frappe.whitelist(methods=["GET"])
def pickers(kind, category=None):
    return _run(lambda c: V.pickers(c, kind, category))


@frappe.whitelist(methods=["GET"])
def audit():
    return _run(V.audit)


@frappe.whitelist(methods=["GET"])
def count_summary(name=None):
    return _run(lambda c: KK.summary(c, name))


# ------------------------------------------------------------------- ghi ----
@frappe.whitelist(methods=["POST"])
def transition(asset, action, employee=None, note=None, checklist=None, condition=None):
    return _run(lambda c: S.transition(c, asset, action, employee=employee, note=note,
                                       checklist=_json(checklist), condition=condition))


@frappe.whitelist(methods=["POST"])
def allocate(asset, employee=None, source_type=None, source_name=None, checklist=None, note=None,
             reserve_only=0):
    return _run(lambda c: F.allocate(c, asset, employee, source_type, source_name, _json(checklist),
                                     note, _bool(reserve_only)))


@frappe.whitelist(methods=["POST"])
def reserve_for_nsp(asset, nsp, note=None):
    return _run(lambda c: F.reserve_for_nsp(c, asset, nsp, note))


@frappe.whitelist(methods=["POST"])
def return_for_clearance(asset, clearance, checklist=None, note=None):
    return _run(lambda c: F.return_for_clearance(c, asset, clearance, _json(checklist), note))


@frappe.whitelist(methods=["POST"])
def check(asset, passed, checklist=None, note=None, condition=None):
    return _run(lambda c: S.transition(c, asset, CHECK_ACTIONS[_bool(passed)], note=note,
                                       checklist=_json(checklist), condition=condition))


@frappe.whitelist(methods=["POST"])
def acknowledge(asset):
    return _run(lambda c: S.acknowledge(c, asset))


@frappe.whitelist(methods=["POST"])
def report_damage(asset, level, parts=None, description=None):
    return _run(lambda c: S.report_damage(c, asset, level, _json(parts, []), description))


@frappe.whitelist(methods=["POST"])
def open_repair(asset, data=None):
    return _run(lambda c: RS.open_repair(c, asset, _json(data, {})))


@frappe.whitelist(methods=["POST"])
def close_repair(repair, data=None):
    return _run(lambda c: RS.close_repair(c, repair, _json(data, {})))


@frappe.whitelist(methods=["POST"])
def cancel_repair(repair, note=None):
    return _run(lambda c: RS.cancel_repair(c, repair, note))


@frappe.whitelist(methods=["POST"])
def handle_damage_request(request, asset, action, data=None):
    return _run(lambda c: F.handle_damage_request(c, request, asset, action, _json(data, {})))


@frappe.whitelist(methods=["POST"])
def install_component(component, parent):
    return _run(lambda c: CS.install(c, component, parent))


@frappe.whitelist(methods=["POST"])
def remove_component(component, to_status=None):
    return _run(lambda c: CS.remove(c, component, to_status))


@frappe.whitelist(methods=["POST"])
def save_specs(asset, rows):
    return _run(lambda c: CS.save_specs(c, asset, _json(rows, [])))


@frappe.whitelist(methods=["POST"])
def create_asset(data):
    return _run(lambda c: CS.create_asset(c, _json(data, {})))


@frappe.whitelist(methods=["POST"])
def update_info(asset, data):
    return _run(lambda c: S.update_info(c, asset, _json(data, {})))


@frappe.whitelist(methods=["POST"])
def open_count(title=None):
    return _run(lambda c: KK.open_count(c, title))


@frappe.whitelist(methods=["POST"])
def confirm_count(asset, ok=1, note=None):
    return _run(lambda c: KK.self_confirm(c, asset, _bool(ok), note))


@frappe.whitelist(methods=["POST"])
def mark_count(asset, result, actual_holder=None, note=None):
    return _run(lambda c: KK.mark(c, asset, result, actual_holder, note))


@frappe.whitelist(methods=["POST"])
def close_count():
    return _run(KK.close)
