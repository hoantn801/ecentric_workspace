# Copyright (c) 2026, eCentric and contributors
"""Trang /pm (Web Page `project-management`) -- NGUON NAM TRONG REPO (A65, 10/2026).

`pm_app.html` canh file nay la ban live PO da duyet (p272 dua /pm vao vo menu chung)
DUA VE NGUON: vo shell (aside.ec-shell-mount + topbar chuan) nam thang trong markup;
cau noi an #ec-pm-nav-bridge va khoi <style id="ec-pm-shell-grid"> cua p272 da go/gop
vao style nguon; SPA bam cac muc /pm#... cua menu chung (khong con #pm-nav noi bo).

Duong ghi cu `pm.pages.sync_pm_page` (transform tren live) NGUNG DUNG tu ban nay --
guard cua no tu tu choi trang moi (khong con #pm-nav), nen khong the ghi de nhau.

KHOA CHONG TROI (mau: legacy_pages/home/page_sync.py): sync() chi ghi khi ban song
bam ra BASELINE_SHA256, mot gia tri trong SUPERSEDES_SHA256, hoac sha da ghi o lan
sync truoc (default `ec_page_sync_sha:pm`). Ai sua trang tren Desk -> sync TU CHOI,
trang giu nguyen, patch ghi Error Log. Sua co chu dich = sua pm_app.html, bump
BASELINE_SHA256, day gia tri cu xuong SUPERSEDES_SHA256, them patch resync va cap
nhat resync_manifest.json -- cung mot commit (A56 / A65).
"""
import hashlib
import io
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "pm"
NAME = "project-management"
TITLE = "Project Management"

#: sha256 cua pm_app.html commit nay ship (cong QC `pagesync` doi chieu manifest).
BASELINE_SHA256 = "bf88bd3c56106b8e4e8409624a496222a4a2b605a9021ced4047de9707805fe2"
SUPERSEDES_SHA256 = (
    # 10/2026: ban live ngay truoc khi dua nguon = p272 transform tren trang cu.
    "df82855d0d0d9f0459229082b7a322f882e99898e40cf3b3f4f6770961d77ae6",
    "82c68f9918d917da7ff944ab60f1ee9177193a17b940216e92b6052405a6b759",
)

#: Dau vet p272 / rail cu: nguon moi KHONG bao gio duoc chua lai.
FORBIDDEN = ('class="ec-sidebar"', 'id="ec-pm-nav-bridge"',
             '<style id="ec-pm-shell-grid">', 'id="pm-nav"')
#: Moi marker phai xuat hien DUNG MOT lan trong nguon.
REQUIRED_ONCE = ('data-ec-shell="1"', 'data-ec-shell-crumbs="1"',
                 'data-ec-shell-header-right="1"', 'data-ec-shell-action-slot="1"',
                 'id="pm-search"', 'id="pm-crumb"', 'id="tb-new"', 'head==="new"')


def _path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "pm_app.html")


def _html():
    with io.open(_path(), encoding="utf-8", newline="") as fh:
        return fh.read()


def check_source(html):
    """File trong repo phai dung ban da khoa + dung hinh dang vo-shell-trong-nguon."""
    digest = hashlib.sha256(html.encode("utf-8")).hexdigest()
    if digest != BASELINE_SHA256:
        raise ValueError("pm_app.html bam ra %s nhung BASELINE_SHA256 = %s: sua file "
                         "ma chua bump hang so" % (digest[:12], BASELINE_SHA256[:12]))
    for mk in FORBIDDEN:
        if mk in html:
            raise ValueError("nguon /pm con dau vet rail cu / p272 (%s) - tu choi" % mk)
    for mk in REQUIRED_ONCE:
        if html.count(mk) != 1:
            raise ValueError("nguon /pm: marker %s xuat hien %d lan (phai dung 1)"
                             % (mk, html.count(mk)))


def render_check(html):
    """Render thu Jinja TRUOC khi ghi (trang di qua pipeline dynamic, su co 2026-07-23):
    biet loi truoc thi KHONG ghi, thay vi ghi roi ca cong ty nhan trang 500."""
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
        # SPA + Jinja pipeline: render dong theo phien (nhu truoc nay tren live).
        if not frappe.db.get_value("Web Page", name, "dynamic_template"):
            frappe.db.set_value("Web Page", name, "dynamic_template", 1)
            res["dynamic_template"] = "set"
        page_sync_util.record_live_sha(ROUTE, name)
    return res


@frappe.whitelist(methods=["POST"])
def sync_pm_source():
    """Dong bo /pm tu nguon repo (System Manager). Thay the sync_pm_page cu."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the PM page."), frappe.PermissionError)
    return sync()
