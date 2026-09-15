# Copyright (c) 2026, eCentric and contributors
"""Resync 6 legacy page sau khi bo fallback CSRF gui chuoi literal "token".

14/09/2026: wrapper fetch tren 23 Web Page ket thuc chuoi fallback bang chuoi
literal "token". Khi chua co token that no gui chuoi rac do di, server tra
CSRFTokenError -> moi POST cua trang hong am tham (dropdown GBS rong, bam nut
khong an). Goc sau xa: nang cap python3.14 go frappe.generate_hash khoi sandbox
khien get_csrf tung tra token RONG (da chua o app method 14/09).

Ban va da ghi THANG len live 23 trang cung ngay. Patch nay dua 6 trang co nguon
trong repo ve khop live."""

import frappe


def execute():
    from ecentric_workspace.legacy_pages.approval_page import page_sync as approval_page
    from ecentric_workspace.legacy_pages.all_ticket import page_sync as all_ticket
    from ecentric_workspace.legacy_pages.gbs_so_form_v2 import page_sync as gbs_so
    from ecentric_workspace.legacy_pages.gbs_po_form_v2 import page_sync as gbs_po
    from ecentric_workspace.legacy_pages.mso_plan_form import page_sync as mso_plan
    from ecentric_workspace.legacy_pages.docs_architecture import page_sync as docs_arch

    for mod in (approval_page, all_ticket, gbs_so, gbs_po, mso_plan, docs_arch):
        try:
            res = mod.sync()
            frappe.logger().info("p185 resync %s -> %s" % (mod.__name__, res))
        except Exception:
            frappe.log_error(
                title="p185 resync FAIL %s" % mod.__name__,
                message=frappe.get_traceback(),
            )