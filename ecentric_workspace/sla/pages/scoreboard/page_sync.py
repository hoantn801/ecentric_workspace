# Copyright (c) 2026, eCentric and contributors
"""Dong bo Web Page /sla tu ma nguon trong repo. Chay lai duoc, co khoa chong ghi de.

Dung lai `approval_center/shared/page_sync.py` thay vi viet ban thu hai: no da
xu ly dung ba cho de sai ma khong ai thay - Frappe dat ten Web Page theo slug
(nen `insert` dam vao khoa chinh neu trang da ton tai), co truong hop trang duoc
tao boi mot lan migrate hong, va co truong hop nguoi van hanh tat `published`.

KHOA CHONG GHI DE (`expect_sha`). Ban chi ap dung khi trang DA TON TAI: lan sync
dau tien tao trang sach se, khong bi chan. Tu lan thu hai tro di, neu ai do sua
tay HTML tren Desk thi ban repo KHONG duoc phep lang le ghi de len - viec lay
lai ban repo phai la mot hanh dong co y (bump BASELINE_SHA256).

CAP NHAT SAU NAY: sua `main_section.html` canh ben, doi BASELINE_SHA256 thanh
sha moi, day gia tri cu xuong SUPERSEDES_SHA256 - ca ba trong CUNG mot commit
(`tools/ci/check.py --only pagesync` bat duoc neu quen). Roi goi
`ecentric_workspace.sla.controllers.api.sync_sla_page`, hoac de patch moi chay.

VI SAO TEP NAY NAM O `sla/pages/scoreboard/` CHU KHONG PHAI `sla/ui/`. Do la
noi `shell/fallback.py` di tim cac trang do module so huu: no doc `ROUTE` o day,
roi dung lai khoi sidebar tinh nam san trong HTML tu chinh so dang ky nav. Dat
tep o cho khac thi trang van chay - nhung khoi sidebar tinh se dong bang tai
ngay hom nay, va lan sau co nguoi them mot muc menu, moi trang deu cap nhat tru
trang nay. Mot cai lech khong ai thay cho toi khi no da cu.
"""
import hashlib
import os

import frappe

from ecentric_workspace.approval_center.shared import page_sync as page_sync_util

ROUTE = "sla"
NAME = "sla-scoreboard"
TITLE = "Điểm SLA"


def _html():
    here = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(here, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def shipped_sha():
    """sha256 cua HTML ma commit nay ship. De doi chieu khi bump baseline."""
    return hashlib.sha256(_html().encode("utf-8")).hexdigest()


# sha256 cua dung ban HTML commit nay ship. Trang /sla chua ton tai tren ban song
# truoc dot nay, nen lan sync dau khong cham vao khoa - gia tri o day la de tu lan
# thu hai tro di.
BASELINE_SHA256 = "41e7476d633c60faac2426c3511782d52f05b530decd6a35b11055828659447f"

#: Cac gia tri live ma ban nay duoc phep ghi de (ban repo truoc do). Rong o lan
#: dau vi chua co ban nao truoc.
SUPERSEDES_SHA256 = (
    "7af9926bb71c2276c22ebc522f1d4b328e93373894376cc3de7f6e1c59df0433",  # ban B7 - dang chay tren live truoc dot nay
    "c548ee191823595295d328d2306b61c53f1c31a667ba53a1d4153fe39f8a262a",  # ban B6 - dang chay tren live truoc dot nay
)


def sync(html=None, force=0):
    """Tra ve {action: created|updated|unchanged|skipped|refused, route, name}."""
    html = html if html is not None else _html()
    res = page_sync_util.upsert_web_page(
        ROUTE, NAME, TITLE, html,
        publish="preserve",
        expect_sha=None if force else ((BASELINE_SHA256,) + SUPERSEDES_SHA256),
    )
    if res.get("action") != "refused" and res.get("name") \
            and frappe.db.exists("Web Page", res["name"]):
        # Ghi lai sha SAU khi may chu xu ly (sanitize + strip shim), de lan sync
        # sau nhan ra chinh ban ghi cua minh thay vi bao "live drift".
        res["recorded_sha"] = page_sync_util.record_live_sha(ROUTE, res["name"])
    return res
