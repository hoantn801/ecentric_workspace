# Copyright (c) 2026, eCentric and contributors
"""Trang chu (Web Page `ecentric-workspace`, route `home`, phuc vu o "/").

NGUON TRANG NAM TRONG REPO tu 29/09/2026 (NHIEU_LOP giai doan 2): `main_section.html`
canh file nay la bo cuc v2 PO da duyet 24/08 (dai navy + dong thoi gian + hang doi),
viet thang thanh markup + CSS. Truoc do live giu bo cuc CU cong mot khoi JS `ec-home-v2`
(deploy_home_v2.ps1) dung lai DOM sau khi tai, nen nguoi dung thay trang cu nhay sang
trang moi roi co chu co lai (NHIEU_LOP/00_KIEM_KE_TUNG_TRANG.md).

Lich su ngan, de khong ai phai doan lai:
  * 21/07: Daily Cockpit bi PO tu choi, live duoc khoi phuc tay; module nay tu khoa
    0-ghi (BASELINE_SHA256 = None) cho toi khi co baseline duoc duyet.
  * 22-24/07: `transform_home` (vo shell + khoi polish) va `neutralize_legacy_action_counts`
    (bo dem toan cuc) chay TREN LIVE, co chung minh byte. Ket qua cua ca hai nam trong ban
    live 29/09 nen nam san trong nguon; hai ham do da go khoi duong ghi.
  * 24/08: bo cuc v2 (JS) PO duyet va ap len "/".
  * 29/09: baseline nay = bo cuc v2 thanh nguon (NHIEU_LOP giai doan 2, PO duyet).

KHOA CHONG TROI: sync() chi ghi khi main_section_html dang song bam ra BASELINE_SHA256
hoac mot gia tri trong SUPERSEDES_SHA256. Ai do sua trang tren Desk -> sync TU CHOI,
trang giu nguyen, patch ghi Error Log. Sua co chu dich = sua main_section.html, bump
BASELINE_SHA256, day gia tri cu xuong SUPERSEDES_SHA256, them patch resync va cap nhat
resync_manifest.json - cung mot commit (CLAUDE.md A65).

Trang dung Jinja (dynamic_template = 1, render theo tung nguoi) nen KHONG phuc vu tinh
(legacy_pages.serving), va Website Settings khong bao gio bi dung toi.
"""
import hashlib
import io
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "home"
NAME = "ecentric-workspace"
TITLE = "eCentric Workspace"

#: sha256 cua main_section.html commit nay ship (phep kiem `pagesync` cua CI doi chieu).
BASELINE_SHA256 = "0a77f921665a2a619232041647cfaa3158216cf070fa6905b1a03020a81fdb5d"
SUPERSEDES_SHA256 = (
    # 29/09/2026: live truoc giai doan 2 = bo cuc cu + khoi JS ec-home-v2 (deploy_home_v2.ps1,
    # ban 28/09 d40b72c) + vo shell/polish cua transform_home. Doi chieu bang trinh duyet.
    "2a4c6826a8f091a203a960e44be652dea97486f5ad75fef09188294e5c9bcf76",
)

#: Dau vet cua Daily Cockpit (PO tu choi 21/07): nguon trang chu khong bao gio duoc chua lai.
COCKPIT_MARKERS = ('class="ec-ck', "ec-cockpit-js", "ec-ck-grid", "data-ec-shell-quickaccess")


def _path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "main_section.html")


def _html():
    with io.open(_path(), encoding="utf-8") as fh:
        return fh.read()


def check_source(html):
    """File trong repo phai dung la ban da khoa. Sai -> ValueError (loi cua repo, khong phai site)."""
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    if digest != BASELINE_SHA256:
        raise ValueError("main_section.html bam ra %s nhung BASELINE_SHA256 = %s: sua file "
                         "ma chua bump hang so" % (digest[:12], BASELINE_SHA256[:12]))
    for mk in COCKPIT_MARKERS:
        if mk in html:
            raise ValueError("nguon trang chu chua dau vet Daily Cockpit (%s) - tu choi" % mk)


def render_check(html):
    """Render thu Jinja TRUOC khi ghi, bang nguoi dung cua tien trinh (Administrator trong
    migrate). Mot loi Jinja tren trang chu la trang 500 cho ca cong ty - biet truoc thi
    KHONG ghi, thay vi ghi roi moi biet."""
    frappe.render_template(html, {})


def sync(force=0):
    html = _html()
    check_source(html)
    render_check(html)
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    name = res.get("name")
    if res.get("action") in ("created", "updated", "unchanged") and name \
            and frappe.db.exists("Web Page", name):
        # Jinja can dynamic_template = 1: render theo tung nguoi, khong vao cache chung.
        if not frappe.db.get_value("Web Page", name, "dynamic_template"):
            frappe.db.set_value("Web Page", name, "dynamic_template", 1)
            res["dynamic_template"] = "set"
        page_sync_util.record_live_sha(ROUTE, name)
    return res


@frappe.whitelist(methods=["POST"])
def sync_home_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the homepage."), frappe.PermissionError)
    return sync()
