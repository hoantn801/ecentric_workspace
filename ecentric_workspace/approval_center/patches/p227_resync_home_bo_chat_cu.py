# Copyright (c) 2026, eCentric and contributors
"""Trang chu: go nut chat cu "AI Tro ly" (#ec-chat-fab) - PO yeu cau 29/09/2026.

Nut chat cu (khung chat Gemini tu thoi 05/2026) nam trong nguon trang chu, trong nhanh
{% else %} cua panel Chinh sach. Tu 28/09 eC Mate (ec_khay) an no voi nguoi co eC Mate, nhung
nut van ve o lan dau roi moi bi an (N8), va chiem 12 KB HTML + 1 khoi style + 1 khoi script.
PO chot 29/09: go han cho gon. Nguoi CHUA co eC Mate (thieu role EC Khay Pilot) se khong con
khung chat tren trang chu nua.

Chi goi legacy_pages.home.page_sync.sync() (khoa chong troi: live phai dang la ban p226
52d1d244, p224 hoac ban goc; render thu Jinja truoc khi ghi). Tu bat loi, khong chan deploy.
"""
import frappe

_GONE = ('id="ec-chat-fab"', 'id="ec-chatbot-js"', 'id="ec-chatbot-style"')


def execute():
    from ecentric_workspace.legacy_pages.home import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p227 home sync=%s" % action, "p227 trang chu go chat cu")
        if action == "refused":
            frappe.log_error("p227: upsert TU CHOI GHI (khoa chong troi): %s" % (res,), "p227 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        left = [m for m in _GONE if m in html]
        if left:
            frappe.log_error("p227: van con %s" % (left,), "p227 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p227 home sync failed")
