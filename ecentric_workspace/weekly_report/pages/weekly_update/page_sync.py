# Copyright (c) 2026, eCentric and contributors
"""Idempotent sync cho /weekly-update -- trang nop bao cao tuan.

VI SAO TRANG NAY MOI VAO REPO HOM NAY (06/10/2026)

`02_CURRENT_STRUCTURE.md` da danh dau trang nay `[NEEDS LIVE VERIFICATION]` tu
thang 5: nguon duy nhat la mot ban local trong thu muc session cu, va
`deploy_weekly_update.ps1` doc tu do. Khong ai chac ban local con khop live.
Nen moi lan sua la sua thang tren trang live, va moi lan sua lai them mot lop.

Hau qua do dem duoc, 05/10: nut Submit mang BA the he code chong len nhau --
`initSubmit` (the he 1: kiem + upload + nop), `attach`/`_validateHooked`
(the he 2: chi kiem), `attachHandler`/`weeklyOverrideV2` -> `doServerSubmit`
(the he 3: upload + nop qua app method). The he 3 co `stopImmediatePropagation`
dung de chan the he 1, nhung no dang ky SAU nen the he 1 da chay xong truoc khi
bi chan. Mot cu bam = HAI luong nop = hai phien upload cung ten tep = HTTP 409
nameAlreadyExists. Ba nguoi khong nop duoc bao cao W40/W41.

Day la truong hop A65 noi toi. Nen buoc dau khong phai la va tiep, ma la dua
nguon ve repo -- lan nay nguyen van tung byte tu live, chua sua gi.

KHOA CHONG TROI

`BASELINE_SHA256` la ma bam cua ban live luc chup (06/10/2026 10:34). `sync()`
TU CHOI ghi de khi live khong con khop -- nghia la co nguoi da sua tay tren
Desk sau ban chup, va ghi de se xoa mat sua doi do. Gap "refused" thi chup lai
live, doi chieu, roi moi cap nhat baseline; dung nang baseline cho qua chuyen.
"""
import os

import frappe
from frappe import _

from ecentric_workspace.approval_center.shared import page_sync

ROUTE = "weekly-update"

#: Ten BAN GHI khac ten route: ban ghi la "bao-cao-tuan" co dau, route la
#: "weekly-update". Mot probe 28/09 loc theo route chua "bao-cao-tuan" va khong
#: ra gi ca -- vi tim nham truong. `find_web_page` tim theo route truoc nen van
#: dung, nhung ghi ten that o day de nguoi sau khoi mat mot vong tim.
NAME = "báo-cáo-tuần"
TITLE = "Báo cáo tuần"

#: sha256 cua `main_section_html` live luc chup nguon (06/10/2026 10:34).
#: Xem docstring: doi so nay ma khong doi chieu live truoc la xoa sua doi cua
#: nguoi khac.
#:
#: SO NAY DA SAI MOT LAN -- doc truoc khi doi. Ban dau la 265c3d0a..., tinh tren
#: file chup co BOM o dau. Nhung live KHONG co BOM: BOM do chinh script chup
#: chen vao, vi `[IO.File]::WriteAllText(..., [Text.Encoding]::UTF8)` cua .NET
#: tu ghi preamble EF BB BF. Ket qua: p229 chay ngay 06/10 14:25 va BI TU CHOI
#: ("live khong khop baseline") du khong ai sua trang. Khoa chan DUNG -- neu no
#: cho qua thi da day mot ky tu BOM len dau trang live.
#: Bai hoc: chup nguon thi ghi bang `New-Object Text.UTF8Encoding $false`, va
#: tinh baseline tu chuoi DOC tu DB, khong tu file da ghi xuong dia.
BASELINE_SHA256 = "7e481f0faaf6c0062fde5eea5fc3b702bd5757615bcdfbaaf1cc52b04b92be78"


def _html():
    base = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(base, "main_section.html"), encoding="utf-8") as fh:
        return fh.read()


def sync(html=None, expect_sha=BASELINE_SHA256):
    """Dong bo nguon repo len trang live. -> dict cua upsert_web_page.

    `expect_sha=None` de ep ghi de khi da doi chieu bang tay va chac chan muon
    ghi. Mac dinh LUON co khoa: trang nay co nguoi dung that moi tuan, ghi de
    nham la mat mot bai sua doi ma khong ai biet.
    """
    html = html if html is not None else _html()
    return page_sync.upsert_web_page(ROUTE, NAME, TITLE, html,
                                     publish=1, expect_sha=expect_sha)


@frappe.whitelist(methods=["POST"])
def sync_weekly_update_page(force=0):
    """Chay tay tu Desk/API. System Manager, vi no ghi de mot trang dang chay."""
    if "System Manager" not in frappe.get_roles(frappe.session.user):
        frappe.throw(_("Only System Manager may sync the /weekly-update page."),
                     frappe.PermissionError)
    return sync(expect_sha=None if int(force or 0) else BASELINE_SHA256)
