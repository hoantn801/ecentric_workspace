# Copyright (c) 2026, eCentric and contributors
"""Cham lai nhung dau viec phe duyet da bi cham sai vi ngay nghi phep.

VIEC NAY SUA MOT HAU QUA DA XAY RA, khong phai chi bat luat moi len.

Ngay 21/09 - ngay dau tien nhom Phan hoi phe duyet tinh diem - mot nguoi nghi
phep nam da duoc duyet van bi mo 24 dau viec voi han tinh nhu ngay di lam. Bay
dau viec co han roi TRON vao ngay nghi va bi cham Tre / Chua lam. Khong co patch
nay thi luat moi chi cuu nhung dau viec tu hom nay tro di, con bay dong kia nam
nguyen trong diem thang 9 cua mot nguoi khong he lam gi sai.

Cua so 30 ngay de phu ca ngay 21/09 lan nhung phieu nghi duoc duyet muon truoc
do. Chay lai khong nhan doi gi: moi doan tam dung co khoa rieng va
`_recompute_paused` cong lai tu dau.

FAIL-SAFE: moi loi bi nuot va ghi Error Log. Mot patch hong chan CA lan deploy,
va job chay moi dem se lam lai dieu tuong tu.
"""
import frappe

TITLE = "p014 cham lai dau viec phe duyet roi vao ngay nghi phep"


def execute():
    try:
        from ecentric_workspace.sla.infrastructure import leave_pause
        res = leave_pause.sync(days=30, limit=5000)
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
        return

    try:
        frappe.log_error(
            title=TITLE,
            message="quet=%s nguoi=%s doan_moi=%s doi_trang_thai=%s loi=%s\n%s" % (
                res.get("quet"), res.get("nguoi"),
                len(res.get("doan_moi") or []),
                len(res.get("doi_trang_thai") or []),
                len(res.get("loi") or []),
                "\n".join((res.get("doi_trang_thai") or [])[:50])))
    except Exception:
        pass
