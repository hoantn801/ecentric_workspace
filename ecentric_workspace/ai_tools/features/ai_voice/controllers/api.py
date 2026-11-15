# Copyright (c) 2026, eCentric and contributors
"""API Giong doc AI (trang /ai-voice). Moi ham: service -> envelope {success, message, data}.
Quyen kiem trong service (role), khong dua vao DocPerm - file MP3 private chi phat qua download_audio.
evoice_callback: may eVoice goi (Guest) - kiem chu ky HMAC-SHA256(token, body) truoc moi thu."""
import json

import frappe

from ecentric_workspace.ai_tools.features.ai_voice import constants as C

APP = "ecentric_workspace.ai_tools.features.ai_voice.application."


def _run(fn, commit=False):
    try:
        out = {"success": True, "message": "", "data": fn()}
        if commit:
            frappe.db.commit()  # GET khong tu commit (vd luu cache mau giong)
        return out
    except C.AiVoicePermission as e:
        frappe.db.rollback()
        frappe.local.response["http_status_code"] = 403
        return {"success": False, "message": str(e), "data": None}
    except (C.AiVoiceError, frappe.ValidationError) as e:
        frappe.db.rollback()
        return {"success": False, "message": frappe.utils.strip_html(str(e)) or C.Msg.UNKNOWN, "data": None}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_voice api")
        return {"success": False, "message": C.Msg.UNKNOWN, "data": None}


def _me():
    return frappe.session.user, frappe.get_roles(frappe.session.user)


def _svc(module, cls):
    return getattr(frappe.get_module(APP + module), cls)


def _payload(data):
    if isinstance(data, str):
        try:
            data = json.loads(data or "{}")
        except ValueError:
            raise C.AiVoiceError(C.Msg.UNKNOWN)
    return data if isinstance(data, dict) else {}


def _file(result, inline):
    """result = (ten file, bytes, mime) -> tra file nhi phan; loi -> envelope JSON."""
    if not result.get("success"):
        return result
    fname, content, mime = result["data"]
    frappe.local.response.update({"type": "download", "filename": fname, "filecontent": content,
                                  "content_type": mime, "display_content_as": "inline" if inline else "attachment"})
    return None


# ------------------------------------------------------------------ trang ---

@frappe.whitelist(methods=["GET"])
def get_state():
    user, roles = _me()
    return _run(lambda: _svc("get_state_service", "GetStateService")().execute(user, roles))


@frappe.whitelist(methods=["GET"])
def machine_status(fresh: int = 0):
    _, roles = _me()
    return _run(lambda: _svc("machine_status_service", "MachineStatusService")().execute(roles, bool(int(fresh or 0))))


@frappe.whitelist(methods=["GET"])
def brands():
    user, roles = _me()
    return _run(lambda: _svc("machine_status_service", "MachineStatusService")().brands(user, roles))


# ------------------------------------------------------------------ phieu ---

@frappe.whitelist(methods=["POST"])
def create_job(data=None):
    user, roles = _me()
    return _run(lambda: _svc("create_job_service", "CreateJobService")().execute(user, roles, _payload(data)))


@frappe.whitelist(methods=["GET"])
def list_jobs(scope: str = "mine", status: str = None, start: int = 0, limit: int = C.LIST_LIMIT):
    user, roles = _me()
    svc = _svc("list_jobs_service", "ListJobsService")()
    return _run(lambda: svc.execute(user, roles, str(scope or "mine"), status or None, start, limit))


@frappe.whitelist(methods=["GET"])
def get_job(name: str):
    user, roles = _me()
    return _run(lambda: _svc("list_jobs_service", "ListJobsService")().get(user, roles, str(name or "")))


@frappe.whitelist(methods=["POST"])
def cancel_job(name: str):
    user, roles = _me()
    return _run(lambda: _svc("cancel_job_service", "CancelJobService")().execute(user, roles, str(name or "")))


@frappe.whitelist(methods=["POST"])
def delete_job(name: str):
    user, roles = _me()
    return _run(lambda: _svc("delete_job_service", "DeleteJobService")().execute(user, roles, str(name or "")))


@frappe.whitelist(methods=["GET"])
def download_audio(name: str, dl: int = 0):
    user, roles = _me()
    svc = _svc("audio_service", "AudioService")()
    return _file(_run(lambda: svc.job_audio(user, roles, str(name or ""))), inline=not int(dl or 0))


@frappe.whitelist(methods=["GET"])
def voice_sample(name: str):
    user, roles = _me()
    svc = _svc("audio_service", "AudioService")()
    return _file(_run(lambda: svc.sample(user, roles, str(name or "")), commit=True), inline=True)


# ------------------------------------------------------------------ thu vien giong (quan ly) ---

@frappe.whitelist(methods=["POST"])
def sync_voices():
    _, roles = _me()
    return _run(lambda: _svc("sync_voices_service", "SyncVoicesService")().execute(roles))


@frappe.whitelist(methods=["POST"])
def add_voice(data=None):
    user, roles = _me()
    return _run(lambda: _svc("add_voice_service", "AddVoiceService")().execute(user, roles, _payload(data)))


@frappe.whitelist(methods=["POST"])
def retry_voice(name: str):
    user, roles = _me()
    return _run(lambda: _svc("add_voice_service", "AddVoiceService")().retry(user, roles, str(name or "")))


@frappe.whitelist(methods=["POST"])
def update_voice(name: str, data=None):
    user, roles = _me()
    svc = _svc("update_voice_service", "UpdateVoiceService")()
    return _run(lambda: svc.execute(user, roles, str(name or ""), _payload(data)))


@frappe.whitelist(methods=["POST"])
def remove_voice(name: str, from_machine: int = 0):
    _, roles = _me()
    svc = _svc("remove_voice_service", "RemoveVoiceService")()
    return _run(lambda: svc.execute(roles, str(name or ""), bool(int(from_machine or 0))))


# ------------------------------------------------------------------ cai dat (System Manager) ---

@frappe.whitelist(methods=["GET"])
def get_settings():
    _, roles = _me()
    return _run(lambda: _svc("settings_service", "SettingsService")().get(roles))


@frappe.whitelist(methods=["POST"])
def save_settings(data=None):
    _, roles = _me()
    return _run(lambda: _svc("settings_service", "SettingsService")().save(roles, _payload(data)))


@frappe.whitelist(methods=["POST"])
def test_connection():
    _, roles = _me()
    return _run(lambda: _svc("settings_service", "SettingsService")().test(roles), commit=True)


# ------------------------------------------------------------------ may eVoice goi ve ---

@frappe.whitelist(allow_guest=True, methods=["POST"])
def evoice_callback():
    from ecentric_workspace.ai_tools.features.ai_voice.application.handle_callback_service import (
        BadSignature, HandleCallbackService)
    raw = frappe.request.get_data(cache=True) or b""
    sig = frappe.get_request_header("X-eVoice-Signature") or ""
    try:
        res = HandleCallbackService().execute(raw, sig)
        frappe.db.commit()
        if res == "unknown":                                  # chua thay phieu (giao dich gui chua commit) -> 404
            frappe.local.response["http_status_code"] = 404   # de eVoice gui lai (3 lan); poll van cuu
        return {"ok": res != "unknown", "result": res}
    except BadSignature:
        frappe.local.response["http_status_code"] = 403
        return {"ok": False}
    except Exception:
        frappe.db.rollback()
        frappe.log_error(title="ai_voice callback")
        frappe.local.response["http_status_code"] = 500
        return {"ok": False}
