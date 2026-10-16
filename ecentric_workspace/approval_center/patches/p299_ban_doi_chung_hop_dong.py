# Copyright (c) 2026, eCentric and contributors
"""Ban doi chung hop dong (16/10/2026, Finance bao, PO Hoan duyet phuong an A).

Moi quyet dinh tren Contract Review (Duyet / Tu choi / Yeu cau bo sung / hoan tat) tu chup tep
Office tren SharePoint thanh ban ghi bat bien `EC SharePoint Snapshot` (.docx goc + PDF). Thiet
ke: docstring dau `shared/integrations/sharepoint_snapshot.py`.

DocType moi do migrate tu tao tu JSON; patch nay CHI resync trang Contract Review (the
"Bản đối chứng" trong man hinh chi tiet). KHONG chup bu cho cac quyet dinh cu: ban tren
SharePoint bay gio KHONG con la trang thai luc ho bam nut - chup bu roi gan nhan "sau duyet cap
2" la tao ra mot bang chung sai.

KHONG BAO GIO nem loi: exception trong migrate lam chet ca lan deploy (p116).
"""
import frappe

_LANDMARK = "function renderDoiChung("


def execute():
    try:
        from ecentric_workspace.approval_center.features.contract_review.infrastructure import page_sync
        res = page_sync.sync() or {}
        if res.get("action") == "refused":
            frappe.log_error("p299: upsert TU CHOI GHI (khoa chong troi) live_sha=%s" % res.get("live_sha"),
                             "p299 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        if _LANDMARK not in html:
            frappe.log_error("p299: trang Contract Review thieu landmark %s" % _LANDMARK,
                             "p299 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p299 resync contract review")
