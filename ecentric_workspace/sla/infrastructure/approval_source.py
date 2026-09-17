# Copyright (c) 2026, eCentric and contributors
"""Nhom "Phan hoi phe duyet": doi chieu nguoc tu ho so duyet -> nghia vu SLA.

KHONG PHAI DUONG CHINH. Duong chinh la cac loi goi hook trong `transitions.py`,
chay dong bo ngay luc cap duyet mo va dong. Tep nay la LUOI DO: no quet lai va
va vao nhung cho hook da truot.

Hook truot that, va truot theo nhung cach khong ai thay:
  * may chu restart giua giao dich duyet don;
  * module SLA chua migrate xong tren mot bench (sla_port nuot im lang - co y);
  * mot loi bat ky ben trong module SLA (sla_port._safe nuot het de khong chan
    nguoi dang duyet don).
Ba truong hop tren deu ket thuc bang: don duyet xong, khong ai bi chan, va bang
diem thieu mot dong ma khong co gi bao. Mot he do luong thieu du lieu im lang
thi te hon mot he do luong khong chay.

CHI DOC ben Approval Center. Khong sua mot dong nao cua `EC Approval Request`,
`...Level`, `...Approver` hay `EC Approval Action`.

CHAY LAI BAO NHIEU LAN CUNG MOT KET QUA: khoa chong trung la
`APPROVAL_STEP:<user>:<doctype>:<ho so>:<cap>:<lan>`, va moi buoc deu doi chieu
trang thai hien tai truoc khi ghi.
"""
import frappe
from frappe.utils import add_days, getdate, now_datetime

from ecentric_workspace.sla.application import hooks as sla_hooks
from ecentric_workspace.sla.application import obligation_service as obl
from ecentric_workspace.sla.constants import (
    DT_OBLIGATION, STATUS_CANCELLED, STATUS_EXCLUDED, STATUS_OPEN,
    TYPE_APPROVAL_STEP,
)
from ecentric_workspace.sla.domain import approval_rules as ar

DT_REQUEST = "EC Approval Request"
DT_LEVEL = "EC Approval Request Level"
DT_APPROVER = "EC Approval Request Approver"
DT_ACTION = "EC Approval Action"

#: Ho so o trang thai nay thi moi nghia vu con mo cua no phai bien khoi phep tinh.
CANCELLED_STATUSES = ("Cancelled",)


def attempt_of(req_name):
    """Lan thu may ho so nay chay lai tu dau. Doc tu nhat ky, khong can cot moi.

    `Restarted` la hanh dong duoc ghi khi `resubmit(restart=True)` dua ho so ve
    cap 1. Dem so lan do la cach duy nhat suy ra `attempt` ma khong phai them
    mot cot vao mot DocType cua module khac.
    """
    try:
        n = frappe.db.count(DT_ACTION, {"approval_request": req_name,
                                        "action": "Restarted"})
    except Exception:
        frappe.log_error(title="sla.approval.attempt_of",
                         message=frappe.get_traceback())
        n = 0
    return ar.attempt_no(n)


def _requests(days, limit):
    cutoff = add_days(getdate(now_datetime()), -int(days or 14))
    try:
        return frappe.get_all(DT_REQUEST, filters={"modified": (">=", str(cutoff))},
                              fields=["name", "reference_doctype", "reference_name",
                                      "approval_status"],
                              order_by="modified desc",
                              limit_page_length=int(limit or 0) or 0)
    except Exception:
        frappe.log_error(title="sla.approval._requests", message=frappe.get_traceback())
        return []


def _levels(req_name):
    return frappe.get_all(DT_LEVEL, filters={"approval_request": req_name},
                          fields=["level_no", "level_status", "activated_at",
                                  "sla_policy"],
                          order_by="level_no asc", limit_page_length=0)


def _approvers(req_name, level_no):
    return frappe.get_all(DT_APPROVER,
                          filters={"approval_request": req_name, "level_no": level_no},
                          fields=["approver", "status", "decided_at"],
                          limit_page_length=0)


def _current(name):
    return frappe.db.get_value(DT_OBLIGATION, name, "status")


# --------------------------------------------------------------------------- #
# Dong bo
# --------------------------------------------------------------------------- #
def _new_report():
    r = {k: [] for k in ("mo", "dong", "loai_tru", "huy", "bo_qua",
                         "truoc_ngay_ap_dung", "khong_ro", "loi")}
    r.update({"ho_so": 0, "cap": 0, "dong_nguoi": 0})
    return r


