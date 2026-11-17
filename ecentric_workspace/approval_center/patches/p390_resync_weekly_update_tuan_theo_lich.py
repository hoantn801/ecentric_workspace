# Copyright (c) 2026, eCentric and contributors
"""/weekly-update: tuan mac dinh theo LICH + hoi lai khi nop nham tuan - 17/11/2026.

Su co 15-16/11: hai bao cao W46 roi vao W47 vi trang tu nhay sang tuan sau tu T6 18:00.
Cung la dieu kien de doi han phong Operation & Data & System sang CN 23:59.

Nguon doi:
  * calculateCurrentWeek(): bo nhay tuan T6 18:00 - mac dinh la tuan lich chua hom nay.
  * Tuan truoc con ban nhap (chua nop): T2-T4 mo thang tuan truoc, T5-CN mo tuan nay va
    nhac; luon co link chuyen tuan (o #wu-week-hint, an san trong markup).
  * doServerSubmit(): hoi lai (confirm) neu ten tep ghi tuan khac / nop tuan chua toi.
    VAN mot duong nop duy nhat (bai hoc 409, p229/p230).

Idempotent: sync() tra "unchanged" khi live da la ban nay. Khoa chong troi chap nhan ban
p230 dang tren live (SUPERSEDES_SHA256). Loi chi ghi log, khong bao gio nem (bai hoc p116).
"""
import frappe

_EXPECT = ("function pickDefaultWeek(", "function wuWeekMismatch(", 'id="wu-week-hint"',
           'type="button" class="wu-btn-primary"')
_FORBID = ("Rollover sau deadline T6 18:00",)


def execute():
    from ecentric_workspace.weekly_report.pages.weekly_update import page_sync as wu

    try:
        res = wu.sync() or {}
        action = res.get("action")
        frappe.log_error("p390 weekly-update sync=%s" % action, "p390 weekly-update")
        if action == "refused":
            frappe.log_error(
                "p390 weekly-update: TU CHOI GHI - live_sha=%s khong nam trong BASELINE/SUPERSEDES."
                " Co the co nguoi sua tay tren Desk. Chup lai live (KHONG BOM), doi chieu roi moi cap nhat."
                % res.get("live_sha"), "p390 REFUSED")
            return
        html = frappe.db.get_value("Web Page", {"route": "weekly-update"}, "main_section_html") or ""
        missing = [m for m in _EXPECT if m not in html] + [m for m in _FORBID if m in html]
        if missing:
            frappe.log_error("p390 weekly-update: dau moc sai=%s" % missing, "p390 KHONG toi noi")
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p390 weekly-update failed")
