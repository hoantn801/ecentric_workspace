# Copyright (c) 2026, eCentric and contributors
"""p290: can giua khung noi dung tren man rong (PO chup 10/10/2026).

8 trang dat max-width cho khung noi dung nhung khong co margin auto -> man rong (1920px) noi dung
dinh trai, bo trong mot dai ben phai: /ai-video, /ai-usage, /reports, 5 trang /alerts*.
Sua NGUON (A65): them `margin-inline:auto` (+ width:100% cho 2 trang AI). Patch nay chi ghi lai
nguon len site. Moi trang mot try: trang loi khong chan trang khac; khong bao gio raise.
Ket qua: Error Log "p290 canh giua noi dung".
"""
import frappe

TITLE = "p290 canh giua noi dung"


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    out = {}
    from ecentric_workspace.ai_tools.pages.ai_video import page_sync as ai_video
    from ecentric_workspace.ai_tools.pages.ai_usage import page_sync as ai_usage
    from ecentric_workspace.reporting.reports_hub import page_sync as reports
    from ecentric_workspace.alerts.site_pages import sync as alerts
    for name, fn in (("ai-video", ai_video.sync), ("ai-usage", ai_usage.sync), ("reports", reports.sync)):
        try:
            out[name] = (fn() or {}).get("action")
        except Exception:
            frappe.log_error(title=TITLE + " FAILED " + name, message=frappe.get_traceback())
    try:
        out["alerts"] = [(r or {}).get("action") for r in (alerts.sync_all() or [])]
    except Exception:
        frappe.log_error(title=TITLE + " FAILED alerts", message=frappe.get_traceback())
    frappe.log_error(title=TITLE, message=repr(out))
