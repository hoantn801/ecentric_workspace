# Copyright (c) 2026, eCentric and contributors
"""Bộ công cụ ERP cho Claude (đợt 1 - Hoàn chốt 16/11/2026):

    Việc cần làm / PM : đọc + giao việc, Xong, Bắt đầu, xin dời hạn, nhắc, bình luận
    Approval Center   : CHỈ ĐỌC (việc chờ tôi xử lý, phiếu của tôi, chi tiết phiếu)
    Báo cáo tuần      : CHỈ ĐỌC

KHÔNG có duyệt / từ chối phiếu, không đụng tiền, không xoá. Muốn thêm thì thêm công cụ mới,
đừng mở công cụ chung kiểu call_method.

QUY TẮC CHO MỌI CÔNG CỤ
  * Gọi ĐÚNG hàm mà màn hình web đang gọi (queue.list, tasks.create, tasks.mark_done, ...).
    Không truy vấn thẳng bảng để "nhanh hơn": quyền, thứ tự, thông báo, audit nằm trong các hàm đó.
    Ngoại lệ có chủ đích: báo cáo tuần đọc qua frappe.get_list / has_permission (đi qua đúng
    permission_query_conditions + has_permission của weekly_report/permissions.py).
  * Người dùng LUÔN là frappe.session.user (chủ token OAuth). Không công cụ nào nhận tham số user.
  * Kết quả gọn: Claude đọc từng chữ, trả 500 dòng thô là tốn và dễ đọc sai.
"""
import html
import re
import unicodedata

import frappe
from frappe.utils import get_url

from ecentric_workspace.claude_mcp.protocol import ToolError

READ = {"readOnlyHint": True, "openWorldHint": False}
WRITE = {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}

PRIORITIES = ("Low", "Medium", "High", "Urgent")
_PRIO_VI = {"thap": "Low", "thấp": "Low", "binh thuong": "Medium", "bình thường": "Medium",
            "cao": "High", "gap": "Urgent", "gấp": "Urgent", "khan cap": "Urgent", "khẩn cấp": "Urgent"}
_YMD = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_HM = re.compile(r"^([01]?\d|2[0-3]):([0-5]\d)$")


# ============================================================ helpers
def fold(s):
    """'Nguyễn Thị Lan' -> 'nguyen thi lan' (so khớp không dấu, như ô @ trên màn giao việc)."""
    s = unicodedata.normalize("NFD", str(s or "")).replace("đ", "d").replace("Đ", "D")
    return "".join(c for c in s if unicodedata.category(c) != "Mn").lower().strip()


def plain(s, cap=1500):
    """HTML -> chữ thường, cắt ngắn."""
    s = re.sub(r"<br\s*/?>|</p>|</div>|</li>", "\n", str(s or ""), flags=re.I)
    s = html.unescape(re.sub(r"<[^>]+>", "", s))
    s = re.sub(r"\n{3,}", "\n\n", s).strip()
    return s if len(s) <= cap else s[:cap] + "…"


def link(path):
    return get_url(path) if path else ""


def task_link(name):
    return link("/pm#task/" + str(name))


def limit_of(v, default, hi):
    try:
        return max(1, min(int(v), hi))
    except (TypeError, ValueError):
        return default


def norm_priority(p):
    if p in (None, ""):
        return None
    if p in PRIORITIES:
        return p
    hit = _PRIO_VI.get(str(p).strip().lower()) or _PRIO_VI.get(fold(p))
    if hit:
        return hit
    cap = str(p).strip().capitalize()
    if cap in PRIORITIES:
        return cap
    raise ToolError("Mức ưu tiên không hợp lệ: %s. Dùng Low / Medium / High / Urgent." % p)


def norm_date(v, label):
    if v in (None, ""):
        return None
    v = str(v).strip()[:10]
    if not _YMD.match(v):
        raise ToolError("%s phải có dạng YYYY-MM-DD (nhận được: %s)." % (label, v))
    return v


def norm_time(v):
    if v in (None, ""):
        return None
    m = _HM.match(str(v).strip()[:5])
    if not m:
        raise ToolError("Giờ phải có dạng HH:MM (nhận được: %s)." % v)
    return "%02d:%s" % (int(m.group(1)), m.group(2))


def as_list(v):
    if v in (None, ""):
        return []
    if isinstance(v, (list, tuple)):
        return [str(x).strip() for x in v if str(x).strip()]
    return [x.strip() for x in re.split(r"[,;\n]", str(v)) if x.strip()]


