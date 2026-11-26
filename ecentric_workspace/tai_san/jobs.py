# Copyright (c) 2026, eCentric and contributors
"""Tac vu nen cua module tai san (dang ky trong hooks.py scheduler_events.cron).

  * 00:40 moi ngay - `return_due_today`: nhan vien co ngay lam viec cuoi = HOM QUA (Clearance /
    Employee.relieving_date) ma con giu may -> may sang "Cho kiem tra", go nguoi giu, bao Ops.
    00:40 (khong phai 00:30 / 00:45): tranh bao scheduler :00/:15/:30/:45 da biet (loi 1205),
    va chay SAU luot khoa tai khoan 00:30.
  * 01:10 ngay 1 hang thang - `monthly_snapshot`: chot so lieu THANG TRUOC vao EC Asset Monthly
    (tung may; chay lai chi chot may con thieu; khoa duy nhat (month, asset) o DocType).

Ca hai idempotent, loi tung may ghi Error Log va di tiep (mot may loi khong giet ca lo).
"""
import frappe
from frappe.utils import add_days, getdate, nowdate

from ecentric_workspace.tai_san import access as A
from ecentric_workspace.tai_san import constants as C
from ecentric_workspace.tai_san import depreciation as D
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
    if done:
        R.notify_role(C.ROLE_MANAGER, "Thu hồi tự động (nghỉ việc %s): %s - kiểm tra máy trên /tai-san/luan-chuyen."
                      % (day, ", ".join(done)), "/" + C.ROUTE_MOVES)
    return {"day": str(day), "returned": len(done)}


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
