# Copyright (c) 2026, eCentric and contributors
"""Dependency mac dinh cho service Ban quyen AI Live (nap muon de test chay khong can Frappe) + ham dung chung."""
import time

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R


def settings():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.license_settings_repository import LicenseSettingsRepository
    return LicenseSettingsRepository()


def machines():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.license_machine_repository import LicenseMachineRepository
    return LicenseMachineRepository()


def dists():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.license_dist_repository import LicenseDistRepository
    return LicenseDistRepository()


def events():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.license_event_repository import LicenseEventRepository
    return LicenseEventRepository()


def locks():
    from ecentric_workspace.ai_tools.features.ai_live.repositories.license_lock_repository import LicenseLockRepository
    return LicenseLockRepository()


def notifier():
    from ecentric_workspace.ai_tools.features.ai_live.infrastructure.license_notify_queue import LicenseNotifyQueue
    return LicenseNotifyQueue()


def clock():
    return time.time


# ------------------------------------------------------------------ dung chung ---
def require_admin(roles):
    if not set(roles or ()) & set(L.ADMIN_ROLES):
        raise L.LicensePermission(L.Msg.NEED_ADMIN)


def guid_key(guid_h):
    return "g:" + guid_h


def seen_vals(p, ip, now, clone=False):
    """So lieu bao ve tu payload. May nghi nhan ban: KHONG ghi de ten may / card mang (2 may that dung chung ban ghi)."""
    out = {"last_seen": now, "last_ip": ip}
    if not clone:
        out.update(host=p["host"], win_user=p["user"], os=p["os"])
    return out


def install_seen(p, now, ip):
    out = {"last_checkin": now, "last_checkin_ip": ip}
    for k in ("build_id", "app_dir"):
        if p.get(k):
            out[k] = p[k]
    return out


def install_of(machine, product):
    return next((i for i in (machine or {}).get("installs") or [] if i.get("product") == product), None)


def check_clone(machine, p):
    """-> True khi lan nay moi phat hien nghi nhan ban (chua bat co)."""
    return bool(machine) and not machine.get("clone_warning") and R.is_clone(machine, p["fp"], p["host"])
