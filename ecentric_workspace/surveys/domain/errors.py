# Copyright (c) 2026, eCentric and contributors
"""Loi nghiep vu cua module Khao sat. controllers/api.py doi chung sang envelope
{success: false, message}. Message viet cho NGUOI DUNG doc - tieng Viet, khong traceback."""


class SurveyError(Exception):
    """Du lieu khong hop le / thao tac khong lam duoc o trang thai hien tai."""


class SurveyPermissionError(SurveyError):
    """Khong co quyen."""


class SurveyNotFound(SurveyError):
    """Khao sat khong ton tai (hoac nguoi xem khong duoc biet no ton tai)."""


class AnswerErrors(SurveyError):
    """Cau tra loi khong hop le. `errors` = {question_id: loi} de trang to do dung cau."""

    def __init__(self, message, errors):
        SurveyError.__init__(self, message)
        self.errors = errors
