# Copyright (c) 2026, eCentric and contributors
"""p212_resync_hr_nav_pages: dong bo lai hai trang co sidebar tinh nhom Nhan su sau khi
them muc 'Phan bo cong viec' vao hr/nav.py (25/09).

Vi sao can: sidebar tinh trong HTML moi trang do shell.fallback sinh tu registry. Them
mot muc menu thi byte trang doi, nhung ban tren site van giu sidebar cu cho toi khi co
nguoi sync lai. ec_shell.js van ve dung menu luc chay, nen day la sua lop du phong - nguoi
tat JS, hoac trang nap truoc khi shell boot, se khong thay mot menu thieu muc.

- install_guide: repo so huu toan bo byte, khong khoa drift.
- sla scoreboard: co khoa drift; ban live cu (1ff637d8...) da nam trong SUPERSEDES."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    log = frappe.logger("approval_center")
    from ecentric_workspace.hr.pages.install_guide import page_sync as guide
    from ecentric_workspace.sla.pages.scoreboard import page_sync as sla
    for name, mod in (("install_guide", guide), ("sla_scoreboard", sla)):
        try:
            log.info("p211 %s: %s" % (name, mod.sync()))
        except Exception:
            # Mot trang loi khong duoc chan migrate cua ca site - chi ghi lai.
            frappe.log_error(title="p212_resync_hr_nav_pages: %s" % name)
