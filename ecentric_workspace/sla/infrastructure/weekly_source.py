# Copyright (c) 2026, eCentric and contributors
"""Nhom "Bao cao tuan": doc `Weekly Team Update` -> nghia vu SLA.

KHONG SUA MOT DONG NAO TRONG `weekly_report`. Day la quyet dinh thiet ke chinh
cua tep nay, va no khong phai vi than trong chung chung:

  * `Weekly Team Update` DA la mot nghia vu day du. No co `due_at` (tinh tu
    `Department Reporting Window`), co `obligation_key` duy nhat
    (`employee::week_label`), co `submitted_at`, co trang thai ket thuc. Khong
    con gi de them - chi con viec DOC.
  * Cam hook vao `ensure_weekly_obligation` / `close_weekly_obligation` se buoc
    module bao cao tuan phu thuoc vao module SLA. Doc mot chieu thi khong.
  * Va quan trong nhat: doc duoc thi BU NGUOC duoc. Cac tuan da qua van con
    nguyen trong DB voi ca han lan moc nop, nen `backfill()` dung ra duoc bang
    diem THAT cua nhieu thang truoc ngay lap tuc - khong phai doi bon tuan moi
    biet engine cham diem co dung khong.

Doi lai la do tre: nghia vu duoc mo/dong theo chu ky job chu khong tuc thi. Voi
mot nghia vu tinh theo TUAN thi mot gio tre la khong dang ke.

Dong bo nay CHAY LAI DUOC bao nhieu lan cung ra mot ket qua: khoa chong trung la
`obligation_key` cua chinh WTU.
"""
import frappe
from frappe.utils import get_datetime

from ecentric_workspace.sla.application import obligation_service as obl
from ecentric_workspace.sla.constants import (
    DT_OBLIGATION, STATUS_OPEN, TYPE_WEEKLY_REPORT,
)
from ecentric_workspace.sla.domain import weekly_rules

WTU = "Weekly Team Update"
TERMINAL_STATES = weekly_rules.TERMINAL_STATES

# Chinh sach cho nhom nay: han do CHINH WTU mang theo, module SLA khong tinh lai.
# Tinh lai se tao ra kha nang hai con han khac nhau cho cung mot ban bao cao.
POLICY_CODE = "SLA-WR-EXPLICIT"

_FIELDS = ["name", "submitter", "week_label", "due_at", "status",
           "obligation_key", "submitted_at", "creation", "modified"]


def _rows(filters, limit):
    return frappe.get_all(WTU, filters=filters, fields=_FIELDS,
                          order_by="due_at asc", limit_page_length=limit)


def sync_row(row, report):
    """Mot WTU -> mot nghia vu. Tra ve 'opened' | 'closed' | 'skipped'."""
    action, closed_at, reason = weekly_rules.decide(row)
    if action == weekly_rules.ACT_SKIP:
        # Dem rieng thay vi bo qua im lang: day chinh la dau hieu phong ban do
        # thieu `Department Reporting Window`, mot lo hong lam nguoi ta bien mat
        # khoi bang diem.
        report["khong_han"].append("%s (%s)" % (row.get("name"), reason))
        return "skipped"

    if obl.before_start(TYPE_WEEKLY_REPORT, row.get("creation")):
        # Truoc ngay bat dau ap dung (chot 17/09: nhom nay tinh tu 21/09).
        # Dem RIENG, khong gop vao "khong mo duoc": mot bang bao cao binh thuong
        # khong duoc trong giong nhu mot dong loi.
        report["truoc_ngay_ap_dung"].append(row.get("name"))
        return "skipped"

    name = obl.open_obligation(
        type_code=TYPE_WEEKLY_REPORT,
        owner_user=row["submitter"],
        source_doctype=WTU,
        source_name=row["name"],
        source_detail=row.get("week_label"),
        opened_at=row.get("creation"),
        title="Báo cáo tuần %s" % (row.get("week_label") or ""),
        policy_code=POLICY_CODE,
        explicit_due=row["due_at"],
    )
    if not name:
        report["khong_mo_duoc"].append(row["name"])
        return "skipped"

    if action == weekly_rules.ACT_CLOSE:
        st = obl.close_obligation(name, get_datetime(closed_at) if closed_at else None)
        if st:
            report["dong"].append("%s -> %s" % (row["name"], st))
            return "closed"
        report["da_dong_tu_truoc"].append(row["name"])
        return "skipped"

    report["mo"].append(row["name"])
    return "opened"


def _new_report():
    return {k: [] for k in ("mo", "dong", "da_dong_tu_truoc", "khong_han",
                            "truoc_ngay_ap_dung", "khong_mo_duoc", "loi")}


def sync(since=None, limit=2000):
    """Dong bo cac ban bao cao gan day. Dung cho job dinh ky.

    `since` mac dinh 60 ngay: du de bat moi ban bao cao con mo va moi ban vua
    duoc nop, ma khong quet lai ca lich su moi gio.
    """
    since = since or frappe.utils.add_days(frappe.utils.nowdate(), -60)
    report = _new_report()
    try:
        rows = _rows({"due_at": (">=", since)}, limit)
    except Exception:
        frappe.log_error(title="sla.weekly_source.sync", message=frappe.get_traceback())
        return report
    for row in rows:
        sp = "sla_wr"
        try:
            frappe.db.savepoint(sp)
        except Exception:
            sp = None
        try:
            sync_row(row, report)
        except Exception:
            if sp:
                try:
                    frappe.db.rollback(save_point=sp)
                except Exception:
                    pass
            report["loi"].append(row.get("name"))
            frappe.log_error(title="sla.weekly_source %s" % row.get("name"),
                             message=frappe.get_traceback())
    report["quet"] = len(rows)
    return report


