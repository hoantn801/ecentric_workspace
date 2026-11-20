# Copyright (c) 2026, eCentric and contributors
"""18/11/2026: resync form 27 /approvals/contract-review + /approvals/payment-request sau QC 18/11:
- tach nguoi lam / nguoi kiem: an nut "Xac nhan da ky du" / "Xac nhan BBNT" / "Xac nhan tai khoan moi"
  voi chinh nguoi lap / nguoi tai ban ky / nguoi doi STK (server da chan tu truoc) - hien "nho Ke toan khac";
- ban nhap: nut "Xoa ban nhap" + hop thoai noi ro xoa vinh vien (truoc ghi "Huy yeu cau ... ket thuc luong
  phe duyet" va bat nhap ly do roi bo di).
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai).
"""
import frappe

_PAGES = (
    ("ecentric_workspace.approval_center.features.contract_review.infrastructure.page_sync",
     "approvals/contract-review", ("can_verify_sign", "doDeleteDraft", "can_confirm_payee")),
    ("ecentric_workspace.approval_center.features.payment_request.infrastructure.page_sync",
     None, ("doDeleteDraft", "legacyKolHTML")),
)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    for module, route, marks in _PAGES:
        try:
            mod = frappe.get_module(module)
            res = mod.sync() or {}
            route = route or getattr(mod, "ROUTE", None)
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            thieu = [m for m in marks if m not in html]
            frappe.logger("approval_center").info("p419 resync %s: %s (thieu moc: %s)"
                                                  % (route, res.get("action"), thieu or "khong"))
            if res.get("action") == "refused" or thieu:
                frappe.log_error(title="p419 resync %s" % route, message="action=%r thieu=%r" % (res.get("action"), thieu))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p419 resync %s" % (route or module))
