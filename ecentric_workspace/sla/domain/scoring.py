# Copyright (c) 2026, eCentric and contributors
"""Cham diem mot nghia vu va gop thanh ti le. Thuan - khong import frappe.

Cong thuc da chot voi chu so huu (16/09):

    moi RSVP, moi ngay cong, moi buoc phe duyet = MOT dau viec, can bang nhau
    %SLA thang = tong dau viec dung han / tong dau viec duoc cham diem

Hai quyet dinh trong file nay quan trong hon phan con lai, va ca hai deu la ve
MAU SO chu khong phai tu so:

1. `Open` + da qua han VAN VAO MAU SO (`is_breached`). Neu chi dem viec da dong
   thi cach de nhat de dat 100%% la khong bao gio dong viec - tre vo han bien
   thanh khong co du lieu, va khong co du lieu hien ra la hoan hao. Day khong
   phai gia dinh: %SLA cu trong Power BI co mot nhanh thang 8/2026 dem moi dong
   check-in la dung han bat ke thuc te, va khong ai doc dashboard nhin thay dieu
   do. Ti le phai tu bao ve truoc chinh no.

2. Mau so QUA NHO thi khong ra ti le. `rate` tra ve None khi so dau viec duoc
   cham diem duoi nguong. Mot nguoi co 1 dau viec lam dung se hien 100%% va dung
   tren nguoi co 80 dau viec dung 78 - do khong phai xep hang, do la nhieu.
   None buoc tang tren phai hien "chưa đủ mẫu" thay vi mot con so.

`Excluded` va `Cancelled` khong vao tu so lan mau so, nhung VAN duoc dem rieng
va van phai hien len bang diem. Mot cot "khong tinh điểm" bang 40%% cua thang la
mot tin tuc, khong phai mot chi tiet ky thuat.
"""
from datetime import datetime, timedelta

from ecentric_workspace.sla.constants import (
    ALL_GROUPS, DEFAULT_MIN_SAMPLE, GROUP_COUNTS_TOWARD_SLA, GROUP_MIN_SAMPLE,
    OVERALL_MIN_SAMPLE, STATUS_CANCELLED, STATUS_EXCLUDED, STATUS_LATE,
    STATUS_MET, STATUS_MISSED, STATUS_OPEN,
)


def _as_naive(dt):
    if dt is None:
        return None
    if isinstance(dt, str):
        dt = datetime.fromisoformat(dt.replace("Z", ""))
    if isinstance(dt, datetime) and dt.tzinfo is not None:
        dt = dt.replace(tzinfo=None)
    return dt


# --------------------------------------------------------------------------- #
# Cham diem MOT nghia vu
# --------------------------------------------------------------------------- #
def classify_close(due_at, closed_at, paused_seconds=0, elapsed_fn=None):
    """Nguoi do da DONG viec. Dung han hay tre?

    Tra ve (status, late_seconds). `paused_seconds` la tong thoi gian dong ho bi
    dung (nghi phep da duyet, cho bo sung thong tin) - no day han lui ra, khong
    xoa nghia vu.

    KHONG CO HAN -> `Excluded`, KHONG phai `Met`. Day la sua mot lo hong nghiem
    trong: hien tai 57/60 buoc duyet chua ai cau hinh SLA. Neu "khong co han" =
    "dung han" thi ngay hom bat he thong len, nhom Phan hoi phe duyet se hien
    100% cho tat ca moi nguoi - mot con so dep, sai, va khong ai co ly do de
    nghi ngo. Loai tru thi no hien ra o cot "khong tinh diem" va tro thanh viec
    phai lam, dung nhu no la.

    `elapsed_fn(from_dt, to_dt) -> giay` do do TRE bang cung thuoc do voi HAN.
    Voi chinh sach gio lam viec, tre phai tinh bang gio lam viec: dong luc 9h
    thu Hai cho mot han 17h thu Sau la tre 30 phut lam viec, khong phai 64 gio.
    Khong truyen thi do bang dong ho (dung cho chinh sach gio dong ho).
    """
    due_at, closed_at = _as_naive(due_at), _as_naive(closed_at)
    if closed_at is None:
        raise ValueError("classify_close yeu cau closed_at")
    if due_at is None:
        return STATUS_EXCLUDED, 0
    effective_due = due_at + timedelta(seconds=int(paused_seconds or 0))
    if closed_at <= effective_due:
        return STATUS_MET, 0
    if elapsed_fn:
        late = int(elapsed_fn(effective_due, closed_at) or 0)
    else:
        late = int((closed_at - effective_due).total_seconds())
    return STATUS_LATE, late


def is_breached(status, due_at, now, paused_seconds=0):
    """Nghia vu con MO va da qua han -> phai vao mau so ngay, khong doi dong.

    Day la cai chan cua lo hong "khong dong thi khong bi tru". Xem ghi chu dau file.
    """
    if status != STATUS_OPEN:
        return False
    due_at, now = _as_naive(due_at), _as_naive(now)
    if due_at is None or now is None:
        return False
    return now > due_at + timedelta(seconds=int(paused_seconds or 0))


