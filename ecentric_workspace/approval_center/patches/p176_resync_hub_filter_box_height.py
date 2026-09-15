# Copyright (c) 2026, eCentric and contributors
"""Hub: bon o loc combobox cao hon the trang - sua luat CSS nham dich cua p173 (10/09, Hoan).

p173 ep chieu cao o nhap ve 28px bang:
    #ec-apl-root .fgrid .ec-cb > *:first-child{ height:28px; ... }
Nhung CON DAU TIEN cua `.ec-cb` la the <select> AN (display:none, cao 0) - `ec_formkit` chen
nut sau no. Nen luat khong trung dich gi ca.

DO TREN PRODUCTION 10/09 (khong suy doan):
    con cua .ec-cb: 0 SELECT h=0 display:none | 1 BUTTON.ec-cb-display h=38.9 | 2 arrow | 3 panel
    wrap .ec-cb = 28px, nut = 38.9px, wrap overflow:visible -> nut tran 11px xuong duoi the .filters
Ba o ngay khong dinh vi chung dung `.ec-dp-field` - trung dich tu dau.

Sua: nham thang `.ec-cb-display`, va giam padding cho vua 28px (nguyen ban 9px tren/duoi).
Mui ten va panel bam theo WRAP chu khong theo nut (arrow lech 6.5px = giua cua 28px; panel
`top:calc(100% + 4px)`), nen khong phai chinh gi them - da do.

Van KHONG sua bundle dung chung: luat gioi han trong `#ec-apl-root .fgrid`.
"""
import frappe

from ecentric_workspace.approval_center.ui.all_requests import page_sync

_LANDMARKS = (".fgrid .ec-cb .ec-cb-display",)
_FORBID = (".ec-cb > *:first-child",)


def execute():
    res = page_sync.sync()
    action = (res or {}).get("action")
    frappe.log_error("p176 all_requests sync=%s" % action, "p176 resync")
    if action == "refused":
        frappe.log_error("p176: upsert TU CHOI GHI - trang KHONG duoc cap nhat.", "p176 REFUSED")
        return
    html = frappe.db.get_value("Web Page", {"route": "approvals/all-requests"},
                               "main_section_html") or ""
    thieu = [m for m in _LANDMARKS if m not in html]
    con = [m for m in _FORBID if m in html]
    if thieu or con:
        frappe.log_error("p176: thieu=%s con_ban_cu=%s" % (thieu, con), "p176 KHONG toi noi")
