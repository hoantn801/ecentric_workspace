# Copyright (c) 2026, eCentric and contributors
"""/weekly-update: dua nguon ve repo + go the he submit cu - 06/10/2026.

VI SAO

Nut Submit mang BA the he code chong len nhau:
  1. `initSubmit`          -- kiem + upload (`uploadPdfToSp`) + nop
  2. `attach`/`_validateHooked` -- chi kiem
  3. `attachHandler`/`weeklyOverrideV2` -> `doServerSubmit` -- upload
     (`wuUploadDeck`) + nop qua app method

The he 3 co `stopImmediatePropagation` dung de chan the he 1, nhung no dang ky
SAU nen the he 1 da chay xong truoc khi bi chan. Nut lai la `type="submit"` nam
trong form, nen mot cu bam kich hoat ca 'click' lan 'submit'.

Ket qua: MOT cu bam = HAI luong nop doc lap = hai phien upload cung ten tep.
Luong sau gap tep luong truoc vua tao -> HTTP 409 nameAlreadyExists. Ba nguoi
khong nop duoc bao cao W40/W41 (NV00083, NV00148, NV00173), 20 dong Error Log
trong ba ngay.

SUA

  - nut `type="submit"` -> `type="button"` (khong con kich hoat nop mac dinh)
  - go hai rang buoc cua the he 1; `handler` giu lai de doc duoc lich su

Phan kiem cua the he 1 KHONG mat: the he 2 kiem du ca ba (trang thai / slide /
cong cu AI), the he 3 kiem `employee`. Da doi chieu tung muc truoc khi go.

Truoc do mot ban va khac (a27bb354) doi ten tep khi gap 409. Da revert
(7c4f4c1f): no chua trieu chung, va moi lan nguoi dung bam lai sinh them mot
tep `(2)`, `(3)` trong SharePoint.

Idempotent: sync() tra ve "unchanged" tren site da co san ban nay.
"""
import frappe

#: Dau hieu phai CO tren ban live sau khi sync. Khong kiem "khong con X": chuoi
#: cu van nam trong chu thich giai thich lich su, nen kiem vang mat se bao dong gia.
_EXPECT = ('id="wu-btn-submit"', 'type="button" class="wu-btn-primary"')


def execute():
    from ecentric_workspace.weekly_report.pages.weekly_update import page_sync as wu

    try:
        res = wu.sync()
        action = (res or {}).get("action")
        frappe.log_error("p229 weekly-update sync=%s" % action, "p229 weekly-update")
        if action == "refused":
            frappe.log_error(
                "p229 weekly-update: upsert TU CHOI GHI (khoa chong troi). Live dang giu mot"
                " ban khong khop BASELINE_SHA256 - co nguoi sua tay tren Desk sau ban chup"
                " 06/10 10:34. Trang KHONG duoc cap nhat. Chup lai live, doi chieu, roi moi"
                " cap nhat baseline - dung nang baseline cho qua chuyen.",
                "p229 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "weekly-update"},
                                   "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html]
        if missing:
            frappe.log_error("p229 weekly-update: thieu landmark=%s" % missing,
                             "p229 KHONG toi noi")
    except Exception:
        # Patch chay trong migrate: mot exception lam chet ca lan deploy (bai hoc p116).
        frappe.log_error(frappe.get_traceback(), "p229 weekly-update failed")
