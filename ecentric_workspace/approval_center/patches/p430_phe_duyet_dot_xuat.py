# Copyright (c) 2026, eCentric and contributors
"""p430 (23/11/2026, Dot 0 quy trinh nhan su - Hoan chot): Phe duyet dot xuat gui CEO + co rieng tu.

1. Dong bo co `EC Approval Type.private` = 1 cho moi loai khai `ApprovalDefinition.private=True`
   (chi BAT, khong bao gio tat co do quan tri dat).
2. Seed EC Approval Type ADHOC_APPROVAL (route /approvals/adhoc-approval, private=1).
3. Tao trang /approvals/adhoc-approval tu ma nguon.
4. Dung process ADHOC_APPROVAL-V1 (Draft) + SLA (2 ngay LV / Gap 4 gio LV) roi KICH HOAT:
   process Active + the Active (Hoan chot: mo cho moi nguoi ngay khi deploy).
Moi buoc mot khoi try; ket qua ghi Error Log. KHONG nem loi (migrate), KHONG goi ra ngoai,
KHONG xoa du lieu. Chay lai: buoc nao da xong thi bo qua."""
import json
import os

import frappe

CODE = "ADHOC_APPROVAL"
ROUTE = "/approvals/adhoc-approval"
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Building",
            "visibility_mode": "All Internal Users", "legacy_source": "Other"}
_F = "ecentric_workspace.approval_center.features.adhoc_approval.infrastructure."


def _seed_row():
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(base, "seed", "approval_types_seed.json"), encoding="utf-8") as fh:
        return next((r for r in json.load(fh) if r.get("approval_code") == CODE), None)


def _sync_private_flags(ket):
    from ecentric_workspace.approval_center.shared.registry import APPROVAL_DEFINITIONS
    if not frappe.db.has_column("EC Approval Type", "private"):
        ket.append("private: chua co cot (migrate DocType chua chay?)")
        return
    for code, d in APPROVAL_DEFINITIONS.items():
        if getattr(d, "private", False) and frappe.db.exists("EC Approval Type", code) \
                and not frappe.db.get_value("EC Approval Type", code, "private"):
            frappe.db.set_value("EC Approval Type", code, "private", 1)
            ket.append("private=1: %s" % code)


def execute():
    ket = []
    try:
        if frappe.db.exists("EC Approval Type", CODE):
            ket.append("type da co")
        else:
            row = dict(_seed_row() or {"approval_code": CODE, "approval_title": "Phê duyệt đột xuất"})
            if row.get("category") and not frappe.db.exists("EC Approval Category", row["category"]):
                ket.append("thieu category %s -> bo trong" % row.pop("category"))
            doc = frappe.new_doc("EC Approval Type")
            doc.update(DEFAULTS)
            doc.update(row)
            doc.route = ROUTE
            doc.private = 1
            doc.insert(ignore_permissions=True)
            ket.append("da tao type %s" % CODE)
        _sync_private_flags(ket)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("type LOI\n" + frappe.get_traceback())
    try:
        res = frappe.get_module(_F + "page_sync").sync() or {}
        ket.append("page: %s" % res.get("action"))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("page LOI\n" + frappe.get_traceback())
    try:
        r1 = frappe.get_module(_F + "setup").setup_adhoc_approval_v1(dry_run=0, apply=1) or {}
        ket.append("setup: %s %s %s" % (r1.get("result"), r1.get("errors") or "",
                                        r1.get("warnings") or ""))
        r2 = frappe.get_module(_F + "activation").activate_adhoc_approval(
            dry_run=0, apply=1, commit=1) or {}
        ket.append("activate: %s blockers=%s" % (r2.get("result") or r2.get("mode"),
                                                 r2.get("blockers")))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("process LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p430 phe duyet dot xuat", message="\n".join(ket))
