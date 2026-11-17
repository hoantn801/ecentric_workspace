# Copyright (c) 2026, eCentric and contributors
"""API noi bo trang /ai-live/ban-quyen (KHONG cho khach - phai dang nhap; quyen kiem o service:
System Manager hoac role "AI Live License Admin", nguoi khac -> 403). Envelope {success, message, data}.
Duong dan: /api/method/ecentric_workspace.ai_tools.features.ai_live.controllers.license_admin_api.<ham>"""
import frappe

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L


def _run(fn):
    try:
        return {"success": True, "message": "", "data": fn()}
    except L.LicensePermission as e:
        frappe.db.rollback()
        frappe.local.response["http_status_code"] = 403
        return {"success": False, "message": str(e), "data": None}
    except (L.LicenseError, frappe.ValidationError) as e:
        frappe.db.rollback()
        return {"success": False, "message": frappe.utils.strip_html(str(e)), "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_live license_admin")
        return {"success": False, "message": "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT.",
                "data": None}


def _ctx():
    user = frappe.session.user
    return user, frappe.get_roles(user)


def _json(v, default):
    if v in (None, ""):
        return default
    return frappe.parse_json(v) if isinstance(v, str) else v


def _q():
    from ecentric_workspace.ai_tools.features.ai_live.application.license_query_service import LicenseQueryService
    return LicenseQueryService()


def _act():
    from ecentric_workspace.ai_tools.features.ai_live.application.license_action_service import LicenseActionService
    return LicenseActionService()


def _detail():
    from ecentric_workspace.ai_tools.features.ai_live.application.license_detail_service import LicenseDetailService
    return LicenseDetailService()


@frappe.whitelist(methods=["GET"])
def summary():
    return _run(lambda: _q().summary(_ctx()[1]))


@frappe.whitelist(methods=["GET"])
def pending_badge():
    return _q().badge(_ctx()[1])          # shell doc thang msg.pending; loi -> huy hieu an (giong cac huy hieu khac)


@frappe.whitelist(methods=["GET"])
def list_machines(filters=None, page=0):
    return _run(lambda: _q().machines_page(_ctx()[1], _json(filters, {}), page))


@frappe.whitelist(methods=["GET"])
def get_machine(name):
    return _run(lambda: _detail().machine(_ctx()[1], name))


@frappe.whitelist(methods=["POST"])
def approve(names):
    user, roles = _ctx()
    return _run(lambda: _act().approve(user, roles, _json(names, [])))


@frappe.whitelist(methods=["POST"])
def block(name, message=None):
    user, roles = _ctx()
    return _run(lambda: _act().block(user, roles, name, message))


@frappe.whitelist(methods=["POST"])
def unblock(name):
    user, roles = _ctx()
    return _run(lambda: _act().unblock(user, roles, name))


@frappe.whitelist(methods=["POST"])
def update_machine(name, label=None, note=None):
    user, roles = _ctx()
    return _run(lambda: _act().update_machine(user, roles, name, label, note))


@frappe.whitelist(methods=["GET"])
def tree(dist=None):
    return _run(lambda: _detail().tree(_ctx()[1], dist))


@frappe.whitelist(methods=["GET"])
def list_dists():
    return _run(lambda: _q().dists_page(_ctx()[1]))


@frappe.whitelist(methods=["POST"])
def update_dist(dist_id, label=None):
    user, roles = _ctx()
    return _run(lambda: _act().update_dist(user, roles, dist_id, label))


@frappe.whitelist(methods=["GET"])
def events(filters=None, page=0):
    return _run(lambda: _q().events_page(_ctx()[1], _json(filters, {}), page))


@frappe.whitelist(methods=["POST"])
def set_mode(enabled, log_only):
    user, roles = _ctx()
    return _run(lambda: _act().set_mode(user, roles, frappe.utils.cint(enabled), frappe.utils.cint(log_only)))
