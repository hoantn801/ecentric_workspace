# Copyright (c) 2026, eCentric and contributors
"""Tac vu nen cua module tai san (dang ky trong hooks.py scheduler_events.cron).

  * 00:40 moi ngay - `return_due_today`: nhan vien co ngay lam viec cuoi = HOM QUA (Clearance /
    Employee.relieving_date) ma con giu may -> may sang "Cho kiem tra", go nguoi giu, bao Ops.
    00:40 (khong phai 00:30 / 00:45): tranh bao scheduler :00/:15/:30/:45 da biet (loi 1205),
    va chay SAU luot khoa tai khoan 00:30.
  * 08:20 moi ngay - `license_alerts`: nhac ban quyen sap het han / qua han (dot 4).
  * 01:10 ngay 1 hang thang - `monthly_snapshot`: chot so lieu THANG TRUOC vao EC Asset Monthly
    (tung may; chay lai chi chot may con thieu; khoa duy nhat (month, asset) o DocType).

Ca hai idempotent, loi tung may ghi Error Log va di tiep (mot may loi khong giet ca lo).
"""
import frappe
from frappe.utils import add_days, getdate, nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import depreciation as D
from ecentric_workspace.tai_san import license_repository as LR
from ecentric_workspace.tai_san import license_service as LS
from ecentric_workspace.tai_san import licenses as LIC
from ecentric_workspace.tai_san import repository as R
from ecentric_workspace.tai_san import reports as RP
from ecentric_workspace.tai_san import service as S

SYSTEM_CTX_USER = "Administrator"


def _system_ctx():
    return A.Ctx(SYSTEM_CTX_USER, [C.ROLE_SYSTEM])


def return_due_today():
    """Ngay lam viec cuoi trong RETURN_CATCHUP_DAYS ngay qua (tinh ca hom qua): dem nao loi / bi
    bo qua thi dem sau bat lai. Idempotent: may da thu hoi khong con nguoi giu nen khong xu ly lai."""
    day = add_days(getdate(nowdate()), -1)
    leaving = R.employees_left_between(add_days(day, 1 - C.RETURN_CATCHUP_DAYS), day)
    if not leaving:
        return {"day": str(day), "returned": 0}
    ctx = _system_ctx()
    done = []
    for a in R.assets({"custodian": ["in", list(leaving)], C.INSTALLED_ON_FIELD: ["is", "not set"]}):
        if a.get(C.OPS_STATUS_FIELD) not in (C.ST_IN_USE, C.ST_RESERVED):
            continue
        try:
            last_day, clr = leaving[a.get("custodian")]
            S.transition(ctx, a["name"], C.A_RETURN, ref_doctype=C.SRC_CLEARANCE if clr else None,
                         ref_name=clr, note="Tự động: hết ngày làm việc cuối %s" % last_day)
            done.append(a.get(C.TAG_FIELD) or a["name"])
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="tai_san return_due_today %s" % a["name"])
    licenses = []
    for emp, (last_day, clr) in leaving.items():
        try:
            names = LS.revoke_for_leaver(ctx, emp, ref_doctype=C.SRC_CLEARANCE if clr else None,
                                         ref_name=clr, last_day=last_day)
            licenses += names
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="tai_san return_due_today license %s" % emp)
    if done:
        R.notify_role(C.ROLE_MANAGER, "Thu hồi tự động (nghỉ việc %s): %s - kiểm tra máy trên /tai-san/luan-chuyen."
                      % (day, ", ".join(done)), "/" + C.ROUTE_MOVES)
    if licenses:
        R.notify_role(C.ROLE_MANAGER, "Đã thu %d chỗ bản quyền của nhân viên nghỉ việc - xem /tai-san/ban-quyen "
                      "(huỷ tài khoản bên hãng nếu cần)." % len(licenses), "/" + C.ROUTE_LICENSES)
    return {"day": str(day), "returned": len(done), "licenses_revoked": len(licenses)}


