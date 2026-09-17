# Copyright (c) 2026, eCentric and contributors
"""Ngay bat dau cham diem cho tung nhom. Chu so huu chot 17/09/2026.

    Cham cong              01/09/2026   do luon ca thang 9
    Phan hoi phe duyet     21/09/2026
    RSVP lich hop          21/09/2026
    Bao cao tuan           21/09/2026
    Cong viec              21/09/2026   (van ngoai %SLA)

VI SAO CHAM CONG DUOC HOI TO MA NHUNG NHOM KIA THI KHONG. Luat cham cong truoc
10:00 da chay tren ban song tu lau, co nhac 08:30 va 09:30 moi ngay lam viec.
Moi nguoi da biet luat va da song voi no ca thang - do lai thang 9 khong bat ai
chiu mot cai han ho chua tung nghe. Con han phan hoi phe duyet thi vua duoc cau
hinh ngay 16/09 (patch p002); ap nguoc lai se cham `Missed` cho nhung buoc ma
luc do KHONG he co han nao.

DIEU CAN NOI TRUOC VOI NGUOI DOC BANG DIEM THANG 9: hai moc khac nhau lam thang
9 lech han. Cham cong co ~22 dau viec moi nguoi; ba nhom kia chi co phan tu
21/09 den 30/09, tuc la ~7 ngay lam viec. Nen %SLA thang 9 gan nhu la diem cham
cong. Tu thang 10 moi can bang. Trang /sla luon hien so dau viec cua tung nhom
ben canh ti le, nen dieu nay doc ra duoc - nhung van phai noi truoc.

21/09/2026 la thu Hai, nen ranh gioi khong cat ngang tuan bao cao nao.

FAIL-SAFE: moi dong boc rieng, ghi Error Log, luon ket thuc xanh.
"""
import frappe

from ecentric_workspace.sla.constants import (
    DT_TYPE, TYPE_APPROVAL_STEP, TYPE_ATTENDANCE_DAY, TYPE_RSVP, TYPE_TASK,
    TYPE_WEEKLY_REPORT,
)

START_DATES = {
    TYPE_ATTENDANCE_DAY: "2026-09-01",
    TYPE_APPROVAL_STEP: "2026-09-21",
    TYPE_RSVP: "2026-09-21",
    TYPE_WEEKLY_REPORT: "2026-09-21",
    TYPE_TASK: "2026-09-21",
}


def execute():
    done, failed = [], []
    for type_code, start in sorted(START_DATES.items()):
        try:
            name = frappe.db.get_value(DT_TYPE, {"type_code": type_code}, "name")
            if not name:
                failed.append("%s (khong thay loai)" % type_code)
                continue
            current = frappe.db.get_value(DT_TYPE, name, "effective_from")
            if str(current or "") == start:
                done.append("%s da dung (%s)" % (type_code, start))
                continue
            frappe.db.set_value(DT_TYPE, name, "effective_from", start)
            done.append("%s: %s -> %s" % (type_code, current or "(trong)", start))
        except Exception:
            failed.append(type_code)
            frappe.log_error(title="p004 effective_from %s" % type_code,
                             message=frappe.get_traceback())

    frappe.log_error(
        title="p004 ngay bat dau cham diem tung nhom",
        message="\n".join(done + (["LOI: " + ", ".join(failed)] if failed else [])))
