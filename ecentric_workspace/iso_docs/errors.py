# Copyright (c) 2026, eCentric and contributors
"""Loi nghiep vu cua thu vien tai lieu ISO - events.py doi sang frappe.throw."""


class DocError(Exception):
    """Du lieu tai lieu khong hop le (ma sai, pham vi sai, tich thong bao sai...)."""