# ============================================================ PM / Việc cần làm
def _row(r):
    """Một dòng hàng đợi (queue._decorate) -> bản gọn cho Claude."""
    out = {
        "rank": r.get("rank") or None,
        "task": r.get("name"),
        "subject": r.get("subject"),
        "group": r.get("bucket"),
        "due": r.get("due") or None,
        "due_time": r.get("due_time") or None,
        "priority": r.get("priority"),
        "state": r.get("workflow_state"),
        "project": r.get("project_name") or None,
        "giver": r.get("giver_name") or ("(tự giao)" if r.get("self") else None),
        "assignees": [a.get("name") for a in r.get("assignees") or []],
        "link": task_link(r.get("name")),
    }
    if r.get("progress"):
        out["progress"] = r["progress"]
    if r.get("awaiting"):
        out["awaiting_acceptance"] = True
    if r.get("unopened"):
        out["not_opened_by_someone"] = True
    if r.get("deadline_ask"):
        out["my_deadline_request"] = r["deadline_ask"]
    if r.get("counter"):
        c = r["counter"]
        out["proposal"] = {"from": c.get("recipient_name"), "kind": c.get("kind"),
                           "new_due": c.get("due"), "new_time": c.get("time"),
                           "old_due": c.get("old_due"), "reason": c.get("reason")}
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def my_tasks(view="me", include_personal=False, limit=40):
    from ecentric_workspace.pm.api import queue

    view = "give" if view == "give" else "me"
    res = queue.list(tab=view, include_personal=1 if include_personal else 0)
    n = limit_of(limit, 40, 200)
    rows = res.get("rows") or []
    labels = {b.get("key"): b.get("label") for b in res.get("buckets") or []}
    out = {
        "today": res.get("today"),
        "view": "Việc cần làm (giao cho tôi)" if view == "me" else "Việc tôi giao",
        "total": len(rows),
        "counts": {labels.get(k, k): v for k, v in (res.get("counts") or {}).items() if v},
        "tasks": [_row(r) for r in rows[:n]],
        "shown": min(n, len(rows)),
        "open_in_browser": link("/pm#mywork"),
    }
    if view == "me":
        asks = res.get("asks") or []
        if asks:
            out["needs_my_acceptance"] = [
                {k: v for k, v in {
                    "request": a.get("request"), "task": a.get("task"), "subject": a.get("subject"),
                    "from": a.get("from_name") or a.get("from_user"), "due": a.get("proposed_end"),
                    "message": a.get("message"), "link": task_link(a.get("task"))}.items() if v}
                for a in asks[:20]]
            out["needs_my_acceptance_note"] = "Nhận / từ chối việc 'Cần đồng ý' hãy mở link trên web."
        waiting = res.get("waiting") or []
        if waiting:
            out["waiting_for_review_by_others"] = [_row(r) for r in waiting[:20]]
    else:
        props = res.get("proposals") or []
        if props:
            out["deadline_proposals_waiting_for_me"] = [_row(r) for r in props[:20]]
    if res.get("personal_hidden"):
        out["personal_log_hidden"] = res["personal_hidden"]
    return out


def get_task(task):
    from ecentric_workspace.pm.api import comments, tasks

    res = tasks.get(task) or {}
    d = res.get("task") or {}
    names = res.get("user_names") or {}
    giver = d.get("giver") or {}
    d["subtasks"] = res.get("subtasks") or []
    d["assignees"] = [{"name": names.get(e) or e} for e in _emails(d.get("_assign"))]
    out = {
        "task": d.get("name"),
        "subject": d.get("subject"),
        "state": d.get("workflow_state"),
        "priority": d.get("priority"),
        "start": str(d.get("exp_start_date") or "") or None,
        "due": str(d.get("exp_end_date") or "") or None,
        "due_time": str(d.get("pm_end_time") or "")[:5] or None,
        "project": d.get("project_name"),
        "parent_task": d.get("parent_task"),
        "giver": giver.get("full_name") or giver.get("user"),
        "assignees": [a.get("name") or a.get("full_name") or a.get("user")
                      for a in d.get("assignees") or [] if isinstance(a, dict)] or None,
        "labels": [l.get("label") or l.get("name") for l in d.get("labels") or [] if isinstance(l, dict)] or None,
        "description": plain(d.get("description")) or None,
        "subtasks": [{"task": s.get("name"), "subject": s.get("subject"),
                      "state": s.get("workflow_state"), "due": str(s.get("exp_end_date") or "") or None}
                     for s in d.get("subtasks") or []] or None,
        "link": task_link(d.get("name")),
    }
    try:
        cm = comments.list("Task", d.get("name")).get("rows") or []
        out["recent_comments"] = [{"by": c.get("owner"), "at": str(c.get("creation"))[:16],
                                   "text": plain(c.get("content"), 400)} for c in cm[-8:]] or None
    except Exception:
        pass
    return {k: v for k, v in out.items() if v not in (None, [], "")}


def _emails(assign):
    """Task._assign (chuỗi JSON hoặc list) -> list email."""
    if not assign:
        return []
    if isinstance(assign, str):
        try:
            assign = frappe.parse_json(assign)
        except Exception:
            return []
    return [a for a in assign or [] if isinstance(a, str) and a]


def find_people(query, limit=8):
    from ecentric_workspace.pm.api import assignment

    q = fold(query).lstrip("@")
    if not q:
        raise ToolError("Cần một tên hoặc email để tìm.")
    rows = assignment.list_assignable().get("rows") or []
    words = q.split()
    hits = []
    for r in rows:
        hay = fold(r.get("full_name")) + " " + fold(r.get("email"))
        if all(w in hay for w in words):
            # tên gọi (chữ cuối) trùng hẳn -> lên đầu
            exact = fold(r.get("full_name")).split()[-1:] == words[-1:]
            hits.append((0 if exact else 1, r.get("full_name") or "", r))
    hits.sort(key=lambda x: (x[0], x[1]))
    n = limit_of(limit, 8, 30)
    return {"query": query, "matches": [{"email": h[2]["email"], "name": h[2].get("full_name")}
                                        for h in hits[:n]],
            "total": len(hits)}


