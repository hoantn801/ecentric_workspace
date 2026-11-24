# Copyright (c) 2026, eCentric and contributors
"""Loi nghiep vu Host QC (tuong duong common/exceptions.py, dat trong module vi chua co noi thu hai dung).

http_status: ma HTTP tang api tra kem envelope. App AI Host QC chi THU LAI khi 5xx / 408 / 429; 4xx khac la
loi du lieu, khong thu lai. Thong diep tieng Viet hien thang cho nguoi dung."""


class HostQCError(Exception):
    http_status = 400

    def __init__(self, message="", data=None):
        super().__init__(message)
        self.data = data


class AuthError(HostQCError):
    http_status = 401


class TooManyAttempts(AuthError):
    http_status = 429


class ForbiddenError(HostQCError):
    http_status = 403


class NotFoundError(HostQCError):
    http_status = 404


class InvalidInput(HostQCError):
    http_status = 400
