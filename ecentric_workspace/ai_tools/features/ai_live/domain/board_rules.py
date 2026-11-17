# Copyright (c) 2026, eCentric and contributors
"""18/11 (hop dong lich live muc 8): du lieu cho kieu xem Bang / Timeline (ngay van hanh 06:00 -> 06:00 hom sau)
va Theo brand (thang). Thuan Python, epoch giay, gio Viet Nam. Dau vao la dong cua slot_report_rules.match
(ke hoach da phat hanh ghep bao cao app)."""
from datetime import date, datetime, timedelta

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R

DAY_START_H = 6       # truc gio 06:00 -> 06:00 hom sau (live dem qua 0h ve lien)
STATUS_TEXT = {"upcoming": "Sắp tới", "waiting": "Chưa lên sóng", "live": "Đang live", "done": "Đã xong",
               "missed": "Lỡ", "no_report": "Không có báo cáo"}
_DONE = ("on_time", "late", "ended_early", "overran", "stop_failed")


def window(day):
    """(lo, hi) epoch cua ngay van hanh `day`: 06:00 ngay do -> 06:00 hom sau (gio VN)."""
    lo = datetime(day.year, day.month, day.day, DAY_START_H, tzinfo=R._VN).timestamp()
    return lo, lo + 86400


def overlaps(row, lo, hi):
    return row["start_ts"] < hi and row["end_ts"] > lo


def status(row, now):
    """Trang thai 1 dong ke hoach: upcoming | waiting | live | done | missed | no_report."""
    rep, a, b = row.get("report") or {}, row["start_ts"], row["end_ts"]
    st = rep.get("status") if rep else None
    if st == "missed":
        return "missed"
    if st == "running":
        return "live"
    if st in ("overran", "stop_failed") and not rep.get("actual_end_ts"):
        return "live"                          # app dat khi qua gio ma live CHUA tat (src/slotreport.js)
    if st in _DONE:
        return "done" if (rep.get("actual_end_ts") or rep.get("final") or now >= b) else "live"
    if rep and rep.get("actual_start_ts") and not rep.get("actual_end_ts") and now < b:
        return "live"
    if rep:                                    # pending: may biet khung nay nhung chua len song
        if now < a:
            return "upcoming"
        return "missed" if now >= b else "waiting"
    if row.get("no_report"):
        return "no_report"
    return "upcoming" if now < a else ("waiting" if now < b else "no_report")


def live_seconds(rep, planned_end, now):
    """So giay da live thuc te cua 1 bao cao: tu luc len song toi luc xuong (dang chay: toi bay gio), tru gian doan."""
    a = float(rep.get("actual_start_ts") or 0)
    if not a:
        return 0
    b = float(rep.get("actual_end_ts") or 0)
    if not b:                                  # chua xuong song: dang chay thi tinh toi lan bao cao cuoi cua may
        cap = float(planned_end or 0)
        if rep.get("status") in ("running", "overran", "stop_failed"):
            cap = max(cap, float(rep.get("updated_ts") or 0))
        b = min(now, max(cap, a))
    return max(0, int(b - a) - int(rep.get("downtime_sec") or 0))


def month_days(month, today):
    """'YYYY-MM' (rong = thang cua today) -> [date...] ca thang. Sai dinh dang -> AiLiveError."""
    m = str(month or "").strip() or today.strftime("%Y-%m")
    if not C.MONTH_RE.match(m):
        raise C.AiLiveError(C.SessMsg.BAD_MONTH)
    y, mo = int(m[:4]), int(m[5:7])
    first = date(y, mo, 1)
    nxt = date(y + (mo == 12), mo % 12 + 1, 1)
    return [first + timedelta(days=k) for k in range((nxt - first).days)]


def brand_rollup(planned, reports, brand_of, now):
    """planned: [{live, brand, start_ts, end_ts}] (ca thang); reports: bao cao trong thang; brand_of(live, rep) -> brand.
    -> [{brand, lives, planned_h, due_h, live_h, pct, off_plan_h}] - pct = gio da live / gio ke hoach DA TOI GIO
    (khung chua toi khong keo % xuong). Bao cao ngoai ke hoach ERP tinh rieng off_plan_h."""
    agg = {}

    def row(b):
        return agg.setdefault(b or "—", {"brand": b or "—", "lives": 0, "planned_s": 0, "due_s": 0, "live_s": 0, "off_s": 0})
    for p in planned:
        r = row(p.get("brand"))
        dur = max(0, p["end_ts"] - p["start_ts"])
        r["lives"] += 1
        r["planned_s"] += dur
        r["due_s"] += max(0, min(now, p["end_ts"]) - p["start_ts"]) if now > p["start_ts"] else 0
    for rep in reports:
        sec = live_seconds(rep, rep.get("planned_end_ts") or 0, now)
        r = row(brand_of(rep.get("live"), rep))
        if int(rep.get("off_plan") or 0):
            r["off_s"] += sec
        else:
            r["live_s"] += sec
    out = []
    for r in sorted(agg.values(), key=lambda x: (-x["planned_s"], x["brand"])):
        out.append({"brand": r["brand"], "lives": r["lives"], "planned_h": round(r["planned_s"] / 3600.0, 1),
                    "due_h": round(r["due_s"] / 3600.0, 1), "live_h": round(r["live_s"] / 3600.0, 1),
                    "off_plan_h": round(r["off_s"] / 3600.0, 1),
                    "pct": round(100.0 * r["live_s"] / r["due_s"]) if r["due_s"] else None})
    return out