def create_task(subject, assignees=None, due_date=None, due_time=None, priority=None,
                description=None, need_acceptance=False, one_per_person=True):
    """Giống ô "giao việc 1 dòng" trên /pm#mywork (pm_queue.js): không dự án, mặc định ưu tiên Medium."""
    from ecentric_workspace.pm.api import assignment, tasks

    subject = (subject or "").strip()
    if not subject:
        raise ToolError("Thiếu tên việc.")
    people = as_list(assignees) or [frappe.session.user]
    bad = [p for p in people if "@" not in p]
    if bad:
        raise ToolError("Người nhận phải là email (dùng find_people để tra): " + ", ".join(bad))
    due = norm_date(due_date, "Hạn")
    tm = norm_time(due_time)
    pri = norm_priority(priority) or "Medium"
    desc = html.escape(description).replace("\n", "<br>") if description else None
    others = [p for p in people if p != frappe.session.user]
    if need_acceptance and others:
        end = (due + " " + (tm or "18:00") + ":00") if due else None
        if len(people) > 1:
            res = assignment.create_with_task(subject=subject, recipients=frappe.as_json(people),
                                              split_per_assignee=1, priority=pri, proposed_end=end,
                                              description=desc, project="")
        else:
            res = assignment.create_with_task(subject=subject, recipient=people[0], priority=pri,
                                              proposed_end=end, description=desc, project="")
        mode = "Cần đồng ý: người nhận phải bấm Nhận việc"
    else:
        split = (1 if one_per_person else 0) if len(people) > 1 else None
        res = tasks.create(project="", subject=subject, assignees=frappe.as_json(people),
                           split_per_assignee=split, exp_end_date=due,
                           pm_end_time=(tm + ":00") if tm else None, priority=pri, description=desc)
        mode = "Giao ngay"
    name = _created_name(res)
    return {"ok": True, "task": name, "subject": subject, "assignees": people, "due": due,
            "due_time": tm, "priority": pri, "mode": mode,
            "link": task_link(name) if name else link("/pm#mywork")}


def _created_name(res):
    if isinstance(res, str):
        return res
    if isinstance(res, dict):
        for k in ("task", "name", "parent", "task_name"):
            v = res.get(k)
            if isinstance(v, str) and v:
                return v
            if isinstance(v, dict) and v.get("name"):
                return v["name"]
    return None


def complete_task(task):
    from ecentric_workspace.pm.api import tasks

    res = tasks.mark_done(task) or {}
    why = res.get("blocked_reason")
    if why == "required_steps":
        raise ToolError("Chưa xong được: còn %s bước bắt buộc trong checklist chưa đánh dấu." % res.get("missing"))
    if why == "open_children":
        raise ToolError("Chưa xong được: còn %s việc con đang mở." % res.get("missing"))
    state = res.get("state")
    msg = "Đã gửi người giao kiểm tra (Chờ duyệt)." if state == "Review" else "Đã đánh dấu Xong."
    return {"ok": True, "task": task, "state": state, "message": msg, "link": task_link(task)}


def start_task(task):
    from ecentric_workspace.pm.api import tasks

    tasks.set_status(task, "In Progress")
    return {"ok": True, "task": task, "state": "In Progress", "link": task_link(task)}


def request_deadline_change(task, new_due, reason):
    from ecentric_workspace.pm.api import pm_inbox

    nd = norm_date(new_due, "Hạn mới")
    if not (reason or "").strip():
        raise ToolError("Cần lý do xin dời hạn.")
    pm_inbox.request_deadline(task, nd, reason.strip())
    return {"ok": True, "task": task, "new_due": nd,
            "message": "Đã gửi xin dời hạn. Hạn chỉ đổi khi người giao đồng ý.", "link": task_link(task)}


def remind_assignees(task):
    from ecentric_workspace.pm.api import pm_inbox

    res = pm_inbox.nudge(task) or {}
    return {"ok": True, "task": task, "reminded": res.get("sent") or res.get("reminded"),
            "skipped_recently_reminded": res.get("skipped") or None}


def comment_on_task(task, text):
    from ecentric_workspace.pm.api import comments

    text = (text or "").strip()
    if not text:
        raise ToolError("Bình luận trống.")
    res = comments.add("Task", task, html.escape(text).replace("\n", "<br>"))
    return {"ok": True, "task": task, "comment": res.get("name"), "link": task_link(task)}


# ============================================================ Approval Center (chỉ đọc)
_SRC_VI = {"approval": "Phiếu chờ duyệt", "task": "Việc PM", "weekly_report": "Báo cáo tuần",
           "fulfillment": "Phiếu cần xử lý", "generic": "Việc khác"}


def my_action_items(limit=20, cursor=None):
    from ecentric_workspace.action_center import feed

    res = feed.build_feed(frappe.session.user, cursor=cursor, limit=limit_of(limit, 20, 100))
    items = []
    for it in res.get("items") or []:
        items.append({k: v for k, v in {
            "kind": _SRC_VI.get(it.get("source_type"), it.get("source_label") or it.get("source_type")),
            "title": it.get("title"),
            "detail": it.get("subtitle") or None,
            "action": it.get("action_label") or None,
            "group": it.get("bucket"),
            "due": (it.get("due_at") or "")[:16] or None,
            "reference": it.get("source_id"),
            "link": link(it.get("action_url")),
        }.items() if v not in (None, "")})
    return {"total": res.get("total"), "counts": res.get("counts"),
            "by_source": res.get("source_counts"), "items": items,
            "next_cursor": res.get("next_cursor"),
            "note": "Chỉ xem. Duyệt / từ chối phiếu hãy mở link trên web."}


