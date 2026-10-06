# Copyright (c) 2026, eCentric and contributors
"""p005: chay ngay phan "Mac dinh du cong" cho nguoi CnB vua tick (02/10/2026, Hoan duyet).

CnB tick o cho bac Tuan / bac Linh luc 11h ngay chot cong - sau job 06:05. Patch nay chay
mot lan khi deploy: ghi du cong tu ngay 1 thang truoc toi hom nay, huy nghia vu SLA cham cong
da sinh, va dong chot cong chua chot cua nguoi du cong -> "Da chot" (CnB chot thay).
Tu nay hook Employee.on_update lam viec nay ngay luc tick. FAIL-SAFE: nuot loi + Error Log.
"""
import frappe

TITLE = "p005 du cong ghi ngay"


def execute():
    from ecentric_workspace.hr import full_cong
    out = {}
    try:
        start, today = full_cong._window_start()
        out["ghi_cong"] = full_cong.mark_range(start, today)
        out["huy_sla"] = full_cong.cancel_sla(list(full_cong.users()))
        out["chot_cong"] = full_cong.close_rows()
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
    frappe.log_error(title=TITLE, message=str(out))
