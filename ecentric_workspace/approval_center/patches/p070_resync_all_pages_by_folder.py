# Copyright (c) 2026, eCentric and contributors
"""Re-sync EVERY Approval Center page -- discovered from disk, not from definition.feature.

ROOT CAUSE của việc p066/p068/p069 'chạy mà không đổi gì': chúng duyệt
APPROVAL_DEFINITIONS rồi lấy `definition.feature` để dựng đường dẫn module. Nhưng chỉ 6/26
definition có đặt `feature`; 20 cái còn lại để rỗng, nên vòng lặp `if not feature: continue`
BỎ QUA đúng 20 form -- im lặng, không lỗi, không log. Mỗi lần deploy lại phải sync tay đúng
ngần ấy trang.

Patch này liệt kê thư mục features/*/infrastructure/page_sync.py trên đĩa, nên không phụ
thuộc metadata nào cả: có trang thì có sync. Ghi đè khi bản live khác bản đang ship (so bằng
sha256 nội dung, không đoán marker), dùng force=1 để không bị #144 drift lock chặn; publish
vẫn 'preserve'. Kết quả + lỗi ghi ra Error Log."""
import hashlib
import importlib
import os
import re

import frappe

_HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # .../approval_center
_FEATURES = os.path.join(_HERE, "features")
_UI = ("ecentric_workspace.approval_center.ui.hub.page_sync",
       "ecentric_workspace.approval_center.ui.all_requests.page_sync",
       "ecentric_workspace.approval_center.ui.dashboard.page_sync")


def _sha(text):
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _sync(module, label, done, failed, skipped):
    try:
        route = getattr(module, "ROUTE", None)
        name = frappe.db.get_value("Web Page", {"route": route}, "name") if route else None
        if not name:
            skipped.append((label, "no live page"))
            return
        live = frappe.db.get_value("Web Page", name, "main_section") or ""
        shipped = module._html()
        if _sha(live) == _sha(shipped):
            skipped.append((label, "unchanged"))
            return
        if "force" in getattr(module.sync, "__code__").co_varnames:
            result = module.sync(force=1) or {}
        else:
            result = module.sync() or {}
        done.append((label, result.get("action")))
    except Exception:
        failed.append(label)
        frappe.log_error(frappe.get_traceback(), "p070 resync failed: %s" % label)


def execute():
    done, failed, skipped = [], [], []
    for path in _UI:
        try:
            _sync(importlib.import_module(path), path.rsplit(".", 2)[-2], done, failed, skipped)
        except Exception:
            failed.append(path)
            frappe.log_error(frappe.get_traceback(), "p070 import failed: %s" % path)

    try:
        features = sorted(f for f in os.listdir(_FEATURES)
                          if os.path.isfile(os.path.join(_FEATURES, f, "infrastructure", "page_sync.py")))
    except Exception:
        features = []
        frappe.log_error(frappe.get_traceback(), "p070: cannot list features/")

    for feature in features:
        try:
            module = importlib.import_module(
                "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
            _sync(module, feature, done, failed, skipped)
        except Exception:
            failed.append(feature)
            frappe.log_error(frappe.get_traceback(), "p070 import failed: %s" % feature)

    summary = ("p070 pages_found=%d synced=%d failed=%d\nsynced=%s\nskipped=%s\nfailed=%s"
               % (len(features) + len(_UI), len(done), len(failed), done, skipped, failed))
    frappe.logger("approval_center").info(summary)
    frappe.log_error(summary, "p070 resync summary")