def license_alerts():
    """08:20 hang ngay: bao ban quyen sap het han (truoc 30 ngay; goi thang truoc 10 ngay) va da qua
    han. Moi moc chi bao MOT lan cho moi han (alert_stage + alert_for_expiry); gia han xong tu reset.
    08:20 - gio lam viec, ngoai bao scheduler :00/:15/:30/:45."""
    today = getdate(nowdate())
    sent = 0
    for lic in LR.licenses({"status": ["in", [C.LS_ACTIVE, C.LS_EXPIRED]]}):
        st = LIC.needs_alert(lic, today)
        if not st:
            continue
        try:
            left = LIC.days_left(lic, today)
            exp = str(lic.expiry_date)[:10]
            if st == C.STAGE_DUE:
                msg = ("Bản quyền %s hết hạn HÔM NAY (%s)" % (lic.license_name, exp) if left == 0
                       else "Bản quyền %s hết hạn sau %d ngày (%s)" % (lic.license_name, left, exp))
            else:
                msg = "Bản quyền %s đã quá hạn từ %s" % (lic.license_name, exp)
            msg += " - gia hạn hoặc huỷ trên /tai-san/ban-quyen."
            link = "/%s?id=%s" % (C.ROUTE_LICENSES, lic.name)
            values = {"alert_stage": st, "alert_for_expiry": exp}
            if st == C.STAGE_EXPIRED:
                values["status"] = C.LS_EXPIRED
            # Ghi truoc, bao sau, va CHI khi han chua doi tu luc doc danh sach (ai do vua gia han giua
            # chung thi bo qua - khong danh dau Het han nham, khong bao thua).
            if not LR.set_license_if(lic.name, lic.expiry_date, values):
                frappe.db.rollback()
                continue
            R.notify_role(C.ROLE_MANAGER, msg, link)
            owner = R.employee_user(lic.owner_employee) if lic.owner_employee else None
            if owner:
                R.notify([owner], msg, link)
            sent += 1
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="tai_san license_alerts %s" % lic.name)
    return {"alerts": sent}


def monthly_snapshot(month=None):
    """Chot thang `month` ('YYYY-MM'; mac dinh: thang truoc). Da chot roi thi bo qua."""
    ym = D.month_key(month) if month else D.add_months(D.month_key(getdate(nowdate())), -1)
    key = D.month_str(ym)
    done = R.monthly_assets(key)
    prev = R.monthly_accumulated(D.month_str(D.add_months(ym, -1)))
    cats = R.categories()
    repair_by_asset = {}
    for r in R.repairs({"status": C.REP_DONE}):
        when = r.returned_date or r.sent_date
        if when and D.month_str(D.month_key(when)) == key:
            repair_by_asset[r.asset] = repair_by_asset.get(r.asset, 0) + float(r.actual_cost or 0)
    n = 0
    for a in R.assets():
        if a["name"] in done:
            continue
        try:
            life = (cats.get(a.get("asset_category")) or {}).get("ec_default_life_months")
            d = D.compute(a, life, ym)
            # Khau hao thang = luy ke thang nay - luy ke da chot thang truoc: thang nao bi lech (may
            # tim thay lai, sua nguyen gia...) thi phan chenh don vao thang nay, tong cac thang luon
            # bang luy ke. Chua co thang truoc -> dung so cua lich.
            dep = round(d["accumulated"] - prev[a["name"]], 2) if a["name"] in prev else d["this_month"]
            if a.get(C.OPS_STATUS_FIELD) == C.ST_DISPOSED and not dep:
                continue
            R.insert_monthly({"month": key, "asset": a["name"], "asset_category": a.get("asset_category"),
                              "status": a.get(C.OPS_STATUS_FIELD), "holder": a.get("custodian"),
                              "department": a.get("department"), "gross": d["gross"],
                              "depreciation": dep, "accumulated": d["accumulated"],
                              "nbv": d["nbv"], "repair_cost": repair_by_asset.get(a["name"], 0),
                              "rent": RP.rent_of(a)})
            n += 1
            frappe.db.commit()
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="tai_san monthly_snapshot %s %s" % (key, a["name"]))
    return {"month": key, "rows": n}
