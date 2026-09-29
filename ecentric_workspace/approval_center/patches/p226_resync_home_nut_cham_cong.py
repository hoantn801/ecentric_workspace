# Copyright (c) 2026, eCentric and contributors
"""Trang chu: nut cham cong khong xuong 2 dong o man 14 inch (NHIEU_LOP GD2, 29/09/2026).

Do tren live ngay sau p224 (29/09 10:20, man 1266 x 620 va 1366 x 650): khi da cham cong,
nut doi nhan thanh "Da cham cong hom nay" - rong 147,23 px, trong khi nac hep cho nut toi
thieu 147 px va o cham cong chi con dung 228 px. Nut bi bop 0,2 px nen chu xuong 2 dong,
dai navy cao them 17 px SAU khi du lieu ve -> loi chao, 4 o so, dong thoi gian, luoi cung
tut xuong. Sua trong nguon trang: nut `white-space:nowrap`, o cham cong nac 2 rong 262 px
(du cho nhan dai nhat + 5 px).

Chi goi legacy_pages.home.page_sync.sync() (khoa chong troi: live phai dang la ban p224
0a77f921 hoac ban goc 2a4c6826; render thu Jinja truoc khi ghi). Tu bat loi, khong chan deploy.
Idempotent: chay lai -> "unchanged".
"""
import frappe

_EXPECT = (
    "min-width:194px;white-space:nowrap;",       # nut khong xuong dong
    ".ec2-band .checkin-card{width:262px}",       # o cham cong nac 2 du cho
)


def execute():
    from ecentric_workspace.legacy_pages.home import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p226 home sync=%s" % action, "p226 trang chu nut cham cong")
        if action == "refused":
            frappe.log_error(
                "p226: upsert TU CHOI GHI (khoa chong troi). Live khong phai ban p224/goc - trang "
                "chu KHONG duoc cap nhat. Doi chieu live_sha: %s" % (res,), "p226 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p226: thieu landmark=%s" % (missing,), "p226 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p226 home sync failed")