def my_requests():
    from ecentric_workspace.action_center import api

    res = api.get_my_requests_summary() or {}
    return {"counts": res.get("counts"), "total": res.get("count"),
            "items": [{"request": i.get("request"), "type": i.get("subtitle"), "title": i.get("title"),
                       "status": i.get("status"), "current_level": i.get("current_level"),
                       "submitted_at": (i.get("submitted_at") or "")[:16],
                       "reference": i.get("source_id"), "link": link(i.get("action_url"))}
                      for i in res.get("items") or []]}


def get_request(reference=None, request=None):
    """reference = "<DocType>/<tên>" (lấy từ my_action_items / my_requests), hoặc request = tên EC Approval Request."""
    from ecentric_workspace.approval_center.shared import registry
    from ecentric_workspace.approval_center.shared.facade import APPROVAL_FACADE
    from ecentric_workspace.action_center.resolvers import build_approval_url

    if request and not reference:
        r = frappe.db.get_value("EC Approval Request", request,
                                ["reference_doctype", "reference_name"], as_dict=True)
        if not r:
            raise ToolError("Không tìm thấy phiếu %s." % request)
        reference = "%s/%s" % (r.reference_doctype, r.reference_name)
    if not reference or "/" not in str(reference):
        raise ToolError("Cần reference dạng '<DocType>/<tên phiếu>' (lấy từ my_action_items hoặc my_requests).")
    doctype, name = str(reference).split("/", 1)
    try:
        definition = registry.get_definition_for_doctype(doctype)
    except KeyError:
        raise ToolError("Loại phiếu %s chưa đọc được qua Claude (phiếu cũ MSO/SO/PO). Mở trên web: %s"
                        % (doctype, link(build_approval_url(doctype, name)))) from None
    d = APPROVAL_FACADE.detail(definition, name) or {}
    return _compact_detail(d, doctype, name, link(build_approval_url(doctype, name)))


_SKIP = {"doctype", "owner", "modified_by", "docstatus", "idx", "_user_tags", "_comments", "_assign",
         "_liked_by", "_seen", "amended_from", "naming_series", "lft", "rgt"}


def _compact_detail(d, doctype, name, url):
    doc = d.get("business") or {}   # đã qua business_redactor của từng loại phiếu
    appr = d.get("approval") or {}
    fields = {}
    if isinstance(doc, dict):
        for k, v in doc.items():
            if k in _SKIP or k.startswith("_") or v in (None, "", 0, [], {}):
                continue
            if isinstance(v, list):
                v = [{kk: vv for kk, vv in (x.items() if isinstance(x, dict) else [])
                      if kk not in _SKIP and kk not in ("name", "parent", "parentfield", "parenttype")
                      and vv not in (None, "")} for x in v[:30]]
            elif isinstance(v, str) and len(v) > 600:
                v = plain(v, 600)
            fields[k] = v
    return {
        "reference": doctype + "/" + name,
        "status": appr.get("status_label") or appr.get("approval_status"),
        "current_level": appr.get("current_level"),
        "fields": fields,
        "levels": [{k: x.get(k) for k in ("level_no", "level_name", "level_status", "due_at")}
                   for x in d.get("levels") or []],
        "approvers": [{k: x.get(k) for k in ("level_no", "approver", "status", "decided_at", "comment")
                       if x.get(k) not in (None, "")} for x in d.get("approvers") or []],
        "timeline": [{k: x.get(k) for k in ("action_time", "actor", "action", "level_name", "comment")
                      if x.get(k) not in (None, "")} for x in (d.get("timeline") or [])[-15:]],
        "attachments": [a.get("file_name") for a in d.get("attachments") or [] if isinstance(a, dict)],
        "link": url,
        "note": "Chỉ xem. Duyệt / từ chối hãy mở link trên web.",
    }


# ============================================================ Báo cáo tuần (chỉ đọc)
WTU = "Weekly Team Update"
_WTU_LIST = ["name", "week_label", "employee", "employee_name", "department", "status",
             "overall_status", "submitted_at", "due_at", "overall_ai_score", "late_submission"]
_WTU_TEXT = ["what_done", "plan_next_week", "blockers_help", "mood", "ai_tools_used", "ai_use_case",
             "ai_summary", "ai_feedback"]


def _fields_that_exist(names):
    meta = frappe.get_meta(WTU)
    return [f for f in names if f == "name" or meta.has_field(f)]


def list_weekly_reports(week=None, employee=None, department=None, limit=20):
    """frappe.get_list -> đi qua permission_query_conditions (weekly_report/permissions.py)."""
    filters = {}
    if week:
        filters["week_label"] = ["like", "%" + str(week).strip() + "%"]
    if employee:
        filters["employee"] = str(employee).strip()
    if department:
        filters["department"] = ["like", "%" + str(department).strip() + "%"]
    rows = frappe.get_list(WTU, filters=filters, fields=_fields_that_exist(_WTU_LIST),
                           order_by="week_label desc, modified desc",
                           limit_page_length=limit_of(limit, 20, 100))
    for r in rows:
        for k in ("submitted_at", "due_at"):
            if r.get(k):
                r[k] = str(r[k])[:16]
        r["link"] = link("/weekly-update?view=" + r["name"])
    return {"filters": {"week": week, "employee": employee, "department": department},
            "reports": rows, "shown": len(rows),
            "note": "Chỉ thấy báo cáo mà bạn có quyền xem (của mình, cấp dưới, phòng ban theo luật hiện hành)."}


