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


# ------------------------------------------------------------------ Giam sat live (fix10c) ---

def _monitor_link():
    return frappe.utils.get_url().rstrip("/") + C.MONITOR_LINK


@frappe.whitelist(methods=["POST"])
def push_heartbeat(machine: str = None, lives=None, thumb_b64=None):
    from ecentric_workspace.ai_tools.features.ai_live.application.push_heartbeat_service import PushHeartbeatService
    payload = {"machine": machine, "lives": lives, "thumb_b64": thumb_b64}
    return _run(lambda: PushHeartbeatService().execute(frappe.session.user, payload))


@frappe.whitelist(methods=["GET"])
def monitor_wall(brand: str = None, level: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.monitor_wall_service import MonitorWallService
    return _run(lambda: MonitorWallService().execute(_roles(), brand or None, level or None))


@frappe.whitelist(methods=["GET"])
def monitor_detail(key: str):
    from ecentric_workspace.ai_tools.features.ai_live.application.monitor_detail_service import MonitorDetailService
    return _run(lambda: MonitorDetailService().execute(_roles(), key))


@frappe.whitelist(methods=["GET"])
def monitor_thumb(key: str, kind: str = "obs"):
    from ecentric_workspace.ai_tools.features.ai_live.application.monitor_thumb_service import MonitorThumbService
    return _run(lambda: MonitorThumbService().execute(_roles(), key, kind))


@frappe.whitelist(methods=["POST"])
def alert_test():
    from ecentric_workspace.ai_tools.features.ai_live.application.alert_test_service import AlertTestService
    return _run(lambda: AlertTestService(link=_monitor_link()).execute(_roles()))


# ------------------------------------------------------------------ Phien live + Lich live (fix10d) ---

def _atomic(fn):
    """Chay fn trong savepoint: loi validate cua 1 phien chi lui phan cua phien do (bat / tat hang loat)."""
    frappe.db.savepoint("ailive_sess")
    try:
        return fn()
    except (C.AiLiveError, frappe.ValidationError) as e:
        frappe.db.rollback(save_point="ailive_sess")
        raise C.AiLiveError(frappe.utils.strip_html(str(e)) or C.Msg.UNKNOWN)


@frappe.whitelist(methods=["GET"])
def list_sessions(brand: str = None, platform: str = None, machine: str = None, status: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.list_sessions_service import ListSessionsService
    return _run(lambda: ListSessionsService().execute(_roles(), brand or None, platform or None, machine or None, status or None))


@frappe.whitelist(methods=["GET"])
def session_detail(name: str):
    from ecentric_workspace.ai_tools.features.ai_live.application.session_detail_service import SessionDetailService
    return _run(lambda: SessionDetailService().execute(_roles(), name))


@frappe.whitelist(methods=["GET"])
def session_history(live: str = None, brand: str = None, days: int = 7):
    from ecentric_workspace.ai_tools.features.ai_live.application.session_history_service import SessionHistoryService
    return _run(lambda: SessionHistoryService().execute(_roles(), live or None, brand or None, int(days or 7)))


@frappe.whitelist(methods=["GET"])
def week_schedule(week: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.week_schedule_service import WeekScheduleService
    return _run(lambda: WeekScheduleService().execute(_roles(), week or None))


@frappe.whitelist(methods=["POST"])
def save_slots(name: str, slots=None):
    from ecentric_workspace.ai_tools.features.ai_live.application.save_slots_service import SaveSlotsService
    return _run(lambda: SaveSlotsService().execute(_roles(), name, slots))


@frappe.whitelist(methods=["POST"])
def set_sessions_enabled(names=None, enabled: int = 1):
    from ecentric_workspace.ai_tools.features.ai_live.application.set_sessions_enabled_service import SetSessionsEnabledService
    return _run(lambda: SetSessionsEnabledService(atomic=_atomic).execute(_roles(), names, bool(int(enabled or 0))))


@frappe.whitelist(methods=["POST"])
def queue_command(name: str, action: str, args=None):
    from ecentric_workspace.ai_tools.features.ai_live.application.queue_command_service import QueueCommandService
    return _run(lambda: QueueCommandService().execute(frappe.session.user, _roles(), name, action, args))


@frappe.whitelist(methods=["GET"])
def pull_commands(machine: str = None):
    from ecentric_workspace.ai_tools.features.ai_live.application.pull_commands_service import PullCommandsService
    return _run(lambda: PullCommandsService().execute(frappe.session.user, str(machine or "")))


@frappe.whitelist(methods=["POST"])
def ack_command(machine: str = None, id: str = None, ok: int = 1, result: str = None):  # noqa: A002 - ten tham so theo hop dong app
    from ecentric_workspace.ai_tools.features.ai_live.application.ack_command_service import AckCommandService
    return _run(lambda: AckCommandService().execute(frappe.session.user, str(machine or ""), id, bool(int(ok or 0)), result))


@frappe.whitelist(methods=["POST"])
def push_session_summary(machine: str = None, live: str = None, brand: str = None, summary=None):
    from ecentric_workspace.ai_tools.features.ai_live.application.push_session_summary_service import PushSessionSummaryService
    return _run(lambda: PushSessionSummaryService().execute(frappe.session.user, str(machine or ""), live, brand, summary))


@frappe.whitelist(methods=["GET"])
def viewer_wall():
    from ecentric_workspace.ai_tools.features.ai_live.application.viewer_wall_service import ViewerWallService
    return _run(lambda: ViewerWallService().execute(_roles()))
