# Copyright (c) 2026, eCentric and contributors
"""p007: lich lam viec rieng cho nhan su truc livestream (03/11/2026, Hoan duyet).

BOI CANH: lich chung cua cong ty nghi T7 + CN. Team production truc livestream lam ca cuoi
tuan, nghi xoay ca trong tuan do lead xep. Voi lich chung: xin nghi vao T7/CN bi HRMS tu choi
("The day(s) ... are holidays"), cham cong cuoi tuan khong ra cong, ngay nghi xoay ca giua tuan
lai bi tinh thieu cong.

CACH LAM: moi nguoi mot Holiday List rieng "Livestream 2026 - <ten>":
    - TRUOC ngay ap dung: chep nguyen lich cong ty (ke ca T7/CN) - thang 10 da chot, ngay cu
      khong duoc doi nghia (khong de cuoi tuan cu bong thanh "thieu cong" / SLA Missed).
    - TU ngay ap dung: chi giu ngay LE (weekly_off = 0). T7/CN la ngay lam.
    - Ngay nghi xoay ca: lead / HR them dong vao lich rieng cua tung nguoi (Holiday List,
      mo ta "Nghi xoay ca"). Moi cho dung holiday_list (HRMS so ngay phep, cham cong web,
      nhac cham cong, SLA, lich cham cong) tu doc theo lich rieng.
Chi TAO lich con thieu + gan cho nguoi chua gan lich Livestream. Khong sua lich da co.
FAIL-SAFE: moi nguoi mot try, loi -> Error Log, khong chan migrate.
"""
import frappe

TITLE = "p007 lich livestream"
USERS = ("bao.tran@ecentric.vn", "an.tran@ecentric.vn", "sang.bui@ecentric.vn")
EFFECTIVE = "2026-11-03"
PREFIX = "Livestream 2026 - "


def build_rows(base_rows, effective=EFFECTIVE):
    """Dong cua lich rieng tu lich cong ty. Thuan, khong frappe.

    base_rows: [{"holiday_date": "YYYY-MM-DD", "description": str, "weekly_off": 0/1}]
    """
    out = []
    for r in base_rows:
        d = str(r.get("holiday_date"))[:10]
        if d < effective or not int(r.get("weekly_off") or 0):
            out.append({"holiday_date": d, "description": r.get("description") or "",
                        "weekly_off": int(r.get("weekly_off") or 0)})
    return sorted(out, key=lambda x: x["holiday_date"])


def _one(user, out):
    emp = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"},
                              ["name", "employee_name", "holiday_list", "company"], as_dict=True)
    if not emp:
        out["khong_thay"].append(user)
        return
    if (emp.holiday_list or "").startswith(PREFIX):
        out["da_co"].append(user)
        return
    base = emp.holiday_list or frappe.db.get_value("Company", emp.company, "default_holiday_list")
    if not base:
        out["khong_lich_goc"].append(user)
        return
    name = PREFIX + (emp.employee_name or emp.name)
    if not frappe.db.exists("Holiday List", name):
        b = frappe.get_doc("Holiday List", base)
        rows = build_rows([h.as_dict() for h in b.holidays])
        doc = frappe.get_doc({"doctype": "Holiday List", "holiday_list_name": name,
                              "from_date": b.from_date, "to_date": b.to_date,
                              "holidays": rows})
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True)
    frappe.db.set_value("Employee", emp.name, "holiday_list", name)
    out["gan"].append("%s -> %s" % (user, name))


def execute():
    out = {"gan": [], "da_co": [], "khong_thay": [], "khong_lich_goc": [], "loi": []}
    for u in USERS:
        sp = "p007_" + u.split("@")[0].replace(".", "_")
        try:
            frappe.db.savepoint(sp)
            _one(u, out)
        except Exception:
            frappe.db.rollback(save_point=sp)
            out["loi"].append(u)
            frappe.log_error(title=TITLE + " " + u, message=frappe.get_traceback())
    frappe.log_error(title=TITLE, message=str(out))
