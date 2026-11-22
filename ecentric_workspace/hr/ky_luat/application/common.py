# Copyright (c) 2026, eCentric and contributors
"""Tien ich dung chung cua cac service Ky luat (thuan Python)."""
from ecentric_workspace.hr.ky_luat import constants as C
from ecentric_workspace.hr.ky_luat.domain.errors import FieldErrors, KyLuatNotFound

SYSTEM_ACTOR = "Hệ thống"


def log(repo, actor, action, note=""):
    return {"at": repo.now(), "actor": actor or SYSTEM_ACTOR, "action": action, "note": (note or "")[:1000]}


def text(v, maxlen=None):
    s = ("" if v is None else str(v)).strip()
    return s[:maxlen] if maxlen else s


def found(obj, what="hồ sơ"):
    if not obj:
        raise KyLuatNotFound("Không tìm thấy %s." % what)
    return obj


def hr_users(repo):
    return repo.users_with_roles(C.HR_ROLES)


def route_notice(name):
    return "%s?tab=the-vang&ma=%s" % (C.ROUTE, name)


def route_case(name):
    return "%s?tab=ho-so&ma=%s" % (C.ROUTE, name)


def int_setting(settings, key, default):
    try:
        v = int(settings.get(key) or 0)
        return v if v > 0 else default
    except (TypeError, ValueError):
        return default


FILE_FIELDS = ("evidence", "violation_record", "meeting_minutes", "decision_draft")


def require_own_files(repo, ctx, values, before=None):
    """Moi o tep MOI (khac gia tri da luu) phai la tep rieng tu cua chinh nguoi bam."""
    before = before or {}
    bad = {}
    for f in FILE_FIELDS:
        url = values.get(f)
        if url and url != before.get(f) and not repo.file_ok(url, ctx.user):
            bad[f] = "Tệp không hợp lệ - tải lên lại (tệp phải do chính bạn tải, ở chế độ riêng tư)."
    if bad:
        raise FieldErrors(bad)
