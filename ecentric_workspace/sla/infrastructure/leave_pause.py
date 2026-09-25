# Copyright (c) 2026, eCentric and contributors
"""Nghi phep da duyet DUNG DONG HO cua nhung dau viec phe duyet.

VI SAO TEP NAY TON TAI. Ngay 21/09 - dung ngay dau tien nhom "Phan hoi phe duyet"
bat dau tinh diem - mot nguoi nghi phep nam da duoc duyet van bi mo 24 dau viec,
han tinh bang gio lam viec y nhu mot ngay di lam:

    mo 21/09 11:20  ->  han 21/09 16:20   (nguoi do dang nghi phep)

Bay dau viec co han roi TRON vao ngay nghi, va ca bay deu bi cham Tre hoac Chua
lam. Them mot so dau viec mo chieu 21/09, dong ho chay suot ngay nghi roi dao han
09:10-09:48 sang 22/09 - trong khi nguoi do cham cong luc 09:22. Co viec het han
truoc khi ho kip mo may.

Nguyen nhan: KHONG he nao biet toi nghi phep ca nhan. `business_hours.py` cua
Approval Center chi biet gio hanh chinh va ngay le CHUNG cua cong ty. Con ben
SLA thi nhom Cham cong co `_leave_days`, nhom Phe duyet thi khong co gi.

Trong khi trang /sla hua nguoc lai, o muc "Khi nao ban KHONG bi cham":
    "Nghi phep da duyet - ngay do van hien tren bang nhung khong tinh diem."

DUNG DONG HO, KHONG LOAI TRU. Chu so huu chot 22/09. Loai tru se mien ca phan
thoi gian ho CO mat: mot ho so mo sang thu Sau, han chieu thu Sau, ma nguoi do
nghi nua ngay - loai tru la cho khong ca buoi sang ho van ngoi day. Dung dong ho
thi viec van phai lam, chi la khong dem nhung gio ho khong co mat. Day cung la
cach "yeu cau bo sung" da chay san, va `classify_close` da ghi san trong docstring
rang `paused_seconds` gom "nghi phep da duyet" - thiet ke co tu dau, chua ai cam
vao.

MOI NGAY NGHI MOT DOAN, KEO TOI DAU NGAY LAM VIEC KE TIEP. Nghe thi thua, nhung
no tu ghep dung:
  - nghi thu Hai  -> doan [T2 00:00, T3 00:00) = 24h  -> han doi tu T2 16:20 sang T3 16:20
  - nghi thu Sau  -> doan [T6 00:00, T2 00:00) = 72h  -> han sang T2, khong roi vao T7
  - nghi T5 va T6 -> doan1 [T5,T6) + doan2 [T6,T2) = 24h + 72h, KHONG chong nhau
Chi tao doan cho NGAY LAM VIEC. Cuoi tuan va ngay le thi han von da khong chay
qua, tinh them la cho khong hai lan.
"""
import datetime

import frappe
from frappe.utils import add_days, getdate, nowdate

from ecentric_workspace.sla.application import obligation_service as obl
from ecentric_workspace.sla.constants import (
    DT_OBLIGATION, DT_PAUSE, PAUSE_ABSENCE, STATUS_CANCELLED, STATUS_LATE,
    STATUS_MET, TYPE_APPROVAL_STEP,
)
from ecentric_workspace.sla.domain import scoring

_FIELDS = ["name", "owner_user", "opened_at", "due_at", "closed_at", "status",
           "paused_seconds", "policy_snapshot"]

#: Tran an toan khi di tim ngay lam viec ke tiep. Mot lich nghi cau hinh sai co
#: the lam moi ngay deu la ngay nghi; khong co tran thi vong lap chay mai.
_MAX_SKIP = 30


def _new_report():
    return {"quet": 0, "nguoi": 0, "doan_moi": [], "doi_trang_thai": [],
            "khong_doc_duoc_nhan_su": [], "loi": []}


def _employees_of(users):
    """user_id -> {name, holiday_list, company}. Khong co ho so thi bo qua."""
    if not users:
        return {}
    rows = frappe.get_all(
        "Employee", filters={"user_id": ("in", list(users))},
        fields=["name", "user_id", "holiday_list", "company"],
        limit_page_length=0)
    return {r["user_id"]: r for r in rows}


def _next_work_start(day, holidays):
    """00:00 cua NGAY LAM VIEC dau tien sau `day`."""
    d = day + datetime.timedelta(days=1)
    for _ in range(_MAX_SKIP):
        if d.weekday() < 5 and d not in holidays:
            break
        d += datetime.timedelta(days=1)
    return datetime.datetime(d.year, d.month, d.day)


def _span_days(opened_at, due_at):
    """Cac ngay ma dong ho cua dau viec nay chay qua."""
    a, b = getdate(opened_at), getdate(due_at)
    if b < a:
        a, b = b, a
    out, d = [], a
    for _ in range(400):
        out.append(d)
        if d >= b:
            break
        d += datetime.timedelta(days=1)
    return out


