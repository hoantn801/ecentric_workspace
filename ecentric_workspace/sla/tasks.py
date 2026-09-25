# Copyright (c) 2026, eCentric and contributors
"""Job dinh ky cua module SLA. Chi dieu phoi - logic nam o service.

Moi job o day deu boc try/except toan bo: mot job SLA chet khong duoc lam hong
hang doi scheduler chung cua site (noti, nhac han duyet don, dong bo). Bang diem
van dung neu job nay khong chay - `scoring.effective_status` tinh lai luc doc.
Job chi lam cho DB khop voi su that de Desk/report thay dieu UI thay.
"""
import frappe

from ecentric_workspace.sla.application import obligation_service


def sweep_overdue():
    """Hang gio: danh dau cac dau viec con mo ma da qua han."""
    try:
        res = obligation_service.sweep_overdue()
        if res.get("breached"):
            frappe.logger("sla").info("sweep_overdue: %s" % res)
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sweep_overdue", message=frappe.get_traceback())
        return None


def sync_weekly_reports():
    """Hang gio: doc `Weekly Team Update` -> mo/dong nghia vu bao cao tuan.

    CHI DOC ben bao cao tuan, khong sua mot dong nao ben do. Chay lai bao nhieu
    lan cung ra mot ket qua (khoa chong trung la chinh ban bao cao).
    """
    try:
        from ecentric_workspace.sla.infrastructure import weekly_source
        res = weekly_source.sync()
        if res.get("mo") or res.get("dong") or res.get("loi"):
            frappe.logger("sla").info(
                "sync_weekly: quet=%s mo=%s dong=%s khong_han=%s loi=%s"
                % (res.get("quet"), len(res.get("mo") or []), len(res.get("dong") or []),
                   len(res.get("khong_han") or []), len(res.get("loi") or [])))
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sync_weekly_reports",
                         message=frappe.get_traceback())
        return None


def sync_attendance():
    """Hang ngay: doc `Employee Checkin` -> mo/dong nghia vu ngay cong.

    Cua so mac dinh 7 ngay, khong phai 1: no phai bat duoc ca nguoi cham bu hom
    qua va phieu nghi vua duoc duyet hoi to trong tuan. Chay lai khong nhan doi
    gi - khoa chong trung la (nguoi, ngay).
    """
    try:
        from ecentric_workspace.sla.infrastructure import attendance_source
        res = attendance_source.sync()
        if res.get("hoi_to_nghi_phep") or res.get("loi"):
            frappe.logger("sla").info(
                "sync_attendance: mo=%s dong=%s hoi_to=%s loi=%s"
                % (len(res.get("mo") or []), len(res.get("dong") or []),
                   len(res.get("hoi_to_nghi_phep") or []), len(res.get("loi") or [])))
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sync_attendance",
                         message=frappe.get_traceback())
        return None


def sync_approvals():
    """Luoi do cho nhom Phan hoi phe duyet. Chay MOT LAN moi dem, khong phai hang gio.

    Duong CHINH la cac loi goi hook trong `transitions.py`. Job nay khong thay
    the chung - no quet lai va va vao nhung cho hook da truot: may chu restart
    giua giao dich, module SLA chua migrate tren mot bench, hoac mot loi bat ky
    ma `sla_port` da nuot de khong chan nguoi dang duyet don.

    VI SAO BAN DEM CHU KHONG PHAI HANG GIO. Job nay ghi vao `EC SLA Obligation`,
    dung bang ma hook dong bo cung ghi - BEN TRONG giao dich duyet don cua nguoi
    dung. Hai ben cham nhau thi khong chi mat mot dong SLA: MariaDB rollback CA
    giao dich duyet, va nguoi dung thay "Da duyet" trong khi ho so khong doi
    trang thai. Chay luc 02:00 dua xac suat do ve gan khong, va mot luoi do thi
    khong can thoi gian thuc - cham nhat mot ngay la du.

    Cua so 7 ngay, tran 1000 ho so: du de duoi kip mot su co ha tang keo vai
    ngay, va khong bao gio dam vao tran doc.
    """
    try:
        from ecentric_workspace.sla.infrastructure import approval_source
        res = approval_source.sync(days=7, limit=1000)
        if res.get("dong") or res.get("loai_tru") or res.get("loi") or res.get("khong_ro"):
            frappe.logger("sla").info(
                "sync_approvals: ho_so=%s dong=%s loai_tru=%s huy=%s khong_ro=%s loi=%s"
                % (res.get("ho_so"), len(res.get("dong") or []),
                   len(res.get("loai_tru") or []), len(res.get("huy") or []),
                   len(res.get("khong_ro") or []), len(res.get("loi") or [])))
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sync_approvals",
                         message=frappe.get_traceback())
        return None
def sync_leave_pauses():
    """Hang dem: cam doan tam dung cho nhung dau viec phe duyet roi vao ngay
    nghi phep da duyet.

    HOI TO LA LY DO CHINH NO CHAY MOI DEM, khong phai chi chay luc mo dau viec.
    Phieu nghi thuong duoc duyet SAU khi nguoi ta da nghi - dung cai canh da lam
    vo diem cua mot nguoi hom 21/09. Quet lai moi dem thi mot phieu duyet muon
    ba ngay van go duoc vet tre da cham hom kia.

    Cua so 14 ngay: du de duoi kip mot phieu nghi duyet muon ca tuan, va van nam
    gon trong mot lan chay ngan.
    """
    try:
        from ecentric_workspace.sla.infrastructure import leave_pause
        res = leave_pause.sync(days=14, limit=5000)
        if res.get("doan_moi") or res.get("doi_trang_thai") or res.get("loi"):
            frappe.logger("sla").info(
                "sync_leave_pauses: quet=%s doan_moi=%s doi_trang_thai=%s loi=%s"
                % (res.get("quet"), len(res.get("doan_moi") or []),
                   len(res.get("doi_trang_thai") or []), len(res.get("loi") or [])))
        return res
    except Exception:
        frappe.log_error(title="sla.tasks.sync_leave_pauses",
                         message=frappe.get_traceback())
        return None
