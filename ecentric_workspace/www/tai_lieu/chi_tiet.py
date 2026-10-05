# Copyright (c) 2026, eCentric and contributors
"""/tai-lieu/<ma> - mot tai lieu: ban hieu luc, so do theo vai tro, bieu mau, lich su phien ban.

?ban=<X.Y> xem mot phien ban cu (giu lai, co nhan "het hieu luc"). Ma khong co va tai lieu nguoi
nay khong duoc doc tra CUNG mot loi - khong cho do ma nao ton tai.
"""
import json

import frappe

from ecentric_workspace.iso_docs import library, pages
from ecentric_workspace.iso_docs.errors import NotFound

no_cache = 1
sitemap = 0


def get_context(context):
    code = pages.arg("code").strip().upper()
    pages.require_login("%s/%s" % (pages.ROUTE, code))
    try:
        d = library.doc_page(frappe.session.user, code, version=pages.arg("ban").strip())
    except (NotFound, frappe.PermissionError):
        frappe.clear_last_message()
        raise frappe.PageDoesNotExistError("Không tìm thấy tài liệu này.")
    context.d = d
    context.roles_json = json.dumps(d["flow"]["roles"], ensure_ascii=False)
    context.mermaid_js = pages.MERMAID_JS
    context.title = "%s %s" % (d["code"], d["name"])
    pages.shell(context, detail=d["code"])
    return context
