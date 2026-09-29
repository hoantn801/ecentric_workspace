# Copyright (c) 2026, eCentric and contributors
"""Trang chu: bo cuc v2 thanh NGUON trang - het "nhay trang cu" (NHIEU_LOP giai doan 2, 29/09/2026).

Truoc: Web Page `ecentric-workspace` giu HTML bo cuc CU (greeting / stats-strip / bento) cong
khoi <script id="ec-home-v2"> 46 KB (deploy_home_v2.ps1). Trinh duyet ve bo cuc cu truoc,
toi DOMContentLoaded JS moi dung lai DOM thanh bo cuc v2, chen CSS vao cuoi <body>, roi
do trang de gan lop gon (ec2-fit1/fit2, ec2-bw1/bw2) - nguoi dung thay trang cu nhay sang
trang moi roi co chu co lai.

Sau: legacy_pages/home/main_section.html LA bo cuc v2 (markup + CSS, cac nac gon la @container
/ @media). JS con lai (ec_home_v2.bundle.js) chi do du lieu. Chi tiet va so do truoc/sau:
NHIEU_LOP/00_KIEM_KE_TUNG_TRANG.md.

Patch lam hai viec, doc lap, moi viec tu bat loi (patch nem loi = CHAN ca dot deploy, bai hoc
p116):
  1. legacy_pages.home.page_sync.sync(): ghi nguon len trang - CHI KHI live dang dung ban
     2a4c6826 (khoa chong troi) - sau khi render thu Jinja thanh cong.
  2. /home-v2 (ban UAT do deploy_home_v2.ps1 JOB 1 tao 24/08) -> published = 0. Giu ban ghi.

Idempotent: chay lai tren site da co ban nay -> sync "unchanged", /home-v2 da an thi bo qua.
"""
import frappe

_EXPECT = (
    'data-ec2-home="1"',                        # bo cuc v2 nam san trong markup
    "container:ec2band/inline-size",            # nac gon theo be ngang la CSS
    "bundled_asset('ec_home_v2.bundle.js')",    # JS chi do du lieu
)


def execute():
    _sync_home()
    _retire_home_v2()


def _sync_home():
    from ecentric_workspace.legacy_pages.home import page_sync
    try:
        res = page_sync.sync()
        action = (res or {}).get("action")
        frappe.log_error("p224 home sync=%s" % action, "p224 trang chu v2 nguon")
        if action == "refused":
            frappe.log_error(
                "p224: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot ban khong nam "
                "trong BASELINE/SUPERSEDES - trang chu KHONG duoc cap nhat, van la ban cu. "
                "Doi chieu live_sha trong ket qua: %s" % (res,), "p224 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": page_sync.ROUTE}, "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p224: thieu landmark=%s" % (missing,), "p224 KHONG toi noi")
    except Exception:
        # Gom ca loi render Jinja (render_check) va loi nguon (check_source): khong ghi gi.
        frappe.log_error(frappe.get_traceback(), "p224 home sync failed")


def _retire_home_v2():
    try:
        name = frappe.db.get_value("Web Page", {"route": "home-v2"}, "name")
        if not name or not frappe.db.get_value("Web Page", name, "published"):
            return
        doc = frappe.get_doc("Web Page", name)
        doc.published = 0
        doc.save(ignore_permissions=True)
        frappe.log_error("p224: /home-v2 (%s) -> published=0" % name, "p224 go /home-v2")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p224 go /home-v2 failed")
