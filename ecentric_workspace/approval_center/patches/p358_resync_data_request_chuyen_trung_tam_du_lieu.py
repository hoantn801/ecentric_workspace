# Copyright (c) 2026, eCentric and contributors
"""p358: trang /approvals/data-request - "Data Request đã chuyển sang Trung tâm Dữ liệu" (09/11/2026).

Trung tam Du lieu dot 3 (data_hub p003) chuyen moi phieu EC Data Request sang /du-lieu va tro the
"Data Request" cua catalog sang /du-lieu. Trang cu (Web Page approval-center-data-request) doi theo:
  * bang tinh ngay dau trang: da chuyen, link /du-lieu (nam trong markup - khong che roi hien);
  * tab "Tạo yêu cầu" -> the "Gửi Data Request mới tại Trung tâm Dữ liệu" (form cu chi con dung cho
    phieu cho bo sung thong tin); server cung tu choi gui phieu moi (service.submit / moved_route);
  * chi tiet phieu cu (?id=EC-DATA-...) -> "Xem trên Trung tâm Dữ liệu" (/du-lieu?ma=<ma cu>, trang moi
    tu tim ticket theo legacy_ref).
So patch: max cua day approval_center trong patches.txt (p348) + 10 de khong dung so voi nhanh khac.
Chi RESYNC trang (khong doi du lieu). Lech khoa / loi -> ghi log, KHONG BAO GIO nem.
"""
import frappe

MOC = "dreq-moved"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    try:
        from ecentric_workspace.approval_center.features.data_request.infrastructure import page_sync
        res = page_sync.sync() or {}
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        ok = res.get("action") != "refused" and MOC in html
        frappe.logger("approval_center").info("p358 data_request resync: %s (moc %s)" % (
            res.get("action"), "co" if MOC in html else "THIEU"))
        if not ok:
            frappe.log_error(title="p358 resync data_request", message=repr(res))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p358 resync data_request")
