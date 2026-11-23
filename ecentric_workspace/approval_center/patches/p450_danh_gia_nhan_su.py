# Copyright (c) 2026, eCentric and contributors
"""Danh gia nhan su + khao sat moc (23/11/2026, HR Dot 2 - Hoan chot 22-23/11).

Moi buoc mot khoi try, ket qua ghi Error Log; KHONG nem loi (migrate gay = rollback ca deploy),
KHONG xoa du lieu, KHONG goi ra ngoai (khong Graph / Teams), khong gui thong bao:
  1. seed EC Approval Type EMPLOYEE_REVIEW (chua co thi tao, co roi giu nguyen);
  2. tao / lam moi 3 trang tu nguon repo:
       /approvals/employee-review   (form, co khoa chong troi)
       /ec-hr/danh-gia-nhan-su      (hang cho C&B)
       /khao-sat/ca-nhan            (ket qua khao sat moc)
  3. mau tieu chi TAM (5 tieu chi chung) neu chua co mau nao;
  4. dung 2 process EMPLOYEE_REVIEW_TV-V1 / _HD-V1 (Draft) + SLA -> UAT (Active) -> publish (the
     chi hien voi C&B). Validate khong qua thi de nguyen va ghi ly do.
Chay lai: type co roi / trang dung noi dung / process Active -> bo qua."""
import json
import os

import frappe

CODE = "EMPLOYEE_REVIEW"
ROUTE = "/approvals/employee-review"
DEFAULTS = {"card_status": "Coming Soon", "process_status": "Building",
            "visibility_mode": "Restricted Roles", "legacy_source": "ERP"}
_F = "ecentric_workspace.approval_center.features.employee_review.infrastructure."
PAGES = (
    _F + "page_sync",
    "ecentric_workspace.hr.pages.danh_gia_nhan_su.page_sync",
    "ecentric_workspace.surveys.pages.ca_nhan.page_sync",
)


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
            doc.update(_seed_row() or {"approval_code": CODE, "approval_title": "Đánh giá nhân sự"})
            doc.route = ROUTE
            doc.insert(ignore_permissions=True)
            ket.append("da tao type %s" % CODE)
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("type LOI\n" + frappe.get_traceback())
    for mod in PAGES:
        try:
            res = frappe.get_module(mod).sync() or {}
            ket.append("page %s: %s" % (mod.rsplit(".", 2)[-2], res.get("action")))
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            ket.append("page %s LOI\n%s" % (mod, frappe.get_traceback()))
    try:
        setup = frappe.get_module(_F + "setup")
        ket.append("mau tieu chi tam: %s" % setup.dam_bao_mau_tieu_chi_tam())
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("mau tieu chi LOI\n" + frappe.get_traceback())
    try:
        setup = frappe.get_module(_F + "setup")
        act = frappe.get_module(_F + "activation")
        r1 = setup.setup_employee_review_v1(dry_run=0, apply=1) or {}
        ket.append("setup: %s %s %s" % (r1.get("result"), r1.get("errors") or "", r1.get("warnings") or ""))
        r2 = act.enable_employee_review_uat(dry_run=0, apply=1, commit=1) or {}
        ket.append("uat: %s blockers=%s" % (r2.get("result") or r2.get("mode"), r2.get("blockers")))
        r3 = act.publish_employee_review(dry_run=0, apply=1, commit=1) or {}
        ket.append("publish: %s blockers=%s" % (r3.get("result") or r3.get("mode"), r3.get("blockers")))
        frappe.db.commit()
    except Exception:
        frappe.db.rollback()
        ket.append("process LOI\n" + frappe.get_traceback())
    frappe.log_error(title="p450 danh gia nhan su", message="\n".join(ket))