def _has_segment(obligation, from_dt):
    return bool(frappe.get_all(DT_PAUSE, filters={
        "obligation": obligation, "reason": PAUSE_ABSENCE, "from_dt": from_dt,
    }, pluck="name", limit_page_length=1))


def _reclassify(row, report):
    """Dau viec DA DONG thi `status` da duoc chot luc dong - phai cham lai.

    Day la duong hoi to, doi xung voi `_ensure_excluded` cua nhom Cham cong: mot
    phieu nghi duyet muon phai go duoc vet tre da cham hom truoc. Khong co buoc
    nay thi doan tam dung vua cam vao chi co tac dung voi nhung dau viec con mo,
    con bay dong da bi cham Tre thi nam nguyen - tuc la sua luat ma khong sua
    hau qua.

    `_elapsed_fn_for` la ham rieng cua `obligation_service`, va dung no la CO Y:
    do "tre bao lau" phai dung cung mot thuoc do voi luc dong. Viet mot phep do
    thu hai o day la tao ra hai dinh nghia "tre".
    """
    if row["status"] not in (STATUS_MET, STATUS_LATE):
        return None
    if not row.get("closed_at") or not row.get("due_at"):
        return None
    paused = frappe.db.get_value(DT_OBLIGATION, row["name"], "paused_seconds")
    status, late = scoring.classify_close(
        row["due_at"], row["closed_at"], paused or 0,
        elapsed_fn=obl._elapsed_fn_for(row))
    if status == row["status"]:
        return None
    frappe.db.set_value(DT_OBLIGATION, row["name"],
                        {"status": status, "late_seconds": late},
                        update_modified=False)
    report["doi_trang_thai"].append("%s %s -> %s" % (row["name"], row["status"], status))
    return status


def _sync_one(row, leave_days, holidays, report):
    """Cam doan tam dung cho MOT dau viec. Tra ve so doan vua them."""
    if not row.get("due_at") or not row.get("opened_at"):
        return 0
    added = 0
    for d in _span_days(row["opened_at"], row["due_at"]):
        if d not in leave_days:
            continue
        # Cuoi tuan / ngay le: han von da khong chay qua nhung ngay nay, cong
        # them mot doan tam dung nua la cho khong hai lan.
        if d.weekday() >= 5 or d in holidays:
            continue
        frm = datetime.datetime(d.year, d.month, d.day)
        if _has_segment(row["name"], frm):
            continue
        obl.start_pause(row["name"], PAUSE_ABSENCE, frm,
                        notes="Nghỉ phép đã duyệt %s" % d)
        obl.end_pause(row["name"], PAUSE_ABSENCE, _next_work_start(d, holidays))
        report["doan_moi"].append("%s %s" % (row["name"], d))
        added += 1
    return added


def sync(days=14, limit=5000):
    """Quet cac dau viec phe duyet gan day, cam doan tam dung cho ngay nghi phep.

    Chay lai duoc: moi doan co khoa (dau viec, ly do, from_dt) va duoc kiem
    truoc khi chen; `_recompute_paused` cong lai TU DAU nen chay hai lan khong
    day han ra xa them.
    """
    report = _new_report()
    since = str(add_days(getdate(nowdate()), -int(days or 14)))
    try:
        rows = frappe.get_all(DT_OBLIGATION, filters={
            "obligation_type": TYPE_APPROVAL_STEP,
            "status": ("!=", STATUS_CANCELLED),
            "opened_at": (">=", since + " 00:00:00"),
        }, fields=_FIELDS, order_by="opened_at asc", limit_page_length=int(limit or 5000))
    except Exception:
        frappe.log_error(title="sla.leave_pause.sync", message=frappe.get_traceback())
        report["loi"].append("doc danh sach that bai")
        return report

    report["quet"] = len(rows)
    by_user = {}
    for r in rows:
        by_user.setdefault(r["owner_user"], []).append(r)
    report["nguoi"] = len(by_user)

    emps = _employees_of(by_user.keys())
    hl_cache = {}
    from ecentric_workspace.sla.infrastructure import attendance_source as att

    for user, urows in by_user.items():
        emp = emps.get(user)
        if not emp:
            # Khong co ho so nhan su thi khong tra duoc nghi phep. Dem rieng
            # thay vi bo qua im lang - do la mot lo hong du lieu cua HR, va no
            # lam nguoi do khong bao gio duoc dung dong ho.
            report["khong_doc_duoc_nhan_su"].append(user)
            continue
        sp = "sla_leave"
        try:
            frappe.db.savepoint(sp)
        except Exception:
            sp = None
        try:
            lo = min(getdate(r["opened_at"]) for r in urows)
            hi = max(getdate(r["due_at"] or r["opened_at"]) for r in urows)
            leave = att._leave_days(emp["name"], lo, hi)
            if not leave:
                continue
            holidays = att._holidays_for(emp, hl_cache)
            for r in urows:
                if _sync_one(r, leave, holidays, report):
                    _reclassify(r, report)
        except Exception:
            if sp:
                try:
                    frappe.db.rollback(save_point=sp)
                except Exception:
                    pass
            report["loi"].append(user)
            frappe.log_error(title="sla.leave_pause %s" % user,
                             message=frappe.get_traceback())
    return report