def _sync_level(req, lv, attempt, report):
    for ap in _approvers(req["name"], lv["level_no"]):
        report["dong_nguoi"] += 1
        action, closed_at, reason = ar.reconcile_decision(
            lv["level_status"], ap["status"], ap.get("decided_at"))
        if action == ar.ACT_SKIP:
            report["bo_qua"].append("%s c%s %s (%s)" % (
                req["reference_name"], lv["level_no"], ap["approver"], reason))
            if reason and "không rõ" in reason:
                report["khong_ro"].append(reason)
            elif reason == ar.REASON_LEVEL_SKIPPED:
                # Cap bi bo qua SAU khi da kich hoat. Hom nay `_activate_level`
                # bo cap TRUOC khi dat `activated_at` nen truong hop nay khong
                # xay ra - nhung neu mot duong moi lam no xay ra thi nhung dong
                # da mo se nam nguyen `Open` va bi cham `Missed` cho mot cap ma
                # chinh he thong da bo. Don o day, khong doi phat hien ra sau.
                _exclude_existing(req, lv, ap["approver"], attempt,
                                  ar.REASON_LEVEL_SKIPPED, report)
            continue

        opened_at = lv["activated_at"]
        if obl.before_start(TYPE_APPROVAL_STEP, opened_at):
            report["truoc_ngay_ap_dung"].append("%s c%s" % (req["reference_name"],
                                                            lv["level_no"]))
            continue

        # MOT duong tao duy nhat: dung chinh ham ma hook dung, de tieu de, khoa
        # chong trung va chinh sach khong bao gio lech giua hai duong.
        names = sla_hooks.open_approval_step_obligations(
            request_doctype=req["reference_doctype"],
            request_name=req["reference_name"],
            level_no=lv["level_no"], approvers=[ap["approver"]],
            opened_at=opened_at, sla_policy_code=lv.get("sla_policy"),
            attempt=attempt)
        if not names:
            continue
        name = names[0]
        cur = _current(name)
        if cur is None or cur in (STATUS_EXCLUDED, STATUS_CANCELLED):
            # Da co ket luan cuoi cung roi thi khong dung vao: mot lan HR dieu
            # chinh bang tay se bi duong quet nay ghi de moi gio, va khong ai
            # hieu vi sao diem cu quay ve.
            continue

        if action == ar.ACT_OPEN:
            if cur == STATUS_OPEN:
                report["mo"].append("%s c%s %s" % (req["reference_name"],
                                                   lv["level_no"], ap["approver"]))
            continue
        if cur != STATUS_OPEN:
            continue          # da dong roi, dung mo lai
        if action == ar.ACT_CLOSE:
            if not closed_at:
                # KHONG DOAN. Lay `opened_at` lam moc dong thi `classify_close`
                # se thay dong truoc han va cham `Met` - mot moc bam khong ro bi
                # lang le bien thanh "dung han". Khong co du lieu thi phai hien
                # ra la khong co, khong duoc hien ra la hoan hao.
                report["khong_ro"].append("%s c%s %s: thiếu mốc quyết định" % (
                    req["reference_name"], lv["level_no"], ap["approver"]))
                continue
            st = obl.close_obligation(name, closed_at)
            if st:
                report["dong"].append("%s c%s %s -> %s" % (
                    req["reference_name"], lv["level_no"], ap["approver"], st))
        elif action == ar.ACT_EXCLUDE:
            # Moc loai tru la luc SU VIEC xay ra, khong phai luc job chay - neu
            # khong thi mot dong thang 9 se mang `closed_at` cua thang 10.
            if obl.exclude_obligation(name, reason, closed_at or opened_at):
                report["loai_tru"].append("%s c%s %s" % (
                    req["reference_name"], lv["level_no"], ap["approver"]))


def _exclude_existing(req, lv, user, attempt, reason, report):
    """Loai tru mot dong DA TON TAI, khong tao moi."""
    try:
        name = frappe.db.get_value(DT_OBLIGATION, {
            "obligation_type": TYPE_APPROVAL_STEP,
            "source_doctype": req["reference_doctype"],
            "source_name": req["reference_name"],
            "source_detail": str(lv["level_no"]),
            "attempt": int(attempt or 1), "owner_user": user,
            "status": STATUS_OPEN}, "name")
        if name and obl.exclude_obligation(name, reason, lv.get("activated_at")):
            report["loai_tru"].append("%s c%s %s (cấp bị bỏ qua)" % (
                req["reference_name"], lv["level_no"], user))
    except Exception:
        frappe.log_error(title="sla.approval._exclude_existing",
                         message=frappe.get_traceback())