def effective_status(row, now):
    """Trang thai DUNG DE CHAM DIEM cua mot dong nghia vu.

    Khac voi cot `status` trong DB o dung mot diem: mot dong `Open` da qua han
    duoc cham nhu `Missed`. Khong ghi nguoc vao DB o day - viec ghi la cua
    `obligation_service.sweep_overdue`. Ham nay chi doc, de bang diem luon dung
    ke ca khi sweep chua chay.
    """
    status = row.get("status")
    if status == STATUS_OPEN and is_breached(status, row.get("due_at"), now,
                                             row.get("paused_seconds") or 0):
        return STATUS_MISSED
    return status


# --------------------------------------------------------------------------- #
# Gop
# --------------------------------------------------------------------------- #
def _empty_bucket():
    return {"ontime": 0, "late": 0, "missed": 0, "excluded": 0, "cancelled": 0,
            "open": 0, "no_policy": 0, "unknown": 0,
            "scored": 0, "rate": None, "enough_sample": False}


def _tally(bucket, status, has_due=True):
    if status == STATUS_MET:
        bucket["ontime"] += 1
        bucket["scored"] += 1
    elif status == STATUS_LATE:
        bucket["late"] += 1
        bucket["scored"] += 1
    elif status == STATUS_MISSED:
        bucket["missed"] += 1
        bucket["scored"] += 1
    elif status == STATUS_EXCLUDED:
        bucket["excluded"] += 1
    elif status == STATUS_CANCELLED:
        bucket["cancelled"] += 1
    elif status == STATUS_OPEN:
        bucket["open"] += 1
    else:
        # Mot chuoi khong nam trong sau trang thai. Moi buoc chuyen sau khi tao
        # deu di qua `frappe.db.set_value`, von BO QUA validate cua controller -
        # nen mot lan import du lieu hoac mot script cu co the ghi vao day. Dem
        # rieng thay vi bo qua: mot dong bien mat khoi ca tu so lan mau so la
        # dung kieu mat mat khong ai nhin thay.
        bucket["unknown"] += 1
    if not has_due:
        bucket["no_policy"] += 1


def _finalize(bucket, min_sample):
    bucket["enough_sample"] = bucket["scored"] >= int(min_sample or 0)
    if bucket["scored"] and bucket["enough_sample"]:
        bucket["rate"] = round(bucket["ontime"] * 100.0 / bucket["scored"], 1)
    else:
        bucket["rate"] = None
    return bucket


def aggregate(rows, now=None, min_sample_by_group=None):
    """rows = [{group_key, status, due_at, paused_seconds}] -> bang diem.

    Tra ve {"groups": {group_key: bucket}, "overall": bucket}.

    `overall` chi gop cac nhom co `counts_toward_sla=1`. Nhom `task` van xuat
    hien trong `groups` voi ti le day du cua no - do la yeu cau ro rang cua chu
    so huu: van do, khong tinh diem.
    """
    now = _as_naive(now) or datetime.now()
    min_sample_by_group = min_sample_by_group or GROUP_MIN_SAMPLE

    groups = {g: _empty_bucket() for g in ALL_GROUPS}
    overall = _empty_bucket()

    for row in rows:
        g = row.get("group_key")
        if g not in groups:
            # Nhom la nhung gi DB tra ve, khong phai nhung gi ta mong doi. Mot
            # loai nghia vu moi them sau nay khong duoc lam vo bang diem.
            groups[g] = _empty_bucket()
        st = effective_status(row, now)
        has_due = row.get("due_at") is not None
        _tally(groups[g], st, has_due)
        # Doc co CUA TUNG DONG truoc, hang so chi la du phong cho du lieu cu.
        # Neu doc hang so thi doi quy tac hom nay se viet lai ti le cua moi thang
        # da qua ngay lan tai trang tiep theo - mot bang diem da cong bo tu doi
        # sau lung nguoi doc thi khong con la ban ghi.
        counts = row.get("counts_toward_sla")
        if counts is None:
            counts = GROUP_COUNTS_TOWARD_SLA.get(g, 1)
        if int(counts or 0):
            _tally(overall, st, has_due)

    for g, bucket in groups.items():
        _finalize(bucket, min_sample_by_group.get(g, DEFAULT_MIN_SAMPLE))

    _finalize(overall, OVERALL_MIN_SAMPLE)
    return {"groups": groups, "overall": overall}


def contribution(groups):
    """Ti le xx%% la do dau? Tra ve danh sach nhom da sap theo so dau viec HONG
    (late + missed) giam dan.

    Day la cau hoi chu so huu hoi bang dung chu cua ong ay - "break ra tỉ lệ xx%%
    là do đâu". Tra loi bang so dau viec hong, khong bang ti le nhom: mot nhom
    50%% tren 4 dau viec lam hong it hon mot nhom 90%% tren 200 dau viec.
    """
    out = []
    for g, b in groups.items():
        if not GROUP_COUNTS_TOWARD_SLA.get(g, 1):
            continue
        fails = b["late"] + b["missed"]
        if fails:
            out.append({"group_key": g, "fails": fails, "late": b["late"],
                        "missed": b["missed"], "scored": b["scored"],
                        "rate": b["rate"]})
    out.sort(key=lambda r: (-r["fails"], r["group_key"]))
    total = sum(r["fails"] for r in out)
    for r in out:
        r["share"] = round(r["fails"] * 100.0 / total, 1) if total else 0.0
    return out
