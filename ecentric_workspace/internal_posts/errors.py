# Copyright (c) 2026, eCentric and contributors
"""Loi nghiep vu cua Tin noi bo - api.py doi thanh {success: False, message} + ma HTTP.
Tach rieng (03/10) de service / ack / comments cung dung ma khong import vong."""


class NotFound(Exception):
    """Khong co bai nay (hoac slug sai)."""


class Forbidden(Exception):
    """Co bai nhung nguoi nay khong duoc doc - trang tra 403, khong lo tieu de."""


class PostError(Exception):
    """Loi nguoi dung gay ra (tham so sai) - api tra success False kem thong diep."""
