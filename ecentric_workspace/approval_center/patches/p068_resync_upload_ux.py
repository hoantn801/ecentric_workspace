# Copyright (c) 2026, eCentric and contributors
"""Re-sync form pages after the attachment/checkbox UX fixes (loud, force where stale).

Ships: bỏ auto-save-nháp khi tải tệp (nó làm server báo 'Value missing for ... Request Title'),
danh sách tệp đã tải kèm nút xóa, ô chọn hiện dấu tích thật, và 'Kênh khác' chỉ hiện khi tích
Other. Ghi đè khi live còn bản cũ (so bằng marker renderFileList); mọi lỗi ra Error Log."""
import importlib

import frappe

from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS

_MODULE = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync"
_MARKER = "function renderFileList("


def execute():
    done, failed = [], []
    seen = set()
    for definition in APPROVAL_DEFINITIONS.values():
        feature = getattr(definition, "feature", "") or ""
        if not feature or feature in seen:
            continue
        seen.add(feature)
        try:
            module = importlib.import_module(_MODULE % feature)
            route = getattr(module, "ROUTE", None)
            name = frappe.db.get_value("Web Page", {"route": route}, "name") if route else None
            if not name:
                continue
            html = frappe.db.get_value("Web Page", name, "main_section") or ""
            ships_marker = _MARKER in (module._html() or "")
            if ships_marker and _MARKER in html:
                continue                       # already current
            done.append((feature, (module.sync(force=1) or {}).get("action")))
        except Exception:
            failed.append(feature)
            frappe.log_error(frappe.get_traceback(), "p068 resync failed: %s" % feature)
    frappe.logger("approval_center").info("p068 done=%s failed=%s" % (done, failed))
    if failed:
        frappe.log_error("p068 failed for: %s" % failed, "p068: form pages not re-synced")
