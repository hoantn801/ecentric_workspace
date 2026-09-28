# Copyright (c) 2026, eCentric and contributors
"""Tong hop bao cao tuan (toan cong ty / tung phong) - /team-pulse + lich thu Hai.

Thay hai Server Script (28/09):
  * `gemini_company_summary` (API)   -> `gemini_company_summary()` o day, qua override
    trong hooks.py nen trang van goi dung ten cu.
  * `auto_company_summary_weekly` (lich 12:00 thu Hai) -> `weekly_job()`, lich trong
    hooks.py; script cu duoc patch p214 tat.
Ca hai script cu goi thang Google (2.5-pro / 2.5-flash). Gio qua cong AI chung.

Quyen giu nguyen luat cua script cu (A14): toan cong ty -> chi Management; tom tat mot
phong -> Management hoac nguoi thuoc phong do. Lam moi / xem truoc -> chi Management.
"""
import json

import frappe

from ecentric_workspace.platform.ai import gateway, scope

CWS = "Company Weekly Summary"
BUDGET = 100
LIST = {"type": "array", "items": {"type": "string"}}
SCHEMA = {"type": "object", "properties": {
    "executive_summary": {"type": "string"}, "highlights": LIST, "risks": LIST,
    "ai_adoption": {"type": "string"}, "cross_team_patterns": LIST, "recommendations": LIST},
    "required": ["executive_summary", "highlights", "risks"]}


def current_week(now_dt):
    iso = now_dt.isocalendar()
    return "%d-W%02d" % (iso[0], iso[1])


def can_view(view, target_dept):
    """PURE."""
    if view["scope"] == scope.ALL:
        return True
    return bool(target_dept) and target_dept in view["depts"]


def build_instruction(target_week, target_dept, recs):
    """PURE. Giu nguyen noi dung prompt cua script cu."""
    depts = {}
    for r in recs:
        depts.setdefault(r.get("department") or "Chua phan loai", []).append(r)
    if target_dept:
        parts = ["# Bao cao tuan phong %s — %s" % (target_dept, target_week),
                 "So nhan su bao cao: %d" % len(recs)]
        for r in recs:
            parts.append("\n[%s]" % (r.get("full_name") or "?"))
            parts.append("Status: %s | AI Score: %s" % (r.get("overall_status") or "-",
                                                        r.get("overall_ai_score") or 0))
            parts.append("AI Tools: " + (r.get("ai_tools_used") or "-"))
            if r.get("ai_summary"):
                parts.append("Tom tat:\n" + r["ai_summary"])
        head = ("Ban la analyst eCentric. Tieng Viet professional.\n"
                "Tom tat hoat dong phong %s trong tuan." % target_dept)
        shape = "4 highlights, 2 risks, 1-2 cross_team_patterns, 2 recommendations"
    else:
        parts = ["# Cong ty eCentric — Tuan " + target_week,
                 "Tong so bao cao: %d | %d phong ban" % (len(recs), len(depts))]
        for dept, rows in depts.items():
            parts.append("\n=== %s (%d nguoi) ===" % (dept, len(rows)))
            for r in rows:
                parts.append("[%s] %s" % (r.get("full_name") or "?", r.get("overall_status") or "-"))
                if r.get("ai_summary"):
                    parts.append(r["ai_summary"])
        head = ("Ban la executive analyst eCentric. Tieng Viet professional.\n"
                "Tong hop bao cao tuan cua toan cong ty, nhan manh cross-team patterns.")
        shape = "5 highlights, 3 risks, 2-3 cross_team_patterns, 3 recommendations"
    return ("%s\n\nCONTEXT:\n%s\n\nexecutive_summary 2-3 doan; %s; ai_adoption la mot nhan xet."
            % (head, "\n".join(parts), shape)), len(depts)


def _records(target_week, target_dept):
    sql = ("SELECT name, department, full_name, overall_status, mood, ai_tools_used, "
           "ai_summary, overall_ai_score, structure_score FROM `tabWeekly Team Update` "
           "WHERE week_label = %(w)s")
    if target_dept:
        return frappe.db.sql(sql + " AND department = %(d)s ORDER BY full_name ASC",
                             {"w": target_week, "d": target_dept}, as_dict=True)
    return frappe.db.sql(sql + " ORDER BY department ASC, full_name ASC",
                         {"w": target_week}, as_dict=True)


