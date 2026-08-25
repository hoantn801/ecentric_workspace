# Copyright (c) 2026, eCentric and contributors
"""Re-sync EVERY Approval Center page (hub, all-requests, dashboard, 26 forms).

Ships:
  * tải tệp báo LỖI THẬT (kể cả 413 'tệp quá lớn') thay vì hiện 'Chưa có tệp nào';
  * danh sách tệp đã tải không còn biến mất khi form vẽ lại;
  * Brand chọn từ danh sách Brand có sẵn (daily_target);
  * mọi trang căn giữa + rộng tới 1600px nên màn to không lệch hẳn sang trái.

Force where the live copy is stale: các patch resync trước (p066, p068) chạy trong migrate
mà KHÔNG ghi được gì và cũng không báo lỗi -- 19-20 trang phải sync tay qua endpoint mới lên.
Nên patch này (a) so bằng marker của chính bản đang ship, (b) dùng force=1 khi live khác, và
(c) log kết quả + mọi lỗi ra Error Log để lần sau không phải mò."""
import importlib

import frappe

from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS

_FEATURE = "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync"
_UI = ("ecentric_workspace.approval_center.ui.hub.page_sync",
       "ecentric_workspace.approval_center.ui.all_requests.page_sync",
       "ecentric_workspace.approval_center.ui.dashboard.page_sync")
_MARKER = "margin-inline:auto"


def _sync(module, label, done, failed):
    try:
        route = getattr(module, "ROUTE", None)
        name = frappe.db.get_value("Web Page", {"route": route}, "name") if route else None
        if not name:
            return
        live = frappe.db.get_value("Web Page", name, "main_section") or ""
        if _MARKER in live:
            return                                   # already current
        if "force" in getattr(module.sync, "__code__", None).co_varnames:
            result = module.sync(force=1) or {}
        else:
            result = module.sync() or {}
        done.append((label, result.get("action")))
    except Exception:
        failed.append(label)
        frappe.log_error(frappe.get_traceback(), "p069 resync failed: %s" % label)


def execute():
    done, failed, seen = [], [], set()
    for path in _UI:
        try:
            _sync(importlib.import_module(path), path.rsplit(".", 2)[-2], done, failed)
        except Exception:
            failed.append(path)
            frappe.log_error(frappe.get_traceback(), "p069 import failed: %s" % path)
    for definition in APPROVAL_DEFINITIONS.values():
        feature = getattr(definition, "feature", "") or ""
        if not feature or feature in seen:
            continue
        seen.add(feature)
        try:
            _sync(importlib.import_module(_FEATURE % feature), feature, done, failed)
        except Exception:
            failed.append(feature)
            frappe.log_error(frappe.get_traceback(), "p069 import failed: %s" % feature)
    frappe.logger("approval_center").info("p069 done=%s failed=%s" % (done, failed))
    frappe.log_error("p069 synced=%s failed=%s" % (done, failed), "p069 resync summary")
