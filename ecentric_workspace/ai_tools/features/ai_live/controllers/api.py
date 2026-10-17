# Copyright (c) 2026, eCentric and contributors
"""API AI Live (app eCentric AI Live tren may phat + trang /ai-video). Moi ham: service -> envelope
{success, message, data}. May phat goi bang header `Authorization: token <api_key>:<api_secret>`
(token cap o EC AI Live Machine). Duong dan ngan cho app: ecentric_workspace.ai_live.api.*"""
import frappe

from ecentric_workspace.ai_tools.features.ai_live import constants as C


def _run(fn):
    from ecentric_workspace.ai_tools.features.ai_video.infrastructure.worker_client import WorkerDown
    try:
        return {"success": True, "message": "", "data": fn()}
    except WorkerDown as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": {"worker_down": True}}
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


# ------------------------------------------------------------------ Bo live + Kho host (trang /ai-video) ---

@frappe.whitelist(methods=["GET"])
def list_kits(brand: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.list_kits_service import ListKitsService
    return _run(lambda: ListKitsService().execute(_roles(), brand or None))


@frappe.whitelist(methods=["GET"])
def get_kit(name: str, tick: int = 0):
    from ecentric_workspace.ai_tools.features.ai_live.application.get_kit_service import GetKitService
    return _run(lambda: GetKitService().execute(_roles(), name, bool(int(tick or 0))))


@frappe.whitelist(methods=["POST"])
def save_kit(data: str, name: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.save_kit_service import SaveKitService
    return _run(lambda: SaveKitService().execute(frappe.session.user, _roles(), name or None, data))


@frappe.whitelist(methods=["POST"])
def build_kit(name: str):
    from ecentric_workspace.ai_tools.features.ai_live.application.start_build_kit_service import StartBuildKitService
    return _run(lambda: StartBuildKitService().execute(_roles(), name))


@frappe.whitelist(methods=["GET"])
def list_hosts():
    from ecentric_workspace.ai_tools.features.ai_live.application.list_hosts_service import ListHostsService
    return _run(lambda: ListHostsService().execute(_roles()))


@frappe.whitelist(methods=["POST"])
def host_image_start(data: str):
    from ecentric_workspace.ai_tools.features.ai_live.application.host_image_service import HostImageService
    return _run(lambda: HostImageService().execute(frappe.session.user, _roles(), data))


@frappe.whitelist(methods=["GET"])
def host_image_status(host: str):
    from ecentric_workspace.ai_tools.features.ai_live.application.host_image_status_service import HostImageStatusService
    return _run(lambda: HostImageStatusService().execute(_roles(), host))


@frappe.whitelist(methods=["POST"])
def host_save(host: str, cand: int, label: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.host_save_service import HostSaveService
    return _run(lambda: HostSaveService().execute(_roles(), host, cand, label))


@frappe.whitelist(methods=["POST"])
def motion_set(host: str, plan: str = None, dry_run: int = 1):
    from ecentric_workspace.ai_tools.features.ai_live.application.motion_set_service import MotionSetService
    return _run(lambda: MotionSetService().execute(_roles(), host, plan, bool(int(dry_run or 0))))
