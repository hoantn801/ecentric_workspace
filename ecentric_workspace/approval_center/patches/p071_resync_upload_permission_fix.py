# Copyright (c) 2026, eCentric and contributors
"""Re-sync form pages sau khi bỏ doctype/docname khỏi lệnh tải tệp (lỗi phân quyền).

Dùng lại cách quét theo thư mục của p070 (không phụ thuộc definition.feature -- thứ đã khiến
p066/p068/p069 bỏ qua im lặng 20 form)."""
import hashlib
import importlib
import os

import frappe

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_FEATURES = os.path.join(_HERE, "features")


def execute():
    done, failed = [], []
    try:
        features = sorted(f for f in os.listdir(_FEATURES)
                          if os.path.isfile(os.path.join(_FEATURES, f, "infrastructure", "page_sync.py")))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p071: cannot list features/")
        return
    for feature in features:
        try:
            m = importlib.import_module(
                "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
            route = getattr(m, "ROUTE", None)
            name = frappe.db.get_value("Web Page", {"route": route}, "name") if route else None
            if not name:
                continue
            live = frappe.db.get_value("Web Page", name, "main_section") or ""
            shipped = m._html()
            if hashlib.sha256(live.encode("utf-8")).hexdigest() == hashlib.sha256(shipped.encode("utf-8")).hexdigest():
                continue
            done.append((feature, (m.sync(force=1) or {}).get("action")))
        except Exception:
            failed.append(feature)
            frappe.log_error(frappe.get_traceback(), "p071 resync failed: %s" % feature)
    frappe.log_error("p071 synced=%s failed=%s" % (done, failed), "p071 resync summary")
