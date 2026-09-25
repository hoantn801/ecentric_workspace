# Copyright (c) 2026, eCentric and contributors
"""Cham bu diem / tom tat con thieu cho bao cao tuan.

Thay ruot Server Script `auto_retrigger_missing_ai` (cron */30). Hai thu bat
buoc phai doi khi chuyen sang Kie:

1. BO dieu kien `gemini_file_uris`. No la di san cua duong Google Files API:
   ban ghi phai co URI thi moi duoc cham. Duong Kie khong dung URI -- no tai PDF
   tu SharePoint va gui bytes inline -- nen loc theo URI se bo qua dung nhung
   ban ghi can cham nhat (vi du hai bao cao W39 nop 18/09: khong co URI vi buoc
   tai len Google that bai, va vi the khong bao gio duoc thu lai).
2. GHI DU LY DO. Ban cu cat loi con 80 ky tu: `regen_fail=4` moi luot ma khong
   mot dong nao noi vi sao. Mot con dem khong kem ly do thi khong dung duoc de
   chan doan -- do la ca tuan mat thoi gian truy nguoc.

Ngan sach: rq worker giet job o 300 GIAY. Day la may bom nho giot cho tuan moi,
KHONG phai cong cu chay bu hang loat -- dung erp-inspection/rescore_from_week.ps1
cho viec do (mot ban ghi moi request HTTP, khong dinh tran 300s).
"""

import frappe

from ecentric_workspace.weekly_report import scoring

WTU = "Weekly Team Update"
WINDOW_DAYS = 30
BATCH_LIMIT = 4


def _candidates(window_days, limit):
    """Ban ghi thieu diem hoac thieu tom tat, trong cua so.

    Cua so tinh bang NGAY chu khong phai gio: cua so 4 gio cua ban cu bien moi
    lan that bai thanh mot lo thung vinh vien -- ban nao truot roi gia qua 4 tieng
    thi khong bao gio duoc thu lai. W35-W38 mat 115 diem vi dung co che do.
    """
    sql = (
        "SELECT name, week_label, overall_ai_score, ai_summary "
        "FROM `tabWeekly Team Update` "
        "WHERE submitted_at > DATE_SUB(NOW(), INTERVAL " + str(int(window_days)) + " DAY) "
        "AND slide_deck IS NOT NULL AND slide_deck != '' "
        "AND ((overall_ai_score IS NULL OR overall_ai_score = 0) "
        "OR (ai_summary IS NULL OR ai_summary = '')) "
        "ORDER BY submitted_at DESC "
        "LIMIT " + str(int(limit))
    )
    return frappe.db.sql(sql, as_dict=True)


def run(window_days=WINDOW_DAYS, limit=BATCH_LIMIT):
    """-> dict thong ke. Khong nem: cron nuot loi thi khong con dau vet nao."""
    stats = {"found": 0, "checked": 0, "score_ok": 0, "score_fail": 0,
             "sum_ok": 0, "sum_fail": 0, "errors": []}

    rows = _candidates(window_days, limit)
    stats["found"] = len(rows)

    for r in rows:
        name = r.get("name")
        stats["checked"] = stats["checked"] + 1

        if not (r.get("overall_ai_score") or 0):
            try:
                res = scoring.score_report(name)
                if res.get("success"):
                    stats["score_ok"] = stats["score_ok"] + 1
                else:
                    stats["score_fail"] = stats["score_fail"] + 1
                    # Ly do DAY DU. Ban cu cat con 80 ky tu va do la ly do
                    # `regen_fail=4` khong dung duoc de chan doan gi.
                    stats["errors"].append(
                        "score " + str(name) + ": " + str(res.get("error"))[:500])
            except Exception as exc:
                stats["score_fail"] = stats["score_fail"] + 1
                stats["errors"].append(
                    "score " + str(name) + " EXC: " + str(exc)[:500])

        if not (r.get("ai_summary") or ""):
            try:
                res = scoring.summarize_report(name)
                if res.get("success"):
                    stats["sum_ok"] = stats["sum_ok"] + 1
                else:
                    stats["sum_fail"] = stats["sum_fail"] + 1
                    stats["errors"].append(
                        "sum " + str(name) + ": " + str(res.get("error"))[:500])
            except Exception as exc:
                stats["sum_fail"] = stats["sum_fail"] + 1
                stats["errors"].append(
                    "sum " + str(name) + " EXC: " + str(exc)[:500])

    return stats
