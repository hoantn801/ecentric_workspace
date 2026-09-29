# Copyright (c) 2026, eCentric and contributors
"""Clearance Request (29/09/2026): seed EC Approval Type CLEARANCE_REQUEST (route co san, the
"Coming Soon" - phieu TU TAO tu Don nghi viec), tao trang /approvals/clearance-request, dung +
bat (UAT) process CLEARANCE_REQUEST-V1 (Each Group: Line Manager / Operation / HR / HOF).
Moi buoc mot khoi try; ket qua ghi Error Log. Validate khong qua thi process de Draft, ghi ly do.
Chay lai: type co roi / trang dung sha / process Active -> bo qua. Khong nem loi (migrate)."""
import json
import os

import frappe

CODE = "CLEARANCE_REQUEST"
ROUTE = "/approvals/clearance-request"
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Building",
            "visibility_mode": "All Internal Users", "legacy_source": "MS Teams"}
_F = "ecentric_workspace.approval_center.features.clearance_request.infrastructure."


def _seed_row():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), encoding="utf-8") as fh:
        return next((r for r in json.load(fh) if r.get("approval_code") == CODE), None)


def execute():
    ket = []
    try:
        if frappe.db.exists("EC Approval Type", CODE):
            ket.append("type da co")
        else:
            doc = frappe.new_doc("EC Approval Type")
            doc.update(DEFAULTS)
            doc.update(_seed_row() or {"approval_code": CODE, "approval_title": "Clearance Request"})
            doc.route = ROUTE
            doc.insert(ignore_permissions=True)
            ket.append("da tao type %s" % CODE)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("type LOI\n" + frappe.get_traceback())
    try:
        res = frappe.get_module(_F + "page_sync").sync() or {}
        ket.append("page: %s" % res.get("action"))
    except Exception:
        ket.append("page LOI\n" + frappe.get_traceback())
    try:
        r1 = frappe.get_module(_F + "setup").setup_clearance_request_v1(dry_run=0, apply=1) or {}
        ket.append("setup: %s %s" % (r1.get("result"), r1.get("errors") or ""))
        r2 = frappe.get_module(_F + "activation").enable_clearance_request_uat(
            dry_run=0, apply=1, commit=1) or {}
        ket.append("uat: %s blockers=%s" % (r2.get("result") or r2.get("mode"), r2.get("blockers")))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("process LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p233 clearance request", message="\n".join(ket))
