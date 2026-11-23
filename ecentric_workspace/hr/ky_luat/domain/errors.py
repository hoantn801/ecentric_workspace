# Copyright (c) 2026, eCentric and contributors
"""Loi nghiep vu cua module Ky luat - controller doi sang envelope {success:false, message}."""


class KyLuatError(Exception):
    """Loi nghiep vu co thong diep tieng Viet doc duoc cho nguoi dung."""


class KyLuatForbidden(KyLuatError):
    """Nguoi goi khong co quyen voi ban ghi / thao tac nay."""


class KyLuatNotFound(KyLuatError):
    pass


class FieldErrors(KyLuatError):
    """Nhieu loi theo truong: errors = {fieldname: thong diep}."""

    def __init__(self, errors):
        self.errors = dict(errors or {})
        super().__init__("; ".join(self.errors.values()) or "Dữ liệu chưa hợp lệ.")
