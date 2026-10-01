# Copyright (c) 2026, eCentric and contributors
"""Ai lam duoc gi voi khao sat. Day la BIEN GIOI BAO MAT cua module: DocType chi cap quyen
System Manager, nen moi duong doc / ghi cua nguoi dung deu phai qua cac ham o day.

  * Tao khao sat      : role EC Survey Creator / HR Manager / System Manager.
  * Soan + xem ket qua: nguoi tao, nguoi cung quan ly (bang editors), System Manager.
  * Lam khao sat      : nguoi nam trong doi tuong (domain/audience.py) khi khao sat dang mo.
  * Xem truoc         : nguoi soan (khong nop duoc).
"""
from ecentric_workspace.surveys import constants as C
from ecentric_workspace.surveys.domain import audience
from ecentric_workspace.surveys.domain.errors import SurveyNotFound, SurveyPermissionError


class Ctx:
    """Nguoi dang goi. controllers/api.py dung tu frappe.session; test tu dung tay."""

    def __init__(self, user, roles):
        self.user = user
        self.roles = set(roles or [])

    @property
    def is_admin(self):
        return self.user == "Administrator" or bool(self.roles & set(C.ADMIN_ROLES))

    @property
    def can_create(self):
        return self.is_admin or bool(self.roles & set(C.CREATOR_ROLES))


def editors_of(survey):
    return {r.get("user") for r in survey.get("editors") or [] if r.get("user")}


def can_manage(ctx, survey):
    return bool(survey) and (ctx.is_admin or survey.get("owner") == ctx.user
                             or ctx.user in editors_of(survey))


def require_create(ctx):
    if not ctx.can_create:
        raise SurveyPermissionError("Bạn chưa có quyền tạo khảo sát. Nhờ HR cấp quyền "
                                    "“%s”." % C.ROLE_CREATOR)


def require_manage(ctx, survey):
    if not survey:
        raise SurveyNotFound("Không tìm thấy khảo sát.")
    if not can_manage(ctx, survey):
        raise SurveyPermissionError("Bạn không quản lý khảo sát này.")


def eligible_set(repo, survey, cache=None):
    """Tap user duoc lam khao sat. `cache` (dict) de dung chung danh sach nhan su / phong ban
    khi tinh cho nhieu khao sat trong mot request."""
    cache = cache if cache is not None else {}
    if "emps" not in cache:
        cache["emps"] = repo.employees()
        cache["depts"] = repo.departments()
    return audience.eligible_users(survey.get("audience_mode"), survey.get("targets") or [],
                                   cache["emps"], cache["depts"])


def is_eligible(repo, ctx, survey, cache=None):
    return ctx.user in eligible_set(repo, survey, cache)
