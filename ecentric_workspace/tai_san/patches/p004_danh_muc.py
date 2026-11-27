# Copyright (c) 2026, eCentric and contributors
"""p004_danh_muc - danh muc phan mem cho ban quyen (Hoan 27/11/2026).

Ban quyen da nhap truoc khi co danh muc (go tay ten) -> noi vao EC Software Product theo ten da chuan
hoa (bo dau / hoa thuong / khoang trang): ten trung khoa ve MOT phan mem, chua co thi tao. Ten GIONG
nhung khac khoa (vd "wins 11 pro" vs "Windows 11 Pro") khong tu gop - nguoi quan ly Gop tren trang.
Idempotent: chi xu ly ban quyen con trong `product`. Loi -> Error Log, khong chan migrate.
"""
import frappe


def execute():
    if not frappe.db.exists("DocType", "EC Software Product"):
        return
    try:
        from ecentric_workspace.tai_san import jobs as J
        from ecentric_workspace.tai_san import product_service as PS
        res = PS.link_unlinked(J._system_ctx())
        frappe.logger("tai_san").info("p004: %s" % res)
    except Exception:
        frappe.log_error(title="tai_san p004_danh_muc", message=frappe.get_traceback())
