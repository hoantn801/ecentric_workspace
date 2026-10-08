# Copyright (c) 2026, eCentric and contributors
"""API trang /ai-video (AI Video hang loat). Moi ham: kiem quyen -> service -> envelope.

VI SAO rollback khi bat loi: bat exception trong ham whitelist nghia la Frappe KHONG tu
rollback nua - phai tu rollback de khong luu nua chung (vd da enqueue ma chua ghi stage)."""
import frappe

from ecentric_workspace.ai_tools.features.ai_video.application import service as svc
from ecentric_workspace.ai_tools.features.ai_video.application import groups
from ecentric_workspace.ai_tools.features.ai_video.infrastructure.worker_client import WorkerDown

MSG_UNKNOWN = "Không thực hiện được. Thử lại sau ít phút, nếu vẫn lỗi thì báo IT."


def _run(fn):
    try:
        svc.check_role()
        return {"success": True, "message": "", "data": fn()}
    except WorkerDown as e:
        frappe.db.rollback()
        return {"success": False, "message": str(e), "data": {"worker_down": True}}
    except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError) as e:
        frappe.db.rollback()
        return {"success": False, "message": frappe.utils.strip_html(str(e)) or MSG_UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_video api")
        return {"success": False, "message": MSG_UNKNOWN, "data": None}


@frappe.whitelist(methods=["GET"])
def list_projects():
    return _run(svc.list_projects)


@frappe.whitelist(methods=["POST"])
def create_project(data: str):
    return _run(lambda: svc.create_project(data))


@frappe.whitelist(methods=["POST"])
def update_project(name: str, data: str):
    return _run(lambda: svc.update_project(name, data))


@frappe.whitelist(methods=["GET"])
def get_project(name: str, tick: int = 0):
    return _run(lambda: svc.get_project(name, tick))


@frappe.whitelist(methods=["POST"])
def add_items(project: str, rows: str):
    return _run(lambda: svc.add_items(project, rows))


@frappe.whitelist(methods=["POST"])
def update_item(name: str, data: str):
    return _run(lambda: svc.update_item(name, data))


@frappe.whitelist(methods=["POST"])
def delete_item(name: str):
    return _run(lambda: svc.delete_item(name))


@frappe.whitelist(methods=["POST"])
def start_holds(project: str, names: str):
    return _run(lambda: svc.start_holds(project, names))


@frappe.whitelist(methods=["POST"])
def pick(name: str, candidate: str):
    return _run(lambda: svc.pick(name, candidate))


@frappe.whitelist(methods=["POST"])
def regen_holds(name: str, data: str = None):
    return _run(lambda: svc.regen_holds(name, data))


@frappe.whitelist(methods=["POST"])
def approve(name: str):
    return _run(lambda: svc.approve(name))


@frappe.whitelist(methods=["POST"])
def regen_clip(name: str, dirs: str = None, unit: str = None):
    return _run(lambda: svc.regen_clip(name, dirs, unit))


@frappe.whitelist(methods=["POST"])
def retry(name: str):
    return _run(lambda: svc.retry(name))


@frappe.whitelist(methods=["POST"])
def cancel_project(project: str):
    return _run(lambda: svc.cancel_project(project))


@frappe.whitelist(methods=["POST"])
def mix(project: str, data: str):
    return _run(lambda: svc.mix(project, data))


@frappe.whitelist(methods=["POST"])
def regen_anchor(project: str):
    return _run(lambda: svc.regen_anchor(project))


@frappe.whitelist(methods=["POST"])
def regen_talk(project: str, ids: str):
    return _run(lambda: svc.regen_talk(project, ids))


@frappe.whitelist(methods=["POST"])
def set_talks(project: str, off: str):
    return _run(lambda: svc.set_talks(project, off))


@frappe.whitelist(methods=["POST"])
def set_units(name: str, off: str):
    return _run(lambda: svc.set_units(name, off))


@frappe.whitelist(methods=["POST"])
def archive_project(name: str, on: int = 1):
    return _run(lambda: svc.archive_project(name, on))


@frappe.whitelist(methods=["POST"])
def delete_project(name: str):
    return _run(lambda: svc.delete_project(name))


@frappe.whitelist(methods=["GET"])
def prompts_get():
    return _run(svc.prompts_get)


@frappe.whitelist(methods=["POST"])
def prompts_set(data: str):
    return _run(lambda: svc.prompts_set(data))


@frappe.whitelist(methods=["GET"])
def groups_get():
    return _run(groups.groups_get)


@frappe.whitelist(methods=["POST"])
def groups_set(data: str):
    return _run(lambda: groups.groups_set(data))


@frappe.whitelist(methods=["POST"])
def groups_rollback(cat: str, v: str):
    return _run(lambda: groups.groups_rollback(cat, v))


@frappe.whitelist(methods=["POST"])
def group_request(data: str):
    return _run(lambda: groups.group_request(data))


@frappe.whitelist(methods=["GET"])
def worker_ping():
    return _run(svc.worker_ping)


@frappe.whitelist(allow_guest=True, methods=["POST"])
def register_worker(url: str = None, ts: str = None, sig: str = None):
    """Goi tu worker (khong co phien dang nhap): xac thuc bang chu ky HMAC, khong bang role."""
    from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client as wc
    try:
        ok = wc.register(url, ts, sig)
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_video register_worker")
        ok = False
    if ok:
        frappe.db.commit()
    return {"success": bool(ok), "message": "" if ok else "rejected", "data": None}
