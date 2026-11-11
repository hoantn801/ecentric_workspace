# Copyright (c) 2026, eCentric and contributors
"""12/11/2026: chuan hoa phieu hop dong KOL NHAP tao truoc dot "dung lai mau tool cu".

Ban 11/11 tu dien san hai gia tri ma nay hieu khac:
  * contract_date = ngay tao phieu -> nay ngay ky tu tinh = 1 ngay lam viec truoc buoi dau. Giu
    nguyen thi he thong coi la ngay nguoi dung chon va "dinh" lai. Xoa de lan luu sau tu tinh.
  * payment_term_days = 30 cho moi loai -> nay ca nhan mac dinh 35 (tool cu). Doi 30 -> 35 cho
    phieu ca nhan.
CHI phieu chua gui (khong co approval_request): phieu da gui / da duyet giu nguyen so nguoi duyet
da thay. Chay lai nhieu lan an toan (dieu kien tu loai phieu da sua). Khong nem loi.
"""
import frappe

DT = "EC Contract Review Request"
KOL = "KOL/KOC / Creator (EC)"


def execute():
    if not frappe.db.exists("DocType", DT):
        return
    try:
        rows = frappe.get_all(DT, filters={"contract_type": KOL, "approval_request": ["is", "not set"]},
                              fields=["name", "creation", "contract_date", "creator_type", "payment_term_days"],
                              limit_page_length=0)
        n_date = n_days = 0
        for r in rows:
            upd = {}
            if r.contract_date and str(r.contract_date)[:10] == str(r.creation)[:10]:
                upd["contract_date"] = None
                n_date += 1
            if r.creator_type == "Cá nhân" and int(r.payment_term_days or 0) == 30:
                upd["payment_term_days"] = 35
                n_days += 1
            if upd:
                frappe.db.set_value(DT, r.name, upd, update_modified=False)
        frappe.logger("approval_center").info("p365: %d phieu nhap KOL, bo ngay ky mac dinh %d, 30->35 ngay %d"
                                              % (len(rows), n_date, n_days))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p365 chuan hoa nhap KOL")