def get_weekly_report(name):
    from ecentric_workspace.weekly_report import permissions as wperm

    if not frappe.db.exists(WTU, name):
        raise ToolError("Không tìm thấy báo cáo %s." % name)
    wperm.assert_can_read(name)
    doc = frappe.get_doc(WTU, name)
    out = {"report": name, "link": link("/weekly-update?view=" + name)}
    for f in _fields_that_exist(_WTU_LIST + _WTU_TEXT):
        v = doc.get(f)
        if v not in (None, ""):
            out[f] = plain(v, 2500) if f in _WTU_TEXT else (str(v)[:16] if f.endswith("_at") else v)
    decks = doc.get("deck_urls") or doc.get("slide_deck")
    if decks:
        out["slides"] = decks
    return out


# ============================================================ registry
def _schema(props, required=()):
    return {"type": "object", "properties": props, "required": list(required), "additionalProperties": False}


_S = {"type": "string"}
_TASK = {"type": "string", "description": "Mã việc, ví dụ TASK-2026-01234 (lấy từ my_tasks)."}

TOOLS = [
    # -------- PM: đọc
    {"name": "my_tasks", "title": "Việc cần làm", "annotations": dict(READ, title="Việc cần làm"),
     "description": ("Danh sách việc của người dùng theo ĐÚNG thứ tự trên màn 'Việc cần làm' của ERP "
                     "(Quá hạn → Hôm nay → Ngày mai → Còn lại tuần này → Tuần sau → Chưa có hạn; trong nhóm theo "
                     "ưu tiên). view='me' = việc giao cho tôi (kèm việc chờ tôi Nhận/đồng ý); view='give' = việc "
                     "tôi giao cho người khác (kèm đề xuất dời hạn chờ tôi trả lời). Dùng khi hỏi 'hôm nay tôi làm "
                     "gì', 'việc nào trễ', 'tôi đã giao gì cho ai'."),
     "inputSchema": _schema({
         "view": {"type": "string", "enum": ["me", "give"], "default": "me"},
         "include_personal": {"type": "boolean", "default": False,
                              "description": "Gồm cả việc trong dự án nhật ký cá nhân."},
         "limit": {"type": "integer", "default": 40, "minimum": 1, "maximum": 200}}),
     "handler": my_tasks},
    {"name": "get_task", "title": "Chi tiết việc", "annotations": dict(READ, title="Chi tiết việc"),
     "description": "Chi tiết một việc: mô tả, người giao, người nhận, hạn, việc con, bình luận gần đây.",
     "inputSchema": _schema({"task": _TASK}, ["task"]), "handler": get_task},
    {"name": "find_people", "title": "Tìm người", "annotations": dict(READ, title="Tìm người"),
     "description": ("Tìm email đồng nghiệp theo tên (không cần dấu). BẮT BUỘC dùng trước create_task khi người "
                     "dùng chỉ nói tên, rồi HỎI LẠI cho chắc: 'Lan là Nguyễn Thị Lan (lan.nguyen@...) đúng không?'. "
                     "Nhiều người trùng tên thì liệt kê cho người dùng chọn, không tự đoán."),
     "inputSchema": _schema({"query": {"type": "string", "description": "Tên hoặc một phần email."},
                             "limit": {"type": "integer", "default": 8}}, ["query"]),
     "handler": find_people},
    # -------- PM: ghi (an toàn)
    {"name": "create_task", "title": "Giao việc", "annotations": dict(WRITE, title="Giao việc"),
     "description": ("Tạo/giao một việc (như ô giao việc 1 dòng trên ERP; không thuộc dự án). assignees = list email "
                     "(bỏ trống = giao cho chính mình). need_acceptance=true = 'Cần đồng ý' (người nhận phải bấm Nhận). "
                     "Nhiều người + one_per_person=true = mỗi người một việc con. Tóm tắt lại cho người dùng xác nhận "
                     "trước khi gọi nếu yêu cầu chưa rõ người nhận hoặc hạn."),
     "inputSchema": _schema({
         "subject": {"type": "string", "description": "Tên việc, ngắn gọn."},
         "assignees": {"type": "array", "items": _S, "description": "Email người nhận."},
         "due_date": {"type": "string", "description": "Hạn YYYY-MM-DD. Không nói hạn thì để trống hoặc hỏi."},
         "due_time": {"type": "string", "description": "Giờ hạn HH:MM (tuỳ chọn)."},
         "priority": {"type": "string", "enum": list(PRIORITIES), "default": "Medium"},
         "description": {"type": "string"},
         "need_acceptance": {"type": "boolean", "default": False},
         "one_per_person": {"type": "boolean", "default": True}}, ["subject"]),
     "handler": create_task},
    {"name": "complete_task", "title": "Đánh dấu Xong", "annotations": dict(WRITE, title="Đánh dấu Xong"),
     "description": ("Bấm 'Xong' cho một việc. Nếu việc cần người giao kiểm tra thì chuyển sang Chờ duyệt. "
                     "Báo lỗi nếu còn bước checklist bắt buộc hoặc việc con đang mở."),
     "inputSchema": _schema({"task": _TASK}, ["task"]), "handler": complete_task},
    {"name": "start_task", "title": "Bắt đầu việc", "annotations": dict(WRITE, title="Bắt đầu việc"),
     "description": "Chuyển việc sang 'Đang làm' (In Progress).",
     "inputSchema": _schema({"task": _TASK}, ["task"]), "handler": start_task},
    {"name": "request_deadline_change", "title": "Xin dời hạn",
     "annotations": dict(WRITE, title="Xin dời hạn"),
     "description": "Người được giao xin người giao dời hạn. Hạn chỉ đổi khi người giao đồng ý. Bắt buộc có lý do.",
     "inputSchema": _schema({"task": _TASK, "new_due": {"type": "string", "description": "YYYY-MM-DD"},
                             "reason": _S}, ["task", "new_due", "reason"]),
     "handler": request_deadline_change},
    {"name": "remind_assignees", "title": "Nhắc người làm",
     "annotations": dict(WRITE, title="Nhắc người làm"),
     "description": "Người giao nhắc những người chưa xong một việc (tối đa 1 lần/giờ/người).",
     "inputSchema": _schema({"task": _TASK}, ["task"]), "handler": remind_assignees},
    {"name": "comment_on_task", "title": "Bình luận việc",
     "annotations": dict(WRITE, title="Bình luận việc"),
     "description": "Thêm bình luận (chữ thường) vào một việc. Mọi người trong việc sẽ thấy.",
     "inputSchema": _schema({"task": _TASK, "text": _S}, ["task", "text"]), "handler": comment_on_task},
    # -------- Approval Center: chỉ đọc
    {"name": "my_action_items", "title": "Việc chờ tôi xử lý",
     "annotations": dict(READ, title="Việc chờ tôi xử lý"),
     "description": ("Mọi thứ đang chờ người dùng xử lý trên ERP (như chuông 'Việc của tôi'): phiếu chờ duyệt, "
                     "phiếu cần xử lý, báo cáo tuần phải nộp, việc PM. Chỉ xem: Claude KHÔNG duyệt/từ chối được, "
                     "hãy đưa link để người dùng mở."),
     "inputSchema": _schema({"limit": {"type": "integer", "default": 20, "maximum": 100},
                             "cursor": {"type": "string", "description": "next_cursor của lần gọi trước."}}),
     "handler": my_action_items},
    {"name": "my_requests", "title": "Phiếu tôi đã gửi", "annotations": dict(READ, title="Phiếu tôi đã gửi"),
     "description": "Các phiếu đề nghị người dùng đã gửi và đang chờ duyệt / cần bổ sung thông tin.",
     "inputSchema": _schema({}), "handler": my_requests},
    {"name": "get_request", "title": "Chi tiết phiếu", "annotations": dict(READ, title="Chi tiết phiếu"),
     "description": ("Chi tiết một phiếu trên Approval Center: nội dung, các cấp duyệt, ai đã duyệt, lịch sử. "
                     "reference = '<DocType>/<tên>' lấy từ my_action_items hoặc my_requests."),
     "inputSchema": _schema({"reference": _S, "request": {"type": "string",
                                                          "description": "Hoặc tên EC Approval Request."}}),
     "handler": get_request},
    # -------- Báo cáo tuần: chỉ đọc
    {"name": "list_weekly_reports", "title": "Danh sách báo cáo tuần",
     "annotations": dict(READ, title="Danh sách báo cáo tuần"),
     "description": ("Liệt kê báo cáo tuần người dùng được xem (của mình, cấp dưới...). Lọc theo tuần "
                     "(vd '2026-W46'), mã nhân viên, phòng ban."),
     "inputSchema": _schema({"week": _S, "employee": {"type": "string", "description": "Mã nhân viên, vd NV00162"},
                             "department": _S, "limit": {"type": "integer", "default": 20, "maximum": 100}}),
     "handler": list_weekly_reports},
    {"name": "get_weekly_report", "title": "Đọc báo cáo tuần",
     "annotations": dict(READ, title="Đọc báo cáo tuần"),
     "description": "Nội dung một báo cáo tuần: đã làm, kế hoạch tuần sau, vướng mắc, tóm tắt và nhận xét AI.",
     "inputSchema": _schema({"name": {"type": "string", "description": "Mã báo cáo, vd WTU-2026-W46-NV00162"}},
                            ["name"]),
     "handler": get_weekly_report},
]



