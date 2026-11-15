# Copyright (c) 2026, eCentric and contributors
"""Dependency mac dinh cho service Giong doc AI (nap muon de test chay khong can Frappe)."""
from ecentric_workspace.ai_tools.features.ai_voice import constants as C

JOB_PREFIX = "ecentric_workspace.ai_tools.features.ai_voice.jobs."


def jobs():
    from ecentric_workspace.ai_tools.features.ai_voice.repositories.job_repository import JobRepository
    return JobRepository()


def profiles():
    from ecentric_workspace.ai_tools.features.ai_voice.repositories.profile_repository import ProfileRepository
    return ProfileRepository()


def settings():
    from ecentric_workspace.ai_tools.features.ai_voice.repositories.settings_repository import SettingsRepository
    return SettingsRepository()


def files():
    from ecentric_workspace.ai_tools.features.ai_voice.repositories.file_repository import FileRepository
    return FileRepository()


def client_factory(settings_repo):
    """Tra ve ham tao EVoiceClient tu cai dat hien tai (doc lai moi lan - doi token tren UI la ap ngay)."""
    def make(timeout=None):
        import frappe
        from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceClient
        if frappe.conf.get(C.KILL_SWITCH):              # tat khan: khong goi may o bat ky duong nao
            raise C.AiVoiceError(C.Msg.PAUSED)
        s = settings_repo.get(with_token=True)
        if not s.get("token") or not s.get("base_url"):
            raise C.AiVoiceError(C.Msg.NOT_CONFIGURED)
        return EVoiceClient(s["base_url"], s["token"], timeout=timeout or s.get("timeout") or C.DEFAULT_TIMEOUT)
    return make


def enqueue(job_module, **kwargs):
    """Chay job nen sau khi giao dich hien tai commit (tranh job doc phieu chua ton tai)."""
    import frappe
    queue = kwargs.pop("queue", "short")
    timeout = kwargs.pop("timeout", 300)
    frappe.enqueue(JOB_PREFIX + job_module + ".run", queue=queue, timeout=timeout, enqueue_after_commit=True, **kwargs)


def publish(user, job):
    """Bao trang /ai-voice cua chu phieu (realtime). Loi socket khong lam hong nghiep vu."""
    try:
        import frappe
        frappe.publish_realtime("ai_voice_job", job, user=user, after_commit=True)
    except Exception:  # noqa: BLE001
        pass


def after_commit(fn):
    """Chay fn SAU khi giao dich hien tai commit (vd xoa file ben may chi khi ERP da luu chac)."""
    import frappe
    hooks = getattr(frappe.db, "after_commit", None)
    if hooks is not None and hasattr(hooks, "add"):
        hooks.add(fn)
    else:  # pragma: no cover - Frappe cu
        fn()


def now():
    import frappe
    return frappe.utils.now_datetime()


def cache():
    import frappe
    return frappe.cache()
