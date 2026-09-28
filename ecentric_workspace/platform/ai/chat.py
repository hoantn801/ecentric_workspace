# Copyright (c) 2026, eCentric and contributors
"""Tro ly chat "AI eCentric" - o chat tren trang chu, /weekly-update, /team-pulse.

Thay Server Script `gemini_chat` (28/09). Trang van goi `/api/method/gemini_chat`: hooks.py
`override_whitelisted_methods` tro ten do ve ham o day, Frappe xet override TRUOC khi tim
Server Script - nen khong phai sua trang nao, va script cu khong con chay.

Ba thu doi so voi script cu:
  1. QUYEN (A14): xem scope.py. Het "chuc danh co chu lead -> xem ca cong ty".
  2. NHO CAU TRUOC: trang gui 10 luot gan nhat trong `history`; script cu bo qua, nen hoi
     tiep "con phong kia thi sao?" la AI khong biet "phong kia" la gi.
  3. DI QUA CONG AI CHUNG: script cu goi thang Google 2.5-flash (248 lan 400 trong 14 ngay
     toi 28/09). Gio Kie, co du phong.

Hop dong voi trang GIU NGUYEN: nhan {message, history:[{role:'user'|'model', text}]},
tra {success, reply, viewer_scope, dept} hoac {success: False, error}.
"""
import frappe

from ecentric_workspace.platform.ai import gateway, scope

MAX_MESSAGE = 4000
MAX_HISTORY_TURNS = 10
MAX_TURN_CHARS = 2000
BUDGET = 90
FIELDS = ("name, full_name, department, overall_status, mood, ai_tools_used, what_done, "
          "blockers_help, plan_next_week, ai_use_case, ai_summary, overall_ai_score, "
          "structure_score, week_label")


def week_labels(now_dt):
    """PURE. -> (tuan_nay, tuan_truoc) dang 'YYYY-Www'. Dung lich ISO ca hai dau - tuan 1
    thi tuan truoc la tuan cuoi cua NAM TRUOC (ban cu ra 'YYYY-W00')."""
    import datetime
    iso = now_dt.isocalendar()
    prev = (now_dt - datetime.timedelta(days=7)).isocalendar()
    return ("%d-W%02d" % (iso[0], iso[1]), "%d-W%02d" % (prev[0], prev[1]))


def clean_history(history):
    """PURE. Chi giu {role, text} hop le, toi da MAX_HISTORY_TURNS luot, moi luot da cat."""
    if isinstance(history, str):
        import json
        try:
            history = json.loads(history)
        except Exception:
            history = []
    out = []
    for h in (history or [])[-MAX_HISTORY_TURNS:]:
        if not isinstance(h, dict):
            continue
        text = str(h.get("text") or "").strip()[:MAX_TURN_CHARS]
        if text:
            out.append({"role": "user" if h.get("role") == "user" else "model", "text": text})
    return out


def _records(view, cur_week, prev_week):
    weeks = (cur_week, prev_week)
    if view["scope"] == scope.ALL:
        return frappe.db.sql(
            "SELECT " + FIELDS + " FROM `tabWeekly Team Update` WHERE week_label IN %(w)s"
            " ORDER BY week_label DESC, department ASC, full_name ASC", {"w": weeks}, as_dict=True)
    if view["scope"] == scope.DEPT:
        return frappe.db.sql(
            "SELECT " + FIELDS + " FROM `tabWeekly Team Update` WHERE week_label IN %(w)s"
            " AND department IN %(d)s ORDER BY week_label DESC, full_name ASC",
            {"w": weeks, "d": tuple(view["depts"])}, as_dict=True)
    if not view["employee"]:
        return []
    return frappe.db.sql(
        "SELECT " + FIELDS + " FROM `tabWeekly Team Update` WHERE week_label IN %(w)s"
        " AND employee = %(e)s ORDER BY week_label DESC LIMIT 2",
        {"w": weeks, "e": view["employee"]}, as_dict=True)


def build_context(view, user, cur_week, recs, company_summary=""):
    """PURE. Ngu canh gui kem cau hoi."""
    label = {"all": "Toan cong ty", "dept": "Phong " + ", ".join(view["depts"]),
             "self": "Bao cao cua ban"}[view["scope"]]
    lines = ["Ban la AI tro ly cua eCentric. Tra loi tieng Viet, ngan gon, dung Markdown "
             "(** bold, * bullet). Chi dua tren du lieu duoi day; khong co thi noi khong co.",
             "Tuan hien tai: " + cur_week, "Nguoi dang hoi: " + user,
             "", "=== %s (%d bao cao, 2 tuan gan nhat) ===" % (label, len(recs))]
    for r in recs:
        lines.append("")
        lines.append("[%s - %s - %s]" % (r.get("full_name") or "?", r.get("department") or "",
                                        r.get("week_label") or ""))
        lines.append("Status: %s | Mood: %s | AI Score: %s" % (
            r.get("overall_status") or "-", r.get("mood") or "-", r.get("overall_ai_score") or "-"))
        lines.append("AI Tools: " + (r.get("ai_tools_used") or "-"))
        for key, name, cap in (("what_done", "Da lam", 300), ("blockers_help", "Blocker", 200),
                               ("plan_next_week", "Plan", 200), ("ai_summary", "AI summary", 500)):
            if r.get(key):
                lines.append("%s: %s" % (name, str(r[key])[:cap]))
    if company_summary:
        lines += ["", "=== Tong hop cong ty tuan %s ===" % cur_week, company_summary]
    return "\n".join(lines)


@frappe.whitelist(methods=["POST"])
def gemini_chat(message=None, history=None, **kwargs):
    user = frappe.session.user
    if not user or user == "Guest":
        return {"success": False, "error": "Cần đăng nhập."}
    message = str(message or "").strip()
    if not message:
        return {"success": False, "error": "Message required"}
    view = scope.resolve(user)
    cur_week, prev_week = week_labels(frappe.utils.now_datetime())
    try:
        recs = _records(view, cur_week, prev_week)
    except Exception:
        frappe.log_error(title="ai_chat records")
        recs = []
    summary = ""
    if view["scope"] == scope.ALL:
        summary = frappe.db.get_value("Company Weekly Summary", cur_week, "executive_summary") or ""
    res = gateway.generate(message[:MAX_MESSAGE],
                           system=build_context(view, user, cur_week, recs, summary),
                           history=clean_history(history), purpose="chat", budget=BUDGET)
    if not res["ok"]:
        return {"success": False, "error": "AI đang bận, thử lại sau ít phút.",
                "viewer_scope": view["scope"]}
    return {"success": True, "reply": res["text"], "viewer_scope": view["scope"],
            "dept": ", ".join(view["depts"]), "model": res["model"]}
