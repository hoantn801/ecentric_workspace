# Copyright (c) 2026, eCentric and contributors
"""Test Host QC chay KHONG can bench: neu chua co frappe thi gan module frappe rong de import duoc repo
(service nhan repo gia qua __init__, khong cham frappe that)."""
import sys
import types

if "frappe" not in sys.modules:
    try:
        import frappe  # noqa: F401
    except ImportError:
        sys.modules["frappe"] = types.ModuleType("frappe")
