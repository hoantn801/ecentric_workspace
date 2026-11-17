# Copyright (c) 2026, eCentric and contributors
"""Việc cần làm - "Tồn đọng" clean-up in one go (hotfix 16, PO 17/11/2026).

One whitelisted write: bulk(action, names, due). It does NOT bypass anything - every task goes
through the SAME governed endpoint a single click uses, so permissions, audit (Version / state
history), notifications and the "Xong" rules (required steps, open sub-tasks, review) are unchanged:

    move  -> tasks.update(exp_end_date=due)                  new due date (today or later)
    clear -> tasks.update(exp_end_date="", pm_end_time="")   "Chưa có hạn"
    done  -> tasks.mark_done                                 Xong / Gửi kiểm tra

Order of checks per task (QC 17/11):
    1. can the caller SEE it? no -> "not_found" (never reveal that someone else's task exists);
    2. move / clear: giver must be ME or a system account (Administrator imports: nobody to ask).
       A deadline someone else gave stays theirs -> "others" (screen: use "Xin dời hạn").
       A "Mỗi người một việc" parent -> "split" (each person's part has its own deadline);
    3. the governed endpoint itself (edit permission, workflow, required steps...).

Each task runs in its own savepoint: one failure is rolled back and reported, the rest still apply.
The request's own form_dict is hidden from tasks.update (its _sent_fields() reads form_dict to tell
"omitted" from "cleared" - keys of THIS request must never look like task fields). A database
deadlock aborts the whole transaction (InnoDB), so the batch stops, rolls back and says so instead
of reporting tasks as done that were silently undone.
Returns {action, ok: [names], states: {name: state}, skipped: [{name, reason, message}]}.
The screen sends at most CHUNK names per call (progress "Đang xử lý 50/180")."""
import frappe
from frappe import _
from frappe.exceptions import QueryDeadlockError
from frappe.utils import getdate, nowdate

from ecentric_workspace.pm import permissions as pmperm
from ecentric_workspace.pm import task_flow as tflow

ACTIONS = ("move", "clear", "done")
MAX_NAMES = 50
R_OTHERS, R_SPLIT, R_BLOCKED, R_ERROR, R_NOT_FOUND = "others", "split", "blocked", "error", "not_found"
BLOCKED_TEXT = {"required_steps": "Còn {0} bước bắt buộc chưa tích.",
                "open_children": "Còn {0} việc con chưa xong."}


def _names(raw):
    if isinstance(raw, str):
        raw = frappe.parse_json(raw) if raw.strip().startswith("[") else [x for x in raw.split(",")]
    out, seen = [], set()
    for n in raw or []:
        n = str(n or "").strip()
        if n and n not in seen:
            seen.add(n)
            out.append(n)
    return out


def _due(due):
    try:
        d = getdate(due) if due else None
    except Exception:
        d = None
    if not d:
        frappe.throw(_("Chọn ngày hạn mới."))
    if d < getdate(nowdate()):
        frappe.throw(_("Hạn mới phải từ hôm nay trở đi."))
    return d.isoformat()


def _skip(name, reason, message):
    return None, {"name": name, "reason": reason, "message": message}


def _one(action, row, due, user, givers):
    from ecentric_workspace.pm.api import tasks

    name = row["name"]
    if action in ("move", "clear"):
        g = givers.get(name) or ""
        if g != user and g not in tflow._SYSTEM_USERS:
            return _skip(name, R_OTHERS, _("Việc người khác giao: dùng Xin dời hạn trên việc đó."))
        if tflow.truthy(row.get("ec_split_parent")):
            return _skip(name, R_SPLIT, _("Việc chia mỗi người một phần: mở việc để dời hạn từng phần."))
        update = getattr(tasks.update, "__wrapped__", tasks.update)   # no inner deadlock retry (it rolls back ALL)
        if action == "move":
            update(name, exp_end_date=due)
        else:
            update(name, exp_end_date="", pm_end_time="")
        return "moved", None
    res = tasks.mark_done(name) or {}
    code = res.get("blocked_reason")
    if code:
        return _skip(name, R_BLOCKED, _(BLOCKED_TEXT.get(code, code)).format(res.get("missing") or ""))
    return res.get("state") or "Done", None


@frappe.whitelist(methods=["POST"])
def bulk(action, names, due=None):
    pmperm.require_pm_access()
    user = frappe.session.user
    if action not in ACTIONS:
        frappe.throw(_("Thao tác không hợp lệ."))
    names = _names(names)
    if not names:
        frappe.throw(_("Chưa chọn việc nào."))
    if len(names) > MAX_NAMES:
        frappe.throw(_("Mỗi lần xử lý tối đa {0} việc.").format(MAX_NAMES))
    due = _due(due) if action == "move" else None
    rows = {r["name"]: r for r in frappe.get_all(
        "Task", filters={"name": ["in", names]},
        fields=["name", "owner", "project", "parent_task", "_assign", "ec_split_parent"], limit_page_length=0)}
    givers = tflow.givers_map(list(rows.values())) if action in ("move", "clear") else {}
    out = {"action": action, "ok": [], "states": {}, "skipped": []}
    saved = frappe.local.form_dict
    frappe.local.form_dict = frappe._dict() if hasattr(frappe, "_dict") else {}
    try:
        for i, name in enumerate(names):
            row = rows.get(name)
            if not row or not pmperm.can_view_task(row, user):
                out["skipped"].append({"name": name, "reason": R_NOT_FOUND, "message": _("Không tìm thấy việc.")})
                continue
            sp = "pmq_bulk_%d" % i
            frappe.db.savepoint(sp)
            try:
                state, skip = _one(action, row, due, user, givers)
            except QueryDeadlockError:
                frappe.db.rollback()
                frappe.throw(_("Hệ thống đang bận, chưa lưu việc nào trong lần này. Thử lại sau ít phút."))
            except Exception as e:
                frappe.db.rollback(save_point=sp)
                frappe.clear_messages()
                state, skip = None, {"name": name, "reason": R_ERROR,
                                     "message": str(getattr(e, "message", "") or e)[:200]}
            if skip:
                out["skipped"].append(skip)
            else:
                out["ok"].append(name)
                out["states"][name] = state
    finally:
        frappe.local.form_dict = saved
    return out