def _from_doc(doc):
    out = {"week_label": doc.week_label, "department": doc.get("department") or "",
           "executive_summary": doc.executive_summary or "", "ai_adoption": doc.ai_adoption or "",
           "report_count": doc.report_count or 0, "dept_count": doc.dept_count or 0,
           "generated_at": str(doc.generated_at or ""), "generated_by": doc.generated_by or "",
           "auto_generated": bool(doc.auto_generated), "model_used": doc.model_used or ""}
    for key in ("highlights", "risks", "cross_team_patterns", "recommendations"):
        try:
            out[key] = json.loads(doc.get(key + "_json") or "[]")
        except Exception:
            out[key] = []
    return out


def _save(cws_name, target_week, target_dept, parsed, model, n_recs, n_depts, by, auto):
    exists = frappe.db.exists(CWS, cws_name)
    if exists:
        doc = frappe.get_doc(CWS, cws_name)
    else:
        doc = frappe.new_doc(CWS)
        doc.name = cws_name
        doc.week_label = target_week
        doc.flags.name_set = True
    doc.department = target_dept
    doc.generated_at = frappe.utils.now()
    doc.generated_by = by
    doc.auto_generated = 1 if auto else 0
    doc.model_used = model
    doc.report_count = n_recs
    doc.dept_count = n_depts
    doc.executive_summary = parsed.get("executive_summary", "")
    doc.ai_adoption = parsed.get("ai_adoption", "")
    for key in ("highlights", "risks", "cross_team_patterns", "recommendations"):
        doc.set(key + "_json", json.dumps(parsed.get(key, []), ensure_ascii=False))
    doc.raw_data = json.dumps(parsed, ensure_ascii=False)
    if exists:
        doc.save(ignore_permissions=True)
    else:
        doc.insert(ignore_permissions=True)


def generate(target_week, target_dept="", by="", auto=False, preview=False):
    """-> dict ket qua (khong nem)."""
    recs = _records(target_week, target_dept)
    if not recs:
        return {"success": False, "error": "Khong co bao cao cho %s tuan %s" % (
            target_dept or "toan cong ty", target_week)}
    prompt, n_depts = build_instruction(target_week, target_dept, recs)
    res = gateway.generate(prompt, schema=SCHEMA, purpose="company_summary", budget=BUDGET)
    if not res["ok"]:
        return {"success": False, "error": "AI đang bận, thử lại sau ít phút."}
    parsed = dict(res["data"])
    if not preview:
        try:
            cws_name = target_week if not target_dept else target_week + "::" + target_dept
            _save(cws_name, target_week, target_dept, parsed, res["model"], len(recs), n_depts,
                  by, auto)
        except Exception:
            frappe.log_error(title="company_summary save")
    parsed.update({"success": True, "week_label": target_week, "department": target_dept,
                   "report_count": len(recs), "dept_count": n_depts,
                   "generated_at": frappe.utils.now(), "from_cache": False,
                   "model_used": res["model"], "preview": bool(preview)})
    return parsed


@frappe.whitelist(methods=["POST"])
def gemini_company_summary(week_label=None, department=None, force_refresh=None,
                           preview=None, **kwargs):
    user = frappe.session.user
    view = scope.resolve(user)
    is_mgmt = view["scope"] == scope.ALL
    target_week = week_label or current_week(frappe.utils.now_datetime())
    target_dept = department or ""
    base = {"is_management": is_mgmt, "viewer_scope": view["scope"],
            "viewer_dept": ", ".join(view["depts"])}
    if not can_view(view, target_dept):
        return dict(base, success=False,
                    error="Khong co quyen xem tom tat " + (target_dept or "toan cong ty"))
    fresh = is_mgmt and bool(force_refresh or preview)
    cws_name = target_week if not target_dept else target_week + "::" + target_dept
    if not fresh and frappe.db.exists(CWS, cws_name):
        return dict(base, success=True, from_cache=True, **_from_doc(frappe.get_doc(CWS, cws_name)))
    out = generate(target_week, target_dept, by=user, preview=bool(preview) and is_mgmt)
    return dict(base, **out)


def weekly_job():
    """Lich thu Hai: tong hop toan cong ty cho tuan hien tai (thay auto_company_summary_weekly)."""
    week = current_week(frappe.utils.now_datetime())
    out = generate(week, "", by="Scheduler", auto=True)
    if not out.get("success"):
        frappe.log_error(title="company_summary weekly_job", message=str(out.get("error"))[:1000])
    return out
