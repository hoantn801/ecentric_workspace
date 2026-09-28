# Copyright (c) 2026, eCentric and contributors
"""p213_resync_my_work_mascot: dong bo lai /viec-cua-toi sau khi doi linh vat sang "Khay"
(chot 25/09, Hoan chon trong 5 phuong an).

Vi sao can mot patch: trang nay KHONG co after_migrate - byte tren site chi doi khi co nguoi
goi page_sync.sync(). Sua main_section.html ma khong co patch nay thi deploy xong trang van
hien linh vat cu, va khong co gi bao loi ca.

Hai noi con lai dung chung linh vat thi KHONG can patch:
- /ec-hr/attendance, /ec-hr/leave: nam trong fixtures (hooks.py loc route like ec-hr/%),
  `bench migrate` tu dong bo tu fixtures/web_page.json.
- panel AI dien ho: la asset ec_aifill.bundle.js, build lai moi lan deploy.

my_work: repo so huu toan bo byte, khong khoa drift (xem page_sync.py)."""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Web Page"):
        return
    from ecentric_workspace.action_center.pages.my_work import page_sync as my_work
    try:
        frappe.logger("approval_center").info("p213 viec-cua-toi: %s" % my_work.sync())
    except Exception:
        # Mot trang loi khong duoc chan migrate cua ca site - chi ghi lai.
        frappe.log_error(title="p213_resync_my_work_mascot")
