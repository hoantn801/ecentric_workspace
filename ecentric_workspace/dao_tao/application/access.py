# Copyright (c) 2026, eCentric and contributors
"""Ai lam duoc gi. BIEN GIOI BAO MAT cua module: DocType chi cap quyen System Manager, moi duong
doc / ghi cua nguoi dung deu qua cac ham o day.

  * Soan bo quiz, MO PHONG, dieu khien phong, soan bai hoc, kiem tra bai thuc hanh:
    Ban dao tao (role EC Training Host) + team HR (HR Manager / HR User) + System Manager (Hoan).
    Hoan 12/11: "chi ban dao tao, team HR va minh truoc". Ca nhom dung chung moi bo quiz / phong
    (mot nguoi may hong thi nguoi khac dieu khien tiep duoc).
  * Choi quiz, hoc bai, binh chon: moi tai khoan noi bo da dang nhap.
"""
from ecentric_workspace.dao_tao import constants as C
from ecentric_workspace.dao_tao.domain.errors import QuizNotFound, QuizPermissionError


class Ctx:
    """Nguoi dang goi. controllers/api.py dung tu frappe.session; test tu dung tay."""

    def __init__(self, user, roles):
        self.user = user
        self.roles = set(roles or [])

    @property
    def is_admin(self):
        return self.user == "Administrator" or bool(self.roles & set(C.ADMIN_ROLES))

    @property
    def can_host(self):
        return self.is_admin or bool(self.roles & set(C.HOST_ROLES))


def require_host(ctx):
    if not ctx.can_host:
        raise QuizPermissionError("Chỉ Ban đào tạo và team HR mở phòng / soạn bài được. Cần quyền "
                                  "thì nhờ HR cấp role “%s”." % C.ROLE_HOST)


def require_found(obj, what="nội dung"):
    if not obj:
        raise QuizNotFound("Không tìm thấy %s." % what)
    return obj
