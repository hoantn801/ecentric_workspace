# Copyright (c) 2026, eCentric and contributors
"""Loi nghiep vu cua module Dao tao / Quiz. controllers/api.py doi sang envelope
{success: false, message}. Message viet cho NGUOI DUNG doc - tieng Viet, khong traceback."""


class QuizError(Exception):
    """Du lieu khong hop le / thao tac khong lam duoc o trang thai hien tai."""


class QuizPermissionError(QuizError):
    """Khong co quyen."""


class QuizNotFound(QuizError):
    """Khong ton tai (hoac nguoi xem khong duoc biet no ton tai)."""


class FieldErrors(QuizError):
    """Du lieu soan sai. `errors` = {khoa: loi} de trang to do dung cho (vd "q3.options")."""

    def __init__(self, message, errors):
        QuizError.__init__(self, message)
        self.errors = errors
