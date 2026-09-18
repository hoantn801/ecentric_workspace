# Copyright (c) 2026, eCentric and contributors
"""Quet lai cham cong mot lan ngay luc deploy, thay vi doi den lan chay dem.

VI SAO CAN. Truoc dot nay, nghia vu ngay cong chi duoc dong boi job chay moi
dem. Han la 10:00, nen ngay tai thoi diem deploy dang co mot loat ngay cong cua
HOM NAY nam o `Open` da qua han - tuc la `effective_status` doc ra thanh
`Missed` cho nhung nguoi DA cham cong dung gio. Hook moi chi dong cho nhung lan
cham cong TU GIO TRO DI; nhung lan da cham sang nay thi khong co su kien nao de
kich hoat nua.

Mot lan quet o day xoa ngay cai vet do. Khong co no thi deploy xanh nhung bang
diem van sai cho toi dem, va nguoi ta se doc con so sai do trong nua ngay.

CHAY LAI DUOC: khoa chong trung la (nguoi, ngay), nen quet lai khong nhan doi gi.

FAIL-SAFE: moi loi bi nuot va ghi Error Log. Mot patch hong chan CA lan deploy,
va viec nay khong quan trong den muc do - job dem se lam lai dieu tuong tu.
"""
import frappe

TITLE = "p011 quet lai cham cong sau khi cam hook thoi gian thuc"


def execute():
    try:
        from ecentric_workspace.sla.infrastructure import attendance_source
        res = attendance_source.sync()
    except Exception:
        frappe.log_error(title=TITLE, message=frappe.get_traceback())
        return

    try:
        frappe.log_error(
            title=TITLE,
            message="nhan_vien=%s dong=%s mo=%s loai_tru=%s hoi_to=%s loi=%s" % (
                res.get("nhan_vien"),
                len(res.get("dong") or []), len(res.get("mo") or []),
                len(res.get("loai_tru") or []),
                len(res.get("hoi_to_nghi_phep") or []),
                len(res.get("loi") or [])))
    except Exception:
        pass
