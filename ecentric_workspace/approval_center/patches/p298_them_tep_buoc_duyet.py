# Copyright (c) 2026, eCentric and contributors
"""p298_them_tep_buoc_duyet: nut "Them tep" o buoc duyet (16/10/2026, Hoan).

Nguoi DANG giu phieu (duyet Pending o cap hien tai / chu viec o buoc xu ly) them tep vao phieu,
chi them khong xoa, ghi lich su "Attachment Added". Nut di qua asset chung (ec_addfile.bundle.js
gan vao EcRemind.buttonHTML) nen 30 trang form KHONG doi. Hai trang doi HTML -> resync:
  * /approvals/all-requests: nut trong popup + ve lai popup khi them xong;
  * /approvals/booking-request: trang nho chi tiet theo ma phieu, phai bo nho khi them xong.

Landmark = dieu PHAI CO tren ban song sau khi sync (kiem bang cach doc main_section_html, xem F11
trong 03_BUGS_AND_NEXT_STEPS.md). Log, KHONG BAO GIO nem: mot trang sync hong khong duoc lam gay
ca lan migrate.
"""
import frappe

MOC = "ec-addfile:done"
_TRANG = (
    ("ecentric_workspace.approval_center.ui.all_requests.page_sync", "approvals/all-requests"),
    ("ecentric_workspace.approval_center.features.booking_request.infrastructure.page_sync",
     "approvals/booking-request"),
)


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    ket = []
    for mod_path, route in _TRANG:
        try:
            res = frappe.get_module(mod_path).sync() or {}
            html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
            ket.append("%s: %s, dau moc %s" % (route, res.get("action"),
                                               "CO" if MOC in html else "THIEU"))
        except Exception:
            frappe.log_error(frappe.get_traceback(), "p298_them_tep_buoc_duyet %s" % route)
            ket.append("%s: LOI" % route)
    frappe.logger("approval_center").info("p298_them_tep_buoc_duyet: " + "; ".join(ket))
