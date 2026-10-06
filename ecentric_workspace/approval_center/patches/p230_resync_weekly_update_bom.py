# Copyright (c) 2026, eCentric and contributors
"""/weekly-update: chay lai sync sau khi sua baseline nhiem BOM - 06/10/2026.

VI SAO CO PATCH NAY THAY VI SUA p229

p229 da chay luc 06/10 14:25 va BI KHOA CHONG TROI TU CHOI: live khong khop
BASELINE_SHA256. Khong ai sua trang ca -- baseline sai. No duoc tinh tren mot
file chup co BOM o dau, ma BOM do chinh script chup chen vao
(`WriteAllText(..., [Text.Encoding]::UTF8)` cua .NET tu ghi preamble EF BB BF).
Live khong co BOM, nen khong bao gio khop.

Frappe chay moi patch DUNG MOT LAN moi site (Patch Log). Sua baseline roi
deploy lai thi p229 KHONG chay nua -- ban sua se nam im trong code mai mai.
Nen can patch moi.

Cung luc da bo BOM khoi nguon trong repo: neu khoa khong chan o p229, sync da
day mot ky tu BOM len dau trang live.

Noi dung sua trang van giu nguyen nhu p229 mo ta: nut Submit `type="button"`
va go hai rang buoc cua the he 1. Xem p229 de biet vi sao.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

_EXPECT = ('id="wu-btn-submit"', 'type="button" class="wu-btn-primary"')


def execute():
    from ecentric_workspace.weekly_report.pages.weekly_update import page_sync as wu

    try:
        res = wu.sync()
        action = (res or {}).get("action")
        frappe.log_error("p230 weekly-update sync=%s" % action, "p230 weekly-update")
        if action == "refused":
            frappe.log_error(
                "p230 weekly-update: VAN BI TU CHOI sau khi sua baseline nhiem BOM."
                " Lan nay co the co nguoi sua that tren Desk. live_sha=%s expect=%s."
                " Chup lai live (ghi KHONG BOM), doi chieu tung dong, roi moi cap nhat."
                % ((res or {}).get("live_sha"), (res or {}).get("expect_sha")),
                "p230 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "weekly-update"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p230 weekly-update: thieu landmark=%s" % missing,
                             "p230 KHONG toi noi")
        if html.startswith(u"﻿"):
            # Canh lan nua: BOM la chinh cai da gay ra p229 bi tu choi.
            frappe.log_error("p230 weekly-update: trang live bat dau bang BOM",
                             "p230 BOM tren live")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p230 weekly-update failed")
