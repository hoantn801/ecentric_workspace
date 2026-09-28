# Copyright (c) 2026, eCentric and contributors
"""Cham bu diem / tom tat con thieu cho bao cao tuan.

Thay ruot Server Script `auto_retrigger_missing_ai` (cron */30).

LICH SU:
  25/09 - bo loc `gemini_file_uris` (di san Google Files API), ghi du ly do loi.
  28/09 - chuyen sang cong AI chung + TACH MOI BAN GHI RA MOT JOB RIENG. Ly do, do that:
    * 200 luot cron 22-28/09 tim 800 luot can cham, chi 26 diem + 31 tom tat thanh cong.
    * Mot luot lam 4 ban ghi x 2 lan goi x (30s Kie + du phong) trong MOT job -> vuot tran
      300s cua rq worker (51 JobTimeoutException). Job bi giet giua chung, khong ghi gi.
    * `LIMIT 4 ORDER BY submitted_at DESC` boc lai DUNG 4 ban ghi hong vinh vien moi 30 phut
      (moi ban 41 lan: deck khong tai duoc) -> ban ghi khac KHONG BAO GIO toi luot.

  Gio: cron chi CHON viec va xep hang; moi ban ghi la mot job tren queue `long` (tran rong,
  job_id chong trung). Ban ghi hong MAX_FAILS lan lien tiep thi nghi COOLDOWN_HOURS - khong
  bi bo han, chi nhuong cho cho ban khac.

Backlog lon van dung erp-inspection/rescore_from_week.ps1.
"""
import frappe

from ecentric_workspace.weekly_report import scoring, scoring_llm

WTU = "Weekly Team Update"
WINDOW_DAYS = 30
#: So job xep hang moi luot cron. 30 phut / luot -> toi da 288 ban ghi / ngay.
BATCH_LIMIT = 6
#: Lay rong hon BATCH_LIMIT de con cho sau khi loai ban dang nghi.
CANDIDATE_POOL = 60
MAX_FAILS = 3
COOLDOWN_HOURS = 12
JOB_TIMEOUT = 600          # giay, tran cua job tren queue long
FAIL_KEY = "wr_ai_fail::%s"


def _candidates(window_days, limit):
    """Ban ghi thieu diem hoac thieu tom tat, trong cua so (tinh bang NGAY - xem 15/09)."""
    return frappe.db.sql(
        """SELECT name, week_label, overall_ai_score, ai_summary
           FROM `tabWeekly Team Update`
           WHERE submitted_at > DATE_SUB(NOW(), INTERVAL %(days)s DAY)
             AND slide_deck IS NOT NULL AND slide_deck != ''
             AND ((overall_ai_score IS NULL OR overall_ai_score = 0)
                  OR (ai_summary IS NULL OR ai_summary = ''))
           ORDER BY submitted_at DESC
           LIMIT %(limit)s""",
        {"days": int(window_days), "limit": int(limit)}, as_dict=True)


def fail_count(name):
    try:
        return int(frappe.cache().get_value(FAIL_KEY % name) or 0)
    except Exception:
        return 0


def _mark(name, ok):
    """Thanh cong -> xoa dem. Hong -> tang dem, song COOLDOWN_HOURS."""
    try:
        if ok:
            frappe.cache().delete_value(FAIL_KEY % name)
        else:
            frappe.cache().set_value(FAIL_KEY % name, fail_count(name) + 1,
                                     expires_in_sec=COOLDOWN_HOURS * 3600)
    except Exception:
        pass


def pick(rows, limit, counts):
    """PURE. -> (chon, dang_nghi). `counts` = {name: so lan hong lien tiep}."""
    chosen, resting = [], []
    for r in rows:
        if counts.get(r["name"], 0) >= MAX_FAILS:
            resting.append(r["name"])
        elif len(chosen) < limit:
            chosen.append(r)
    return chosen, resting


def run(window_days=WINDOW_DAYS, limit=BATCH_LIMIT):
    """Cron: chon viec + xep hang. -> dict thong ke. Khong nem."""
    stats = {"found": 0, "enqueued": 0, "resting": 0, "resting_names": [], "errors": []}
    try:
        rows = _candidates(window_days, CANDIDATE_POOL)
    except Exception as exc:
        stats["errors"].append("query: %s" % str(exc)[:300])
        return stats
    stats["found"] = len(rows)
    counts = {r["name"]: fail_count(r["name"]) for r in rows}
    chosen, resting = pick(rows, int(limit), counts)
    stats["resting"] = len(resting)
    stats["resting_names"] = resting[:20]
    for r in chosen:
        try:
            frappe.enqueue("ecentric_workspace.weekly_report.ai_retrigger.process_one",
                           queue="long", timeout=JOB_TIMEOUT, name=r["name"],
                           job_id="wr_ai::%s" % r["name"], deduplicate=True)
            stats["enqueued"] += 1
        except Exception as exc:
            stats["errors"].append("enqueue %s: %s" % (r["name"], str(exc)[:300]))
    return stats


def process_one(name):
    """Job: cham + tom tat MOT ban ghi. Ghi Error Log khi hong, kem ly do day du."""
    row = frappe.db.get_value(WTU, name, ["overall_ai_score", "ai_summary"], as_dict=True)
    if not row:
        return {"skipped": "khong con ban ghi"}
    kw = {"budget": scoring_llm.JOB_BUDGET, "attempt_timeout": scoring_llm.JOB_ATTEMPT_TIMEOUT}
    errors, did = [], []
    if not (row.get("overall_ai_score") or 0):
        res = _safe(scoring.score_report, name, kw)
        (did if res.get("success") else errors).append("score: %s" % (res.get("error") or "ok"))
    if not (row.get("ai_summary") or ""):
        res = _safe(scoring.summarize_report, name, kw)
        (did if res.get("success") else errors).append("sum: %s" % (res.get("error") or "ok"))
    _mark(name, not errors)
    if errors:
        try:
            frappe.log_error(title="wr_ai_retrigger_fail",
                             message=("%s (lan hong thu %d)\n%s" % (
                                 name, fail_count(name), "\n".join(errors)))[:2000])
        except Exception:
            pass
    return {"name": name, "ok": not errors, "done": did, "errors": errors}


def _safe(fn, name, kw):
    try:
        return fn(name, **kw) or {}
    except Exception as exc:
        return {"success": False, "error": "EXC %s: %s" % (type(exc).__name__, str(exc)[:400])}
