# Copyright (c) 2026, eCentric and contributors
"""API AI Live (app eCentric AI Live tren may phat + trang /ai-video). Moi ham: service -> envelope
{success, message, data}. May phat goi bang header `Authorization: token <api_key>:<api_secret>`
(token cap o EC AI Live Machine). Duong dan ngan cho app: ecentric_workspace.ai_live.api.*"""
import frappe

from ecentric_workspace.ai_tools.features.ai_live import constants as C


def _run(fn):
    try:
        return {"success": True, "message": "", "data": fn()}
    except C.AiLivePermission as e:
        frappe.db.rollback()
        frappe.local.response["http_status_code"] = 403
        return {"success": False, "message": str(e), "data": None}
    except (C.AiLiveError, frappe.ValidationError) as e:
        frappe.db.rollback()
        return {"success": False, "message": frappe.utils.strip_html(str(e)) or C.Msg.UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_live api")
        return {"success": False, "message": C.Msg.UNKNOWN, "data": None}


def _roles():
    return frappe.get_roles(frappe.session.user)


@frappe.whitelist(methods=["GET"])
def get_config(machine: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.get_config_service import GetConfigService
    return _run(lambda: GetConfigService().execute(frappe.session.user, str(machine or "")))


@frappe.whitelist(methods=["POST"])
def push_cost(machine: str = None, brand: str = None, session: str = None, date: str = None, usd=None, items=None):
    from ecentric_workspace.ai_tools.features.ai_live.application.push_cost_service import PushCostService
    payload = {"machine": machine, "brand": brand, "session": session, "date": date, "usd": usd,
               "items": frappe.parse_json(items) if isinstance(items, str) else items}
    return _run(lambda: PushCostService().execute(frappe.session.user, payload))


@frappe.whitelist(methods=["POST"])
def put_brand_settings(brand: str = None, templates=None, playlist=None, cooldowns=None):
    from ecentric_workspace.ai_tools.features.ai_live.application.put_brand_settings_service import PutBrandSettingsService
    payload = {"brand": brand, "templates": templates, "playlist": playlist, "cooldowns": cooldowns}
    return _run(lambda: PutBrandSettingsService().execute(frappe.session.user, _roles(), payload))


@frappe.whitelist(methods=["POST"])
def register_machine(code: str, label: str = None, brands: str = None, new_token: int = 1):
    from ecentric_workspace.ai_tools.features.ai_live.application.register_machine_service import RegisterMachineService
    return _run(lambda: RegisterMachineService().execute(_roles(), code, label, brands, bool(int(new_token or 0))))


@frappe.whitelist(methods=["GET"])
def cost_summary(brand: str = None, days: int = 7):
    from ecentric_workspace.ai_tools.features.ai_live.application.cost_summary_service import CostSummaryService
    return _run(lambda: CostSummaryService().execute(_roles(), brand or None, int(days or 7)))