def backfill(weeks=26, limit=20000):
    """Dung lai nghia vu cho cac tuan DA QUA tu du lieu co san.

    Day la duong ngan nhat de biet engine cham diem co dung khong: thay vi doi
    bon tuan cho du lieu moi, doi chieu ngay voi nhung tuan da co nguoi nop dung
    han va nguoi nop muon. Neu bang diem sinh ra khong khop voi thuc te thi sai
    lech lo ra truoc khi bat ky ai bi cham diem that.
    """
    since = frappe.utils.add_days(frappe.utils.nowdate(), -7 * int(weeks or 1))
    return sync(since=since, limit=limit)


# --------------------------------------------------------------------------- #
# Do phu
# --------------------------------------------------------------------------- #
def coverage(period=None):
    """Ai KHONG co nghia vu bao cao tuan nao trong ky?

    Cau hoi nay quan trong ngang voi "ai tre". Mot nguoi khong co nghia vu nao
    se hien 0 dau viec - va mot mau so bang 0 trong nhieu he thong se hien ra la
    100%. O day thi khong (`rate=None`), nhung danh sach duoi day moi la thu noi
    ro TAI SAO: gan nhu luon la phong ban do chua co `Department Reporting
    Window`, chu khong phai nguoi do duoc mien.
    """
    from ecentric_workspace.sla.application.scoreboard_service import current_period
    period = period or current_period()
    out = {"period": period, "co_nghia_vu": [], "khong_co_nghia_vu": []}
    try:
        emps = frappe.get_all("Employee", filters={"status": "Active",
                                                   "user_id": ("is", "set")},
                              fields=["user_id", "department"], limit_page_length=0)
        having = set(frappe.get_all(DT_OBLIGATION, filters={
            "period_month": period, "obligation_type": TYPE_WEEKLY_REPORT},
            pluck="owner_user", limit_page_length=0))
    except Exception:
        frappe.log_error(title="sla.weekly_source.coverage",
                         message=frappe.get_traceback())
        return out
    for e in emps:
        entry = "%s (%s)" % (e["user_id"], e.get("department") or "không phòng ban")
        (out["co_nghia_vu"] if e["user_id"] in having
         else out["khong_co_nghia_vu"]).append(entry)
    return out


def open_count():
    return frappe.db.count(DT_OBLIGATION, {"obligation_type": TYPE_WEEKLY_REPORT,
                                           "status": STATUS_OPEN})


# --------------------------------------------------------------------------- #
# Chay kho
# --------------------------------------------------------------------------- #
def preview(weeks=26, limit=20000):
    """Engine SE cham diem the nao cho cac tuan da qua - KHONG GHI GI CA.

    Ton tai vi hai dieu dung nhau: chu so huu chot nhom bao cao tuan chi tinh tu
    21/09, nhung engine cham diem thi can duoc kiem chung bang du lieu THAT chu
    khong phai bang test. Neu bu nguoc that thi se tao ra nghia vu cho nhung tuan
    khong duoc phep cham diem; neu khong bu thi phai doi bon tuan moi biet engine
    dung hay sai.

    Ham nay go nut do: tinh tren chinh du lieu `Weekly Team Update` co san, tra
    ve con so, khong cham vao DB. Doi chieu ket qua voi thuc te la cach re nhat
    de biet cong thuc co dung khong TRUOC khi no cham diem ai.
    """
    from frappe.utils import get_datetime
    from ecentric_workspace.sla.domain import scoring

    since = frappe.utils.add_days(frappe.utils.nowdate(), -7 * int(weeks or 1))
    out = {"tu_ngay": since, "quet": 0, "dung_han": 0, "tre": 0, "chua_nop": 0,
           "khong_cham_duoc": 0, "theo_nguoi": {}}
    try:
        rows = _rows({"due_at": (">=", since)}, limit)
    except Exception:
        frappe.log_error(title="sla.weekly_source.preview",
                         message=frappe.get_traceback())
        return out

    now = frappe.utils.now_datetime()
    out["quet"] = len(rows)
    for row in rows:
        action, closed_at, _reason = weekly_rules.decide(row)
        who = row.get("submitter") or "(không rõ)"
        bucket = out["theo_nguoi"].setdefault(
            who, {"dung_han": 0, "tre": 0, "chua_nop": 0, "khong_cham_duoc": 0})
        if action == weekly_rules.ACT_SKIP:
            key = "khong_cham_duoc"
        elif action == weekly_rules.ACT_CLOSE:
            st, _late = scoring.classify_close(row["due_at"], get_datetime(closed_at))
            key = "dung_han" if st == "Met" else "tre"
        else:
            key = "chua_nop" if get_datetime(row["due_at"]) < now else "khong_cham_duoc"
        out[key] += 1
        bucket[key] += 1
    return out
