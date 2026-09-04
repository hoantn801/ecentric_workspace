# Copyright (c) 2026, eCentric and contributors
"""p141 chot "ky dung phieu dang mo" so business_name (EC-PAYR-...) voi reqName cua hub - ma
reqName la MA PHE DUYET (EC-APR-...). Chot luon truot: chi Lien bam "Duyet & Ky" thay "Khong xac
dinh duoc phieu de ky" (04/09 15:50). Sua: so approval.name. Patch moi vi p141 da chay.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARK = "ap.name!==reqName"


def execute():
    res = page_sync.sync()
    frappe.log_error("p142 all_requests sync=%s" % (res or {}).get("action"), "p142 resync")
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    if _LANDMARK not in html:
        raise Exception("p142: hub van so nham ma phieu sau sync (action=%s)" % (res or {}).get("action"))
