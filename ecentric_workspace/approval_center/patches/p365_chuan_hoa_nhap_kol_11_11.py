# Copyright (c) 2026, eCentric and contributors
"""12/11/2026: chuan hoa phieu hop dong KOL NHAP tao truoc dot "dung lai mau tool cu".

Ban 11/11 tu dien san hai gia tri ma nay hieu khac:
  * contract_date = ngay tao phieu -> nay ngay ky tu tinh = 1 ngay lam viec truoc buoi dau. Giu
    nguyen thi he thong coi la ngay nguoi dung chon va "dinh" lai. Xoa de lan luu sau tu tinh.
  * payment_term_days = 30 cho moi loai -> nay ca nhan mac dinh 35, cong ty + Shopee 15 (tool cu).
    Doi 30 -> 35 (ca nhan) / 30 -> 15 (cong ty Shopee).
Moi phieu bi sua co mot dong ghi chu (vet: ai / sua gi), log ghi ten phieu.
CHI phieu chua gui (khong co approval_request): phieu da gui / da duyet giu nguyen so nguoi duyet
da thay. Chay lai nhieu lan an toan (dieu kien tu loai phieu da sua). Khong nem loi.
"""
import frappe

DT = "EC Contract Review Request"
KOL = "KOL/KOC / Creator (EC)"


def _comment(name, text):
    try:
        frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": DT,
                        "reference_name": name, "content": text}).insert(ignore_permissions=True)
    except Exception:
        pass                        # ghi chu chi la vet; khong vi no ma bo do sua du lieu


def execute():
    if not frappe.db.exists("DocType", DT):
        return
    try:
        rows = frappe.get_all(DT, filters={"contract_type": KOL, "approval_request": ["is", "not set"]},
                              fields=["name", "creation", "contract_date", "creator_type", "platform", "payment_term_days"],
                              limit_page_length=0)
        n_date = n_days = 0
        touched = []
        for r in rows:
            upd = {}
            if r.contract_date and str(r.contract_date)[:10] == str(r.creation)[:10]:
                upd["contract_date"] = None
                n_date += 1
            days = int(r.payment_term_days or 0)
            if r.creator_type == "Cá nhân" and days == 30:
                upd["payment_term_days"] = 35
            elif r.creator_type == "Công ty" and r.platform == "Shopee" and days == 30:
                upd["payment_term_days"] = 15
            if "payment_term_days" in upd:
                n_days += 1
            if upd:
                frappe.db.set_value(DT, r.name, upd, update_modified=False)
                note = []
                if "contract_date" in upd:
                    note.append("bỏ ngày ký mặc định %s (nay tự tính theo buổi đầu)" % str(r.contract_date)[:10])
                if "payment_term_days" in upd:
                    note.append("số ngày thanh toán %d -> %d (theo tool cũ)" % (days, upd["payment_term_days"]))
                _comment(r.name, "p365: " + "; ".join(note) + ".")
                touched.append(r.name)
        frappe.logger("approval_center").info("p365: %d phieu nhap KOL, bo ngay ky mac dinh %d, doi so ngay %d: %s"
                                              % (len(rows), n_date, n_days, ", ".join(touched)))
    except Exception:
        frappe.log_error(frappe.get_traceback(), "p365 chuan hoa nhap KOL")
