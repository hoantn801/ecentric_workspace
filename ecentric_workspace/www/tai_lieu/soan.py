# Copyright (c) 2026, eCentric and contributors
"""/tai-lieu/soan - soan tai lieu moi (Ban ISO) / sua ban nhap (?ma=) ngay tren ERP, khong qua
man quan tri (PO Hoan 05/10/2026). Luu qua iso_docs.api.save_draft, gui duyet qua api.action."""
import json

import frappe

from ecentric_workspace.iso_docs import manage, pages
from ecentric_workspace.iso_docs.errors import Forbidden, NotFound

no_cache = 1
sitemap = 0


def get_context(context):
    code = pages.arg("ma").strip().upper()
    pages.require_login(pages.ROUTE + "/soan" + (("?ma=" + code) if code else ""))
    try:
        ctx = manage.editor_page(frappe.session.user, code)
    except (NotFound, frappe.PermissionError):
        frappe.clear_last_message()
        raise frappe.PageDoesNotExistError("Không tìm thấy tài liệu này.")
    except Forbidden as e:
        raise frappe.PermissionError(str(e))
    context.update(ctx)
    context.boot_json = json.dumps({"code": ctx["code"], "mode": ctx["mode"], "rows": ctx["rows"],
                                    "forms": ctx["forms"]}, ensure_ascii=False)
    context.title = "Soạn tài liệu" if ctx["mode"] == "new" else "Soạn %s" % ctx["code"]
    pages.shell(context, route=pages.ROUTE + "/quan-ly", detail="Soạn tài liệu")
    return context