# ============================================================ đợt 2: tệp, lên nháp mọi form, ký số, xuất dữ liệu
def _lazy(module, fn):
    def call(**kw):
        import importlib
        return getattr(importlib.import_module("ecentric_workspace.claude_mcp." + module), fn)(**kw)
    call.__name__ = fn
    return call


_REF = {"type": "string", "description": "'<DocType>/<mã phiếu>' do create_draft_request trả về."}
_FILE = {"type": "string", "description": "Mã tệp (file) từ list_my_uploads, hoặc tên tệp."}
_DATE = {"type": "string", "description": "YYYY-MM-DD"}

TOOLS += [
    # -------- tệp
    {"name": "list_my_uploads", "title": "Tệp tôi vừa tải", "annotations": dict(READ, title="Tệp tôi vừa tải"),
     "description": ("Tệp người dùng vừa tải lên ERP (chưa gắn vào phiếu) + upload_link. Claude KHÔNG nhận được tệp "
                     "thả trong khung chat; muốn đưa tệp vào ERP (gắn phiếu, đọc hợp đồng) hãy gửi upload_link cho người "
                     "dùng, chờ họ thả tệp rồi gọi lại công cụ này."),
     "inputSchema": _schema({"hours": {"type": "integer", "default": 24},
                             "include_attached": {"type": "boolean", "default": False}}),
     "handler": _lazy("files", "list_my_uploads")},
    {"name": "read_file", "title": "Đọc tệp", "annotations": dict(READ, title="Đọc tệp"),
     "description": ("Đọc chữ trong một tệp trên ERP (PDF có lớp chữ, DOCX, XLSX, TXT/CSV). PDF scan thì báo scanned=true: "
                     "nhờ người dùng thả chính tệp đó vào khung chat để Claude đọc bằng mắt."),
     "inputSchema": _schema({"file": _FILE, "max_chars": {"type": "integer", "default": 40000}}, ["file"]),
     "handler": _lazy("files", "read_file")},
    # -------- Approval Center: lên nháp (không gửi)
    {"name": "list_forms", "title": "Các loại phiếu", "annotations": dict(READ, title="Các loại phiếu"),
     "description": "Các loại phiếu Approval Center người dùng được tạo (mã form dùng cho get_form / create_draft_request).",
     "inputSchema": _schema({}), "handler": _lazy("approvals", "list_forms")},
    {"name": "get_form", "title": "Cấu trúc phiếu", "annotations": dict(READ, title="Cấu trúc phiếu"),
     "description": ("Các ô của một loại phiếu: tên ô, kiểu, bắt buộc, lựa chọn hợp lệ, gợi ý; ô người lập phải tự làm "
                     "trên web; có ký số hay không. LUÔN gọi trước create_draft_request."),
     "inputSchema": _schema({"code": {"type": "string", "description": "Mã form, vd PAYMENT_REQUEST"}}, ["code"]),
     "handler": _lazy("approvals", "get_form")},
    {"name": "create_draft_request", "title": "Lưu nháp phiếu", "annotations": dict(WRITE, title="Lưu nháp phiếu"),
     "description": ("Tạo MỘT phiếu NHÁP (không gửi) với các ô đã biết + gắn tệp đã tải lên. Trả về ô còn thiếu: "
                     "missing_ask_user (hỏi người dùng rồi update_draft_request) và missing_user_fills_on_web (người dùng "
                     "tự chọn trên form). Nhiều hồ sơ thì gọi nhiều lần, mỗi hồ sơ một phiếu. Claude không bao giờ gửi "
                     "phiếu: người dùng mở link và tự bấm Gửi."),
     "inputSchema": _schema({"code": _S, "fields": {"type": "object", "description": "{tên_ô: giá_trị} theo get_form"},
                             "files": {"type": "array", "items": _S, "description": "Mã tệp từ list_my_uploads"}},
                            ["code"]),
     "handler": _lazy("approvals", "create_draft_request")},
    {"name": "update_draft_request", "title": "Sửa phiếu nháp", "annotations": dict(WRITE, title="Sửa phiếu nháp"),
     "description": "Điền thêm / sửa ô hoặc gắn thêm tệp cho một phiếu NHÁP của chính người dùng.",
     "inputSchema": _schema({"reference": _REF, "fields": {"type": "object"},
                             "files": {"type": "array", "items": _S}}, ["reference"]),
     "handler": _lazy("approvals", "update_draft_request")},
    {"name": "get_signing_setup", "title": "Thiết lập ký số", "annotations": dict(READ, title="Thiết lập ký số"),
     "description": ("Phiếu nháp có ký số: danh sách người ký (slot_key), các tệp cần ký, ô ký đã đặt, và các dòng chữ "
                     "mốc trong PDF (anchors: 'ĐẠI DIỆN BÊN A', 'Người đề nghị'...) để đặt ô ký."),
     "inputSchema": _schema({"reference": _REF}, ["reference"]), "handler": _lazy("approvals", "get_signing_setup")},
    {"name": "place_signature", "title": "Đặt ô ký", "annotations": dict(WRITE, title="Đặt ô ký"),
     "description": ("Đặt ô chữ ký cho một người ký trên một tệp PDF của phiếu nháp, ngay dưới dòng chữ mốc anchor_text "
                     "(lấy từ get_signing_setup; occurrence = lần xuất hiện thứ mấy). Chỉ đặt khi chắc chỗ đó là của "
                     "người ký này (vd bên eCentric là Bên A hay Bên B: đọc hợp đồng trước). Không chắc thì để người dùng tự kéo."),
     "inputSchema": _schema({"reference": _REF, "file": _FILE, "slot_key": _S, "anchor_text": _S,
                             "occurrence": {"type": "integer", "default": 1},
                             "page": {"type": "integer"}, "x": {"type": "number"}, "y": {"type": "number"},
                             "width": {"type": "number", "default": 150}, "height": {"type": "number", "default": 60}},
                            ["reference", "file", "slot_key"]),
     "handler": _lazy("approvals", "place_signature")},
    {"name": "set_requires_signature", "title": "Tệp cần ký / kèm theo",
     "annotations": dict(WRITE, title="Tệp cần ký / kèm theo"),
     "description": "Đánh dấu một tệp của phiếu nháp là CẦN KÝ (true) hay chỉ là chứng từ kèm theo (false).",
     "inputSchema": _schema({"reference": _REF, "file": _FILE, "requires_signature": {"type": "boolean"}},
                            ["reference", "file", "requires_signature"]),
     "handler": _lazy("approvals", "set_requires_signature")},
    # -------- xuất dữ liệu
    {"name": "export_requests", "title": "Xuất danh sách phiếu", "annotations": dict(READ, title="Xuất danh sách phiếu"),
     "description": ("Xuất phiếu của một loại form theo bộ lọc (ngày gửi, trạng thái, phòng ban, người đề nghị, tìm kiếm), "
                     "đúng phạm vi người dùng được xem, có ghi vết. Trả rows (tối đa 300/lần, dùng offset lấy tiếp) + link "
                     "tệp XLSX đầy đủ. Người dùng cần mẫu riêng: dựng lại từ rows/tệp theo mẫu họ đưa."),
     "inputSchema": _schema({"code": _S, "date_from": _DATE, "date_to": _DATE,
                             "status": {"type": "string", "description": "Pending / Approved / Rejected / Information Required / Cancelled"},
                             "department": _S, "requester": {"type": "string", "description": "email"},
                             "search": _S, "extra_filters": {"type": "object", "description": "Lọc theo ô riêng của form, vd {\"ec_brand\": \"LOF-VN\"}"},
                             "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 100},
                             "make_file": {"type": "boolean", "default": True}}, ["code"]),
     "handler": _lazy("exports", "export_requests")},
    {"name": "payment_status", "title": "Tình trạng thanh toán", "annotations": dict(READ, title="Tình trạng thanh toán"),
     "description": ("Đề nghị thanh toán và tình trạng chi: số tiền, người nhận, ngày đề nghị, trạng thái chi, ngày chi/UNC, "
                     "brand, loại chi phí, kỳ chi phí. Lọc theo ngày gửi, trạng thái duyệt, đã chi/chưa chi. Kèm tệp XLSX."),
     "inputSchema": _schema({"date_from": _DATE, "date_to": _DATE, "approval_status": _S,
                             "paid": {"type": "boolean", "description": "true = đã chi xong, false = chưa"},
                             "offset": {"type": "integer", "default": 0}, "limit": {"type": "integer", "default": 100},
                             "make_file": {"type": "boolean", "default": True}}),
     "handler": _lazy("exports", "payment_status")},
    {"name": "pnl_data", "title": "Dữ liệu PnL", "annotations": dict(READ, title="Dữ liệu PnL"),
     "description": ("Số liệu Dashboard PnL theo quyền người dùng: dataset='costs' (chi phí + lương ước tính, tổng hợp, "
                     "không lộ lương cá nhân) hoặc 'revenue_pnl' (doanh thu / PnL). Lọc theo khoảng tháng."),
     "inputSchema": _schema({"dataset": {"type": "string", "enum": ["costs", "revenue_pnl"], "default": "costs"},
                             "date_from": _DATE, "date_to": _DATE,
                             "brands": {"type": "array", "items": _S, "description": "(costs) kịch bản theo brand"}}),
     "handler": _lazy("exports", "pnl_data")},
]


