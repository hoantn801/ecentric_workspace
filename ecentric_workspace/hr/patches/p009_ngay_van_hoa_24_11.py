# Copyright (c) 2026, eCentric and contributors
"""p009: danh sach di lam Ngay Van hoa Viet Nam 24/11/2026 (Hoan, 24/11/2026).

Ca cong ty nghi 24/11 (da them vao lich nghi cong ty + 3 lich Livestream truc tiep tren
ban song). 23 ban dang ky di lam campaign: tinh nhu ngay lam binh thuong, thuong 500K +
2 ngay phep nam, KHONG xin nghi bu OT cho ngay nay. Danh sach theo file HR "DANH SACH NHAN
SU LAM VIEC NGAY VAN HOA VIET NAM 24/11/2026"; Nguyen Thi Yen Nhi file ghi NV00161 nhung
ho so ERP la NV00157 -> dung NV00157.
Chi tao neu chua co dot nao ngay 24/11. Luu xong -> service.apply: ghi bu ngay cong cho
nguoi cham cong dung gio, cong 2 ngay phep cho nguoi da cham cong. FAIL-SAFE.
"""
import frappe

DAY = "2026-11-24"
CODES = (
    "NV00167 NV00154 NV00176 NV00131 NV00013 NV00138 NV00143 NV00062 NV00003 NV00102 "
    "NV00083 NV00163 NV00188 NV00124 NV00140 NV00183 NV00039 NV00157 NV00145 NV00021 "
    "NV00146 NV00084 NV00040"
)


def execute():
    try:
        if not frappe.db.table_exists("EC Holiday Work"):
            return
        if frappe.db.exists("EC Holiday Work", {"work_date": DAY}):
            return
        doc = frappe.get_doc({
            "doctype": "EC Holiday Work",
            "title": "Ngày Văn hoá Việt Nam 24/11/2026",
            "work_date": DAY,
            "counts_as_workday": 1,
            "require_checkin": 1,
            "allow_comp_off": 0,
            "leave_bonus_days": 2,
            "cash_bonus": 500000,
            "paste_codes": CODES,
            "note": "Campaign 24/11. Địa điểm: Văn phòng eCentric / Raw Studio. "
                    "Yến Nhi: file HR ghi NV00161, hồ sơ ERP là NV00157.",
        })
        doc.insert(ignore_permissions=True)
    except Exception:
        frappe.log_error(title="p009_ngay_van_hoa_24_11", message=frappe.get_traceback())
