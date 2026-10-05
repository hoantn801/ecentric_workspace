# Copyright (c) 2026, eCentric and contributors
"""Nut "Chuyen nguoi xu ly" cho Hiring Request + Daily Target (05/10/2026, Hoan).

Hai form nay co buoc xu ly (bind_fulfillment -> endpoint list_reassign_targets /
reassign_fulfillment da co) nhung trang chua ve nut: anh Tuan nhan Hiring 00007 roi khong
chuyen cho Luc duoc. UI o asset dung chung public/js/ec_reassign.bundle.js. Ban nay chi RESYNC
hai trang; trang bi tu choi (lech khoa) -> ghi Error Log, khong nem loi."""
import frappe

_FEATURES = ("hiring_request", "daily_target")
_LANDMARK = "EcReassign.buttonHTML(cap)"


def execute():
    ket = []
    for feature in _FEATURES:
        try:
            mod = frappe.get_module(
                "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
            res = mod.sync() or {}
            html = frappe.db.get_value("Web Page", {"route": mod.ROUTE}, "main_section_html") or ""
            ket.append("%s: %s, landmark=%s" % (feature, res.get("action"), _LANDMARK in html))
        except Exception:
            ket.append("%s LOI\n%s" % (feature, frappe.get_traceback()))
    frappe.log_error(title="p260 nut chuyen nguoi xu ly", message="\n".join(ket))
