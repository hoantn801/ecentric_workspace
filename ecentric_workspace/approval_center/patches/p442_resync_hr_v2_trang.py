# Copyright (c) 2026, eCentric and contributors
"""23/11/2026 (HR v2 - Dot 1): resync /approvals/resignation, /approvals/offer-request,
/approvals/new-staff-preparation:
- Nghi viec: bo nut "Tu choi", nut "Rut don", ngay nghi som nhat hop le (Dieu 35), bo phan danh gia kieu
  khao sat khoi form (don cu: chi HR xem), buoc Clearance tren tien trinh;
- Offer: o "Luong offer" dang so (so voi muc Hiring -> HOF co dieu kien), nut "Ung vien tu choi" / "Huy offer";
- New Staff Preparation: nhom HR chon ho so Employee -> ghi dong Thu viec/Thuc tap vao hop dong.
Chi RESYNC trang. Lech / loi -> Error Log, KHONG nem (patch nem = migrate dung lai)."""
import frappe

_F = "ecentric_workspace.approval_center.features."
_PAGES = (
    (_F + "resignation.infrastructure.page_sync", ("doWithdraw", "resn-notice")),
    (_F + "offer_request.infrastructure.page_sync", ("offered_salary", "doMarkCandidate")),
    (_F + "new_staff_preparation.infrastructure.page_sync", ("doPickEmployee",)),
)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    for module, marks in _PAGES:
        route = None
        try:
            mod = frappe.get_module(module)
            res = mod.sync() or {}
            route = getattr(mod, "ROUTE", None)
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            thieu = [m for m in marks if m not in html]
            frappe.logger("approval_center").info("p442 resync %s: %s (thieu moc: %s)"
                                                  % (route, res.get("action"), thieu or "khong"))
            if res.get("action") == "refused" or thieu:
                frappe.log_error(title="p442 resync %s" % route,
                                 message="action=%r thieu=%r" % (res.get("action"), thieu))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p442 resync %s" % (route or module))
