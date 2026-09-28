# Copyright (c) 2026, eCentric and contributors
"""Seed EC Approval Type OFFER_REQUEST + NEW_STAFF_PREPARATION (28/09/2026). Idempotent -
cung khuon p178. Co san `route` ngay tu dau (khac p178): hai phieu nay KHONG mo tu the tren
Approval Center (Offer mo tu nut "Tao Offer" tren Hiring, NSP tu tao) nhung ToDo / Action
Center / thong bao can route de dan link dung; the van "Coming Soon" (an)."""
import json
import os

import frappe

DOCTYPE = "EC Approval Type"
ROUTES = {"OFFER_REQUEST": "/approvals/offer-request",
          "NEW_STAFF_PREPARATION": "/approvals/new-staff-preparation"}
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Building",
            "visibility_mode": "All Internal Users", "legacy_source": "MS Teams"}


def _seed_rows():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), "r", encoding="utf-8") as fh:
        return {r["approval_code"]: r for r in json.load(fh) if r.get("approval_code") in ROUTES}


def execute():
    ket = []
    try:
        if not frappe.db.exists("DocType", DOCTYPE):
            return
        rows = _seed_rows()
        for code, route in ROUTES.items():
            if frappe.db.exists(DOCTYPE, code):
                ket.append("%s da co" % code)
                continue
            row = rows.get(code)
            if not row:
                ket.append("%s khong co trong seed" % code)
                continue
            if row.get("category") and not frappe.db.exists("EC Approval Category", row["category"]):
                ket.append("%s: thieu category %s" % (code, row["category"]))
                continue
            doc = frappe.new_doc(DOCTYPE)
            doc.update(DEFAULTS)
            doc.update(row)
            doc.route = route
            doc.insert(ignore_permissions=True)
            ket.append("Da tao %s (route %s)" % (code, route))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("LOI:\n" + frappe.get_traceback())
    frappe.log_error(title="p219 seed offer/nsp types", message="\n".join(ket))
