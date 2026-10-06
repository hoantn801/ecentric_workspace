# Copyright (c) 2026, eCentric and contributors
"""Dua /pm ve vo shell chung de co thanh khu vuc navy (menu 2 tang, PO chup 07/10/2026).

VI SAO. /pm (Web Page "project-management") van la ban pm_app.html GOC: sidebar rieng cua
PM, khong co `.ec-shell-mount` -> bam "Cong viec" tren thanh navy thi mat thanh, ra menu PM
cu. Bien doi sang vo shell da co san tu 07/2026 (`pm/pages.transform`, `sync_pm_page`;
audit 23/07 ghi PASS tren live) nhung lan deploy PM sau ghi lai ban goc va khong chay lai
sync (NHIEU_LOP/00_KIEM_KE_TUNG_TRANG.md: "co trong repo, chua co tren live").

CACH LAM. Goi DUNG `pm.pages.transform` (idempotent: trang da o vo shell -> khong doi, trang
dang o trang thai lai -> sua). Khong viet transform moi, khong sua pm_app.html. Ghi ca
main_section lan main_section_html nhu sync_pm_page.

An toan: loi bat ky -> Error Log, khong nem (exception trong migrate lam chet ca lan deploy).
Ket qua doc trong Error Log, tieu de "p272 pm vo shell".
[TEMP-WORKAROUND] (A65): transform cu chen `<style id="ec-pm-shell-grid">` vao trang live. Han go:
khi chat PM dua ban vo shell vao THANG pm_app.html (nguon) - 03_BUGS ghi muc nay.
LUU Y cho chat PM: moi lan day pm_app.html goc len site phai chay lai sync_pm_page.
"""
import frappe

TITLE = "p272 pm vo shell"


def execute():
    try:
        from ecentric_workspace.pm import pages as P
        if not frappe.db.exists("Web Page", P.NAME):
            frappe.log_error(title=TITLE, message="skip: Web Page %s khong ton tai" % P.NAME)
            return
        ms = frappe.db.get_value("Web Page", P.NAME, "main_section") or ""
        new = P.transform(ms)
        if new == ms:
            frappe.log_error(title=TITLE, message="unchanged (da o vo shell)")
            return
        doc = frappe.get_doc("Web Page", P.NAME)
        doc.main_section = new
        doc.main_section_html = new
        doc.save(ignore_permissions=True)
        frappe.log_error(title=TITLE, message="updated len %d -> %d, mount=%d"
                         % (len(ms), len(new), new.count('data-ec-shell="1"')))
    except Exception:
        frappe.log_error(title=TITLE + " FAILED", message=frappe.get_traceback())
