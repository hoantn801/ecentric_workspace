# Copyright (c) 2026, eCentric and contributors
"""Gieo `sp_uploaded_at` cho cac ban ghi lien ket da co (15/09).

Truong nay moi them. Ban ghi cu khong co moc nen, ma luat canh bao doc "khong co moc nen thi
canh bao nhu cu" - tuc 5 bang canh bao dang bao NHAM se con bao nham tiep sau khi deploy.

Gieo bang chinh `sp_last_modified` hien tai: voi ban ghi cu, moc sua tren SharePoint dung la
cua lan HE THONG tai len (chua co gi doc lai moc tu SharePoint truoc dot nay, va con nguoi
chua he sua tep nao qua Word Online). Nen lay no lam moc nen la dung ban chat, khong phai mot
phep lam trong cho qua chuyen.

Tu sau patch nay, canh bao chi noi khi tep doi SAU moc nen - tuc do NGUOI sua.

KHONG BAO GIO nem loi: patch chay trong migrate (p116). Idempotent: chi gieo o dong con trong.
"""
import frappe

LINK_DT = "EC SharePoint File Link"


def execute():
    try:
        if not frappe.db.exists("DocType", LINK_DT):
            return
        rows = frappe.get_all(LINK_DT, filters={"sp_uploaded_at": ["is", "not set"],
                                                "sp_last_modified": ["is", "set"]},
                              fields=["name", "sp_last_modified"], limit_page_length=0)
        for r in rows:
            frappe.db.set_value(LINK_DT, r.name, "sp_uploaded_at", r.sp_last_modified,
                                update_modified=False)
        frappe.log_error("da gieo moc nen cho %d ban ghi" % len(rows), "p199 sp_uploaded_at")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p199 sp_uploaded_at THAT BAI")
