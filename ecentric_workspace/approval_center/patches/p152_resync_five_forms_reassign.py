# Copyright (c) 2026, eCentric and contributors
"""Nut "Chuyen nguoi xu ly" + hoi lai khi quan tri nhan viec, tren 5 form co fulfillment
(07/09, Hoan): Asset Request, Data Request, Document Request, Resignation, System Request.

Vi sao: `is_eligible_fulfiller` cho System Manager di qua VO DIEU KIEN, nen nut "Nhan xu ly"
hien voi Hoan tren ca 6 form du anh khong thuoc nhom xu ly loai nao. 07/09 anh bam nham mot
ho so nghi viec cua HR va khong co duong nao tra lai - engine co san
`transitions.reassign_fulfillment` nhung chua bao gio duoc noi ra UI.

Chot voi Hoan: KHONG an nut cua quan tri (con can that khi nguoi xu ly mac dinh di vang),
chi hoi lai truoc khi nhan; va them nut chuyen viec de bam nham con go duoc.

AI Topup CHUA lam trong dot nay: khoi fulfillment cua no viet khac 5 form kia.
Patch moi vi cac patch resync truoc da chay tren production. Tu VERIFY landmark tung trang.
"""
import frappe

_PAGES = (
    ("asset_request", "approvals/asset-request"),
    ("data_request", "approvals/data-request"),
    ("document_request", "approvals/document-request"),
    ("resignation", "approvals/resignation"),
    ("system_request", "approvals/system-request"),
)
_LANDMARKS = ("function doReassign(name)", 'data-act="reassign"', "claim_is_admin_override")


def execute():
    missing_all = []
    for feature, route in _PAGES:
        mod = frappe.get_module(
            "ecentric_workspace.approval_center.features.%s.infrastructure.page_sync" % feature)
        res = mod.sync()
        frappe.log_error("p152 %s sync=%s" % (feature, (res or {}).get("action")), "p152 resync")
        html = frappe.db.get_value("Web Page", {"route": route}, "main_section_html") or ""
        missing = [m for m in _LANDMARKS if m not in html]
        if missing:
            missing_all.append("%s thieu %s (action=%s)"
                               % (route, missing, (res or {}).get("action")))
    if missing_all:
        raise Exception("p152: " + " | ".join(missing_all))