def instructions():
    from frappe.utils import get_fullname, nowdate

    user = frappe.session.user
    return "\n".join([
        "Bạn đang nối vào ERP nội bộ eCentric (eCentric Workspace) với tư cách %s (%s)." % (get_fullname(user), user),
        "Hôm nay là %s (giờ Việt Nam). Trả lời bằng tiếng Việt, ngắn gọn." % nowdate(),
        "Mọi quyền đọc/ghi đúng như khi người này tự bấm trên web; công cụ báo lỗi quyền thì nói lại cho họ, đừng thử đường khác.",
        "GIAO VIỆC: chỉ có tên thì find_people, rồi xác nhận lại email với người dùng ('ABC là abc@... đúng không?'); "
        "hỏi thêm hạn / mức ưu tiên / có cần người nhận đồng ý nếu chưa rõ; đổi 'thứ 6', 'mai' sang YYYY-MM-DD; tóm tắt rồi mới create_task.",
        "LÊN PHIẾU: list_forms -> get_form -> lấy tệp (list_my_uploads; chưa có thì gửi upload_link) -> read_file từng tệp -> "
        "liệt kê cho người dùng các ô đọc được và ô còn thiếu của TỪNG hồ sơ, hỏi gộp một lần -> create_draft_request mỗi hồ sơ một phiếu "
        "-> form có ký số: get_signing_setup + place_signature -> báo danh sách link nháp. KHÔNG bao giờ gửi phiếu; ô cam kết "
        "(missing_user_fills_on_web) người dùng tự chọn trên web.",
        "XUẤT DỮ LIỆU: export_requests / payment_status / pnl_data. Người dùng đưa mẫu (cột, thứ tự, định dạng) thì dựng file theo "
        "mẫu từ dữ liệu trả về; luôn kèm link tệp XLSX gốc.",
        "Trước các thao tác ghi hãy chắc người dùng thật sự muốn làm. Không duyệt/từ chối phiếu được: đưa link để họ làm trên web.",
        "Khi liệt kê việc, giữ đúng thứ tự công cụ trả về (đó là thứ tự ưu tiên của công ty) và kèm link.",
    ])