def _sync_request(req, report):
    if req.get("approval_status") in CANCELLED_STATUSES:
        n = obl.cancel_obligations_for_source(req["reference_doctype"],
                                              req["reference_name"])
        if n:
            report["huy"].append("%s (%s dòng)" % (req["reference_name"], n))
        return
    attempt = attempt_of(req["name"])
    for lv in _levels(req["name"]):
        # Chua kich hoat thi khong ai no gi. Cap bi danh Skipped tu luc nop cung
        # roi vao day (`activated_at` rong) - dung nhu `_activate_level` xu ly.
        if not lv.get("activated_at"):
            continue
        report["cap"] += 1
        _sync_level(req, lv, attempt, report)


#: Commit sau moi ngan nay ho so. Khong co no thi ca vong quet nam trong MOT
#: giao dich, giu khoa ghi tren bang nghia vu hang phut - trong khi hook dong bo
#: cung ghi vao dung bang do, BEN TRONG giao dich duyet don cua nguoi dung. Mot
#: lan deadlock o do khong chi lam mat mot dong SLA: no rollback ca giao dich
#: duyet, va nguoi dung thay "Da duyet" trong khi ho so khong doi trang thai.
COMMIT_EVERY = 50


def sync(days=14, limit=None):
    """Quet cac ho so duyet vua doi trong `days` ngay va va vao cho hook truot."""
    report = _new_report()
    reqs = _requests(days, limit)
    report["ho_so"] = len(reqs)
    report["tu_ngay"] = str(add_days(getdate(now_datetime()), -int(days or 14)))
    for i, req in enumerate(reqs):
        if not req.get("reference_doctype") or not req.get("reference_name"):
            continue
        if i and i % COMMIT_EVERY == 0:
            try:
                frappe.db.commit()
            except Exception:
                pass
        sp = "sla_appr"
        try:
            frappe.db.savepoint(sp)
        except Exception:
            sp = None
        try:
            _sync_request(req, report)
        except Exception:
            # MOI HO SO MOT DIEM LUU. Khong co no thi mot ho so hong keo theo:
            # giao dich bi huy bo, moi ho so sau do cung hong, va den luot
            # `log_error` cung nem loi vi giao dich da chet.
            if sp:
                try:
                    frappe.db.rollback(save_point=sp)
                except Exception:
                    pass
            report["loi"].append(req.get("name"))
            frappe.log_error(title="sla.approval.sync %s" % req.get("name"),
                             message=frappe.get_traceback())
    return report


def backfill(start="2026-09-21", limit=None):
    """Dung lai tu moc ap dung cua nhom nay. `days` suy ra tu `start`."""
    days = (getdate(now_datetime()) - getdate(start)).days + 1
    return sync(days=max(days, 1), limit=limit)


# --------------------------------------------------------------------------- #
# Do phu
# --------------------------------------------------------------------------- #
def coverage(days=14):
    """Cap duyet nao DA KICH HOAT ma khong co mot nghia vu nao.

    Day la phep kiem chinh HOOK, khong phai kiem nguoi duyet: khac 0 nghia la co
    mot duong kich hoat cap nao do chua goi sang SLA.

    SO THEO TUNG CAP, khong dem theo ho so. Dem theo ho so thi mot ho so co cap 1
    duoc cam hook dung va cap 3 bi truot van ra "co nghia vu" - va chi so nay se
    luon bang 0, cho mot cam giac an toan sai.

    Cap kich hoat TRUOC ngay ap dung cua nhom khong duoc tinh la thieu: khong co
    nghia vu cho chung la dung, khong phai loi.
    """
    out = {"ho_so": 0, "cap": 0, "thieu": [], "tu_ngay": None}
    reqs = _requests(days, None)
    out["ho_so"] = len(reqs)
    out["tu_ngay"] = str(add_days(getdate(now_datetime()), -int(days or 14)))
    for req in reqs:
        if not req.get("reference_name"):
            continue
        try:
            attempt = attempt_of(req["name"])
            activated = set()
            for lv in _levels(req["name"]):
                if not lv.get("activated_at"):
                    continue
                if obl.before_start(TYPE_APPROVAL_STEP, lv["activated_at"]):
                    continue
                activated.add(str(lv["level_no"]))
            if not activated:
                continue
            out["cap"] += len(activated)
            have = set(frappe.get_all(DT_OBLIGATION, filters={
                "obligation_type": TYPE_APPROVAL_STEP,
                "source_doctype": req["reference_doctype"],
                "source_name": req["reference_name"],
                "attempt": attempt}, pluck="source_detail", limit_page_length=0))
            for lvl in sorted(activated - have):
                out["thieu"].append("%s %s cấp %s" % (req["reference_doctype"],
                                                      req["reference_name"], lvl))
        except Exception:
            frappe.log_error(title="sla.approval.coverage",
                             message=frappe.get_traceback())
    return out


def open_count():
    return frappe.db.count(DT_OBLIGATION, {"obligation_type": TYPE_APPROVAL_STEP,
                                           "status": STATUS_OPEN})
