# Copyright (c) 2026, eCentric and contributors
"""doc_events cua Quality Procedure (hooks.py) - chi la keo dan frappe <-> service."""
import frappe

from ecentric_workspace.iso_docs import service
from ecentric_workspace.iso_docs.errors import DocError


def validate(doc, method=None):
    try:
        service.on_validate(doc)
    except DocError as e:
        frappe.throw(str(e).replace("\n", "<br>"), title="Tài liệu ISO")


def on_update(doc, method=None):
    service.on_update(doc)