def preview(days=14, limit=5000):
    """Chay thu: dem xem se cam bao nhieu doan, KHONG ghi gi."""
    report = _new_report()
    since = str(add_days(getdate(nowdate()), -int(days or 14)))
    rows = frappe.get_all(DT_OBLIGATION, filters={
        "obligation_type": TYPE_APPROVAL_STEP,
        "status": ("!=", STATUS_CANCELLED),
        "opened_at": (">=", since + " 00:00:00"),
    }, fields=_FIELDS, order_by="opened_at asc", limit_page_length=int(limit or 5000))
    report["quet"] = len(rows)
    by_user = {}
    for r in rows:
        by_user.setdefault(r["owner_user"], []).append(r)
    report["nguoi"] = len(by_user)
    emps = _employees_of(by_user.keys())
    hl_cache = {}
    from ecentric_workspace.sla.infrastructure import attendance_source as att
    for user, urows in by_user.items():
        emp = emps.get(user)
        if not emp:
            report["khong_doc_duoc_nhan_su"].append(user)
            continue
        lo = min(getdate(r["opened_at"]) for r in urows)
        hi = max(getdate(r["due_at"] or r["opened_at"]) for r in urows)
        leave = att._leave_days(emp["name"], lo, hi)
        if not leave:
            continue
        holidays = att._holidays_for(emp, hl_cache)
        for r in urows:
            for d in _span_days(r["opened_at"], r["due_at"]):
                if d in leave and d.weekday() < 5 and d not in holidays \
                        and not _has_segment(r["name"], datetime.datetime(d.year, d.month, d.day)):
                    report["doan_moi"].append("%s %s (%s)" % (r["name"], d, r["status"]))
    return report
# --------------------------------------------------------------------------- #
# DUNG CHUNG - cho module khac doc ngay nghi ma khong phai viet lai luat
# --------------------------------------------------------------------------- #
#
# Approval Center can biet "hom do nguoi duyet co nghi khong" de dan nhan cho
# dung. Neu ho tu viet lai, se co HAI dinh nghia "ngay nghi" trong cung mot he
# thong, va chung se troi ra xa nhau - cai nay sua, cai kia quen.
#
# CO Y KHONG LAM THANH ENDPOINT - khong dat decorator cong khai o day. Ben goi
# (`query_service` cua Approval Center) chay o server; ho goi thang ham Python
# nay duoc. Mo mot endpoint se day ngay nghi ca nhan cua moi nguoi ra truoc
# trinh duyet, trong khi khong ai can den no o do.
#
# "NGAY LAM VIEC" LA PHAN QUAN TRONG. Ham nay chi tra ve nhung ngay nghi ma dong
# ho VON DANG CHAY: cuoi tuan va ngay le bi loai ra. Nghi thu Bay thi han khong
# he chay qua do, nen dan "nguoi duyet nghi phep" vao mot ho so qua han hom thu
# Bay la giai thich sai nguyen nhan.


def working_leave_days(users, start, end):
    """Ngay nghi phep DA DUYET **va la ngay lam viec**, theo tung nguoi.

    `users`: mot user_id hoac danh sach user_id (khong phai ma nhan vien).
    Tra ve `{user_id: [datetime.date, ...]}` da sap xep, luon co du moi key
    duoc hoi - nguoi khong co ho so nhan su hay khong nghi ngay nao thi la
    danh sach rong.

    KHONG NEM LOI. Ben goi la mot cai nhan tren man hinh; tra loi khong duoc
    thi nhan hien nhu cu, chu khong duoc lam vo ca trang duyet don.
    """
    if isinstance(users, str):
        users = [users]
    users = [u for u in (users or []) if u]
    out = {}
    for u in users:
        out[u] = []
    if not users:
        return out

    lo, hi = getdate(start), getdate(end)
    if hi < lo:
        lo, hi = hi, lo

    try:
        emps = _employees_of(users)
    except Exception:
        frappe.log_error(title="sla.leave_pause.working_leave_days",
                         message=frappe.get_traceback())
        return out

    hl_cache = {}
    from ecentric_workspace.sla.infrastructure import attendance_source as att
    for u in users:
        emp = emps.get(u)
        if not emp:
            continue
        try:
            leave = att._leave_days(emp["name"], lo, hi)
            if not leave:
                continue
            holidays = att._holidays_for(emp, hl_cache)
            out[u] = sorted(d for d in leave
                            if d.weekday() < 5 and d not in holidays)
        except Exception:
            frappe.log_error(title="sla.leave_pause.working_leave_days %s" % u,
                             message=frappe.get_traceback())
    return out


def is_on_leave(user, day):
    """Mot cau hoi, mot ngay. Tien cho cho chi can dan nhan mot dong."""
    if not user or not day:
        return False
    d = getdate(day)
    return d in set(working_leave_days(user, d, d).get(user) or ())
