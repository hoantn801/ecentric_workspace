# Copyright (c) 2026, eCentric and contributors
"""Ghi de 3 endpoint cua Frappe tra `docinfo` ve form: goi BAN GOC y nguyen, roi loc Version.

Dang ky o hooks.py `override_whitelisted_methods`. Chu ky (ten + kieu tham so, methods) giu
DUNG nhu frappe v16 - form Desk goi theo ten, lech mot tham so la moi form deu gay.
    getdoc       mo form
    get_docinfo  tai lai timeline (sau comment, gan viec...)
    savedocs     luu form - Frappe dung lai docinfo NOI BO (save.send_updated_docs), khong
                 qua get_docinfo cong khai, nen phai ghi de ca cho nay.
Khong ghi de `cancel` / `discard`: Employee khong submit duoc; neu sau nay can cho DocType
submit duoc thi them theo cung mau.
"""
import frappe
from frappe.desk.form import load as _load
from frappe.desk.form import save as _save
from frappe.model.document import Document

from ecentric_workspace.hr.privacy.version_scrub import scrub_response_versions


@frappe.whitelist()
def getdoc(doctype: str, name: str | int):
    _load.getdoc(doctype, name)
    scrub_response_versions()


@frappe.whitelist()
def get_docinfo(doc: Document | dict | str | None = None, doctype: str | None = None,
                name: str | int | None = None):
    _load.get_docinfo(doc=doc, doctype=doctype, name=name)
    scrub_response_versions()


@frappe.whitelist(methods=["POST", "PUT"])
def savedocs(doc: str, action: str):
    _save.savedocs(doc, action)
    scrub_response_versions()
