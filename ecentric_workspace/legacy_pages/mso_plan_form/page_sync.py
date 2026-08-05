# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync for the LEGACY /mso-plan-form Web Page.

This is the MSO plan creation/edit form. Reached from the sidebar ('MSO
Request') and from /approval when a KAM opens an MSO for editing; /mso-form
301-redirects here.

#61 repo-ization (2026-08-03): main_section.html was imported VERBATIM from
live team.ecentric.vn -- main_section == main_section_html, sha-verified -- so
this page stops being site-only. Until now it existed on the server and nowhere
else: a rebuild would have lost it, and nothing in review could see what it
contained. The first sync against unchanged live content MUST return
{"action": "unchanged"}; that is the drift-detection dry run.

The page ships HTML only. Every action it performs (create/edit/submit, the
GBS/boxme push, the resubmit round-trip) is executed by live Server Scripts and
whitelisted endpoints, which this module does not touch."""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center import page_sync_util

ROUTE = "mso-plan-form"
NAME = "mso-plan-form"
TITLE = "MSO Plan Form"  # exact live title -- required for the first sync to be "unchanged"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


# sha256 of main_section.html as it ships in this commit == the live
# main_section_html at import time (5adb8dc45511b2182cfa4a1d64648f07377247239c85c79e0c0f714e3c9d60b2).
#
# upsert_web_page REFUSES to write (and changes nothing) when live hashes to
# none of the accepted values. This page has a history of being edited straight
# on the site, so without the lock a stray call to the endpoint below would
# silently revert those edits to whatever the repo happened to hold.
#
# Deliberate update = edit main_section.html, bump BASELINE_SHA256, and move the
# value it replaced into SUPERSEDES_SHA256 -- all in the same commit.
BASELINE_SHA256 = "11c71d930fd836b22150b27cae7fc8261a5d36f2905c4e90f3b69e963ccf61d9"
SUPERSEDES_SHA256 = (
    # bytes ban dau khi repo-hoa trang nay (#61). Live tren team.ecentric.vn da
    # duoc ghi thang len BASELINE_SHA256 ngay 2026-08-04 (round feedback MSO 1:
    # bo Channel, GMV -> NMV, preview chuoi duyet doc tu ec_mso_lookups.chain),
    # nen sync dau tien o do tra ve "unchanged"; entry nay de cac moi truong
    # chua nhan ban ghi do van sync tien len duoc.
    "5adb8dc45511b2182cfa4a1d64648f07377247239c85c79e0c0f714e3c9d60b2",
    # bytes cua round feedback MSO 1 truoc khi sua lai card "Chuoi duyet"
    # (fb round 1b, 2026-08-04). Ban render fb#3 nhet ten cap + email + ghi chu
    # thanh 3 con flex ngang nhau trong .cp-step (display:flex), cot email co lai
    # ~40px, cong word-break:break-all -> email bi be theo tung ky tu
    # ("lam.n / guyen / @ece / ntric.v / n"). Ban nay quay lai dung khung san co
    # cua trang (.cp-num + .cp-step-info), doi sang word-break:break-word +
    # overflow-wrap:anywhere, va cap nao co nhieu nguoi (Finance dang 4 nguoi) thi
    # hien bubble chu cai dau, tro chuot vao ra full mail -- giong cach lam o
    # trang duyet. Live team.ecentric.vn da duoc ghi thang len BASELINE_SHA256
    # cung ngay nen sync dau tien o do tra ve "unchanged".
    "eddcf6d7522c5bf210894d9c26f0c38d760823d5498afc7530a5b81534f2d6f0",
    # bytes truoc round feedback MSO 2 (2026-08-04): round do BO HAN loai phi
    # '% GMV' / '% NMV' khoi form. KAM go thang so tien vao o Amount; may chu
    # khong con tinh amount = fee_percent * forecast_gmv / 100 nua (nhanh do da
    # bi go khoi ec_mso_before_save v3.5). Bang ngan sach mat 2 cot 'Loai phi'
    # va '%'. Live team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung
    # ngay nen sync dau tien o do tra ve "unchanged".
    "161cd7a8dfa5273cb9720de650deb7a31ab3116c296e240d96c7d9bad3e38ab7",  # pre-mso-fb-2
    # bytes truoc round feedback MSO 3 (2026-08-05): dong dau tien cua dropdown
    # Team / Khoan muc la <option value=""></option> -- value rong VA text rong,
    # trinh duyet ve ra mot dong trang o dau danh sach. Round nay dat nhan that
    # ("-- Chon team --" / "-- Chon khoan muc --") va them script
    # ec-mso-searchable-dropdowns: combobox co o tim kiem dung dung mau UI/UX cua
    # ec-gbs-searchable-dropdowns tren /gbs-so-form-v2 va /gbs-po-form-v2, ap dung
    # cho #brand va 3 cot Team / Nhom / Khoan muc. Select goc van nam trong DOM
    # (an di) va van nhan value nen readRows()/fillCats()/submit khong doi. Live
    # team.ecentric.vn da duoc ghi thang len BASELINE_SHA256 cung ngay nen sync
    # dau tien o do tra ve "unchanged".
    "51135084243aa8819a56c6e4776dc99c142ecdcdf28e052fc8f1ffc43bc3ad38",  # pre-mso-fb-3
    # bytes cua ban combobox v1 (2026-08-05, cung ngay). v1 con 2 loi UI:
    # (1) o hien thi la <input readonly> nen dinh .f-control[readonly] ->
    # background var(--bg) + color var(--muted), o DA CHON cung bi to xam nhu
    # o khong nhap duoc; (2) panel dat position:absolute trong o cua bang nen
    # bi .bl-wrap{overflow-x:auto} (media max-width:1024px) cat cut danh sach.
    # v2 ghi de lai mau cho [readonly] (chi o CHUA chon moi xam) va doi panel
    # sang position:fixed render o document.body, tu lat len tren khi thieu
    # cho, cong tooltip khi chu bi cat ngang. Live team.ecentric.vn da duoc ghi
    # thang len BASELINE_SHA256 cung ngay nen sync dau tien o do tra ve
    # "unchanged".
    "9afb4ae3369be56ccd368ba5f246de5d4bef317f8e634351377573368c7a74b2",  # mso-fb-3 v1
)


def sync(html=None, force=0):
    """Guarded sync. publish=None never re-publishes a page an operator
    un-published; expect_sha refuses (writes nothing) on live drift.
    force=1 drops only the drift lock -- it never force-publishes."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish=None,
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") == "refused":
        return res
    if res.get("name") and frappe.db.exists("Web Page", res["name"]):
        res.update(page_sync_util.strip_legacy_shims(res["name"]))
        from ecentric_workspace.legacy_pages import serving
        res.update(serving.ensure_static_serving(res["name"], html))
    return res


@frappe.whitelist(methods=["POST"])
def sync_mso_plan_form_page():
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /mso-plan-form page."), frappe.PermissionError)
    return sync()
