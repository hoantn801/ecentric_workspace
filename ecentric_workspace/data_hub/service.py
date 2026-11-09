# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu - phia NHAN VIEN + phan doc dung chung: gui yeu cau, xem danh sach / chi tiet /
Gantt (moi nhan vien doc duoc moi yeu cau - PO chot 09/11), nhan tin, theo doi, nghiem thu, huy yeu
cau cua minh, tai tep. Phia team Data (nhan viec, doi han, tam dung, hoan tat) o ops_service.py.

Moi ham nhan `user` do api.py / trang www lay tu PHIEN - khong bao gio tu tham so HTTP. Ham nao cung
kiem quyen TRUOC khi doc / ghi (repository dung ignore_permissions). `repo` / `pm` tiem vao duoc:
test chay bang repo gia + PM gia, khong can bench.
"""
import json

from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D


class NotFound(Exception):
    """Khong co yeu cau nay."""


class Forbidden(Exception):
    """Nguoi nay khong duoc lam viec nay."""


class DataHubError(Exception):
    """Loi nguoi dung gay ra - api tra success False kem thong diep."""


def _repo(repo):
    if repo is not None:
        return repo
    from ecentric_workspace.data_hub import repository
    return repository


def _fail(errors):
    raise DataHubError(" ".join(errors) if isinstance(errors, (list, tuple)) else errors)


# ------------------------------------------------------------------ vai tro ---------------
def team_role(repo):
    return repo.settings().get("data_team_role") or C.DEFAULT_DATA_TEAM_ROLE


def is_team(repo, user):
    return bool(user) and user != "Guest" and team_role(repo) in repo.roles(user)


def can_operate(repo, user):
    """Team Data (role trong Settings) hoac System Manager: moi thao tac dieu phoi."""
    return is_team(repo, user) or repo.is_admin(user)


def is_internal(repo, user):
    """Nhan vien eCentric (ho so Active) / team Data / quan tri - doc duoc moi yeu cau."""
    if not user or user == "Guest":
        return False
    return bool(repo.employee(user)) or can_operate(repo, user)


def is_rule_viewer(repo, user):
    approver = repo.settings().get("rule_approver") or ""
    return can_operate(repo, user) or (bool(approver) and user == approver)


def require_internal(repo, user):
    if not is_internal(repo, user):
        raise Forbidden("Chỉ nhân viên eCentric mới dùng được Trung tâm Dữ liệu.")


def require_operate(repo, user):
    if not can_operate(repo, user):
        raise Forbidden("Chỉ team Data mới làm được việc này.")


def members(repo):
    return repo.users_with_role(team_role(repo))


def rules(repo):
    return D.rules_view(repo.rule_set())


def load(repo, code):
    t = repo.get(code)
    if not t:
        raise NotFound(code)
    return t


def follower_users(t):
    return [f["user"] for f in t.get("followers") or () if f.get("user")]


def can_message(repo, user, t):
    return (user == t.get("requester") or user == t.get("assignee") or user in follower_users(t)
            or can_operate(repo, user))


# ------------------------------------------------------------------ nhat ky ---------------
def log(repo, code, event, actor, source=C.SRC_HUB, from_value="", to_value="", note=""):
    return repo.insert_log({"ticket": code, "event": event, "actor": actor or C.SYSTEM_USER, "source": source,
                            "from_value": str(from_value or "")[:140], "to_value": str(to_value or "")[:140],
                            "note": (note or "")[:C.REASON_MAX]})


# ------------------------------------------------------------------ gui yeu cau -----------
def create(user, data, files=None, repo=None):
    """Gui yeu cau du lieu - thang team Data (khong qua truong phong). -> {code}."""
    repo = _repo(repo)
    require_internal(repo, user)
    today = repo.today()
    try:
        v = D.normalize_create(data or {}, repo.sent_today(user, today))
    except D.Invalid as e:
        _fail(e.errors)
    errs = D.check_files(files or ())
    if errs:
        _fail(errs)
    r = rules(repo)
    hol = repo.holidays()
    emp = repo.employee(user) or {}
    v.update({
        "kind": C.KIND_REQUEST, "naming_series": C.SERIES[C.KIND_REQUEST], "requester": user,
        "requester_department": emp.get("department") or "", "status": C.ST_WAITING,
        "priority": "", "rule_version": r["version"],
        "sla_days": D.ticket_sla_days(r, v["request_type"], v["proposed_priority"]),
        "intake_due_date": D.intake_due(today, r, hol),
    })
    code = repo.insert_ticket(v, files=files)
    log(repo, code, C.EV_CREATED, user, to_value=v["proposed_priority"],
        note=("Đề xuất Khẩn: " + v["urgent_reason"]) if v["urgent_reason"] else "")
    from ecentric_workspace.data_hub import notify
    notify.new_request(repo, repo.get(code), user)
    return {"code": code}


# ------------------------------------------------------------------ trao doi --------------
def send_message(user, code, body, mentions=None, files=None, repo=None):
    repo = _repo(repo)
    require_internal(repo, user)
    t = load(repo, code)
    if not can_message(repo, user, t):
        raise Forbidden("Bấm “Theo dõi” để tham gia trao đổi về yêu cầu này.")
    body = D.clean_text(body, C.MESSAGE_MAX + 1)
    if len(body) > C.MESSAGE_MAX:
        _fail("Tin nhắn dài quá {0} ký tự.".format(C.MESSAGE_MAX))
    if not body and not files:
        _fail("Chưa có nội dung tin nhắn.")
    errs = D.check_files(files or ())
    if errs:
        _fail(errs)
    tagged = sorted(repo.enabled_users(D.clean_mentions(mentions)))
    msg = repo.insert_message({"ticket": code, "author": user, "body": body, "mentions": json.dumps(tagged)})
    if files:
        repo.add_files(code, files, user, message=msg)
    from ecentric_workspace.data_hub import notify
    notify.new_message(repo, t, user, body, tagged)
    return {"message": msg}


def follow(user, code, on=True, repo=None):
    repo = _repo(repo)
    require_internal(repo, user)
    t = load(repo, code)
    if on in ("0", "false", "False", 0, False):
        repo.remove_follower(code, user)
        following = False
    else:
        repo.add_follower(code, user, user)
        following = True
    n = len(set(follower_users(load(repo, code))))
    return {"following": following, "followers": n, "code": t["name"]}


# ------------------------------------------------------------------ nghiem thu / huy -------
def respond(user, code, verdict, reason="", repo=None, pm=None):
    """Nguoi gui nghiem thu: "Đạt" -> Hoan tat; "Chưa đạt" + ly do -> mo lai ve Dang xu ly."""
    repo = _repo(repo)
    require_internal(repo, user)
    t = repo.lock(code)
    if not t:
        raise NotFound(code)
    if user != t.get("requester") and not repo.is_admin(user):
        raise Forbidden("Chỉ người gửi yêu cầu mới nghiệm thu được.")
    if t.get("status") != C.ST_REVIEW:
        _fail("Yêu cầu không ở bước chờ nghiệm thu (đang: {0}). Tải lại trang để xem mới nhất.".format(
            t.get("status")))
    from ecentric_workspace.data_hub import ops_service as O
    if verdict == C.ACC_OK:
        O.apply_close(repo, t, user, C.ACC_OK)
        return {"status": C.ST_DONE}
    if verdict == C.ACC_FAIL:
        reason = D.clean_text(reason, C.REASON_MAX)
        if not reason:
            _fail("Ghi rõ chưa đạt ở điểm nào để team Data sửa.")
        O.apply_reopen(repo, t, user, reason, pm=pm)
        return {"status": C.ST_DOING}
    _fail("Chọn Đạt hoặc Chưa đạt.")


def cancel(user, code, reason="", repo=None, pm=None):
    """Nguoi gui huy khi con Cho tiep nhan; team Data huy bat ky luc nao (bat buoc ly do)."""
    repo = _repo(repo)
    require_internal(repo, user)
    t = repo.lock(code)
    if not t:
        raise NotFound(code)
    reason = D.clean_text(reason, C.REASON_MAX)
    st = t.get("status")
    if st in C.CLOSED:
        _fail("Yêu cầu đã đóng.")
    if can_operate(repo, user):
        if not reason:
            _fail("Huỷ yêu cầu cần ghi lý do (người gửi sẽ thấy).")
    elif user == t.get("requester"):
        if st != C.ST_WAITING:
            raise Forbidden("Team Data đã nhận việc - nhắn team Data trong khung trao đổi nếu muốn dừng.")
    else:
        raise Forbidden("Chỉ người gửi hoặc team Data mới huỷ được yêu cầu.")
    from ecentric_workspace.data_hub import ops_service as O
    O.apply_cancel(repo, t, user, reason, pm=pm)
    return {"status": C.ST_CANCELLED}


def download(user, code, row, repo=None):
    repo = _repo(repo)
    require_internal(repo, user)
    load(repo, code)
    got = repo.file_content(code, str(row or ""))
    if not got:
        raise NotFound(code)
    return got


# ------------------------------------------------------------------ hien thi --------------
def dept_label(dept):
    """"Commercial - EC" -> "Commercial"."""
    d = (dept or "").strip()
    return d.rsplit(" - ", 1)[0] if " - " in d else d


def priority_view(t):
    """(nhan, css, da_chot). Chua chot -> muc nguoi gui de xuat, kem "(đề xuất)"."""
    if t.get("priority"):
        return t["priority"], C.PRIORITY_CSS.get(t["priority"], "gray"), True
    p = t.get("proposed_priority") or C.PRI_NORMAL
    return p, C.PRIORITY_CSS.get(p, "gray"), False


def row_view(t, user, names, today, hol, followers=None):
    pri, pri_css, confirmed = priority_view(t)
    sla = D.sla_view(t, today, hol)
    st = t.get("status")
    due = D.effective_due(t)
    mine = user in (t.get("requester"), t.get("assignee")) or user in (followers or ())
    return {
        "code": t["name"], "title": t.get("title") or "", "kind": t.get("kind") or C.KIND_REQUEST,
        "type": t.get("request_type") or "", "type_short": C.TYPE_SHORT.get(t.get("request_type"), t.get("request_type") or ""),
        "requester": t.get("requester") or "", "requester_name": names.get(t.get("requester")) or t.get("requester") or "",
        "team": dept_label(t.get("requester_department")),
        "priority": pri, "priority_css": pri_css, "priority_confirmed": confirmed,
        "proposed_priority": t.get("proposed_priority") or "",
        "assignee": t.get("assignee") or "", "assignee_name": names.get(t.get("assignee")) or "",
        "status": st, "status_label": C.STATUS_LABEL.get(st, st), "status_css": C.STATUS_CSS.get(st, "gray"),
        "sla_label": sla["label"], "sla_pct": sla["pct"], "sla_css": sla["css"],
        "overdue": D.is_overdue(t, today), "due": D.iso(due), "created": str(t.get("creation") or "")[:19],
        "closed": str(t.get("closed_at") or "")[:19],
        "scope": "open" if st in C.OPEN else ("done" if st == C.ST_DONE else "cancel"),
        "mine": 1 if mine else 0,
        "search": " ".join([t["name"], t.get("title") or "", names.get(t.get("requester")) or "",
                            t.get("requester") or "", names.get(t.get("assignee")) or ""]).lower(),
    }


def _names_for(repo, rows, extra=()):
    users = set(extra)
    for t in rows:
        users.update([t.get("requester"), t.get("assignee")])
    return repo.full_names(users)


def list_rows(user, repo=None):
    """Bang danh sach (moi yeu cau du lieu, da sap xep)."""
    repo = _repo(repo)
    require_internal(repo, user)
    return _rows(repo, user)[0]


def _rows(repo, user):
    today, hol = repo.today(), repo.holidays()
    rows = repo.list_rows({"kind": C.KIND_REQUEST}, limit=C.LIST_LIMIT)
    names = _names_for(repo, rows, members(repo))
    fmap = repo.follower_map([t["name"] for t in rows])
    out = [row_view(t, user, names, today, hol, fmap.get(t["name"])) for t in D.sort_rows(rows, today)]
    return out, rows, names


def _timeline(t, logs, names):
    out = []
    for lg in logs:
        who = names.get(lg.get("actor")) or lg.get("actor") or C.SRC_SYSTEM
        if lg.get("actor") in (C.SYSTEM_USER, "", None):
            who = C.SRC_SYSTEM
        ev, a, b = lg.get("event"), lg.get("from_value") or "", lg.get("to_value") or ""
        if ev == C.EV_CREATED:
            text = who + " gửi yêu cầu" + (" · đề xuất " + b if b and b != C.PRI_NORMAL else "")
        elif ev == C.EV_ACCEPTED:
            text = who + " nhận việc · " + b
        elif ev == C.EV_ASSIGNEE:
            text = "%s đổi người xử lý %s → %s" % (who, names.get(a) or a or "—", names.get(b) or b or "—")
        elif ev == C.EV_DUE:
            text = "%s dời hạn %s → %s" % (who, D.fmt_date(a) or "—", D.fmt_date(b) or "—")
        elif ev == C.EV_START:
            text = "%s đổi ngày bắt đầu %s → %s" % (who, D.fmt_date(a) or "—", D.fmt_date(b) or "—")
        elif ev == C.EV_PRIORITY:
            text = "%s đổi ưu tiên %s → %s" % (who, a or "—", b or "—")
        elif ev == C.EV_PAUSE:
            text = who + " tạm dừng – chờ người gửi (đồng hồ hạn dừng)"
        elif ev == C.EV_RESUME:
            text = who + " tiếp tục" + (" · hạn mới " + D.fmt_date(b) if b else "")
        elif ev == C.EV_DONE:
            text = who + (" hoàn tất bổ sung data, các ô đã chuyển “Có”" if b == C.ST_DONE
                          else " hoàn tất, chờ người gửi nghiệm thu")
        elif ev == C.EV_ACCEPT_OK:
            text = who + " nghiệm thu: Đạt"
        elif ev == C.EV_ACCEPT_FAIL:
            text = who + " nghiệm thu: Chưa đạt – mở lại"
        elif ev == C.EV_AUTO_CLOSE:
            text = "Tự đóng: Đạt (tự động) – người gửi không phản hồi sau %d ngày làm việc" % C.AUTO_CLOSE_WORKING_DAYS
        elif ev == C.EV_CANCEL:
            text = who + " huỷ yêu cầu"
        elif ev == C.EV_PM:
            text = (b or "Đã tạo task /pm") if not a else "%s: %s" % (a, b)
        elif ev == C.EV_PM_ERROR:
            text = "Chưa đồng bộ được với /pm"
        else:
            text = "%s %s" % (who, ev or "")
        if lg.get("source") == C.SRC_PM and ev not in (C.EV_PM, C.EV_PM_ERROR):
            text += " (từ /pm)"
        out.append({"when": D.fmt_dt(lg.get("creation")), "text": text, "note": lg.get("note") or "",
                    "event": ev, "source": lg.get("source") or "", "warn": ev == C.EV_PM_ERROR})
    return out


def detail(user, code, repo=None):
    """Du lieu popup chi tiet (card thong tin + card trao doi). Quyen thao tac tinh san o `can`."""
    repo = _repo(repo)
    require_internal(repo, user)
    t = load(repo, code)
    today, hol = repo.today(), repo.holidays()
    msgs = repo.messages(code)
    logs = repo.logs(code)
    team = members(repo)
    fol = follower_users(t)
    users = set(fol) | set(team) | {t.get("requester"), t.get("assignee"), user}
    users.update(m.get("author") for m in msgs)
    users.update(lg.get("actor") for lg in logs)
    users.update(lg.get("from_value") for lg in logs if lg.get("event") == C.EV_ASSIGNEE)
    users.update(lg.get("to_value") for lg in logs if lg.get("event") == C.EV_ASSIGNEE)
    names = repo.full_names(users)
    row = row_view(t, user, names, today, hol, fol)
    operate = can_operate(repo, user)
    st = t.get("status")
    files_by_msg = {}
    attachments = []
    for f in t.get("attachments") or ():
        item = {"id": f["name"], "name": f.get("file_name") or "tệp", "size": int(f.get("file_size") or 0),
                "url": "/api/method/ecentric_workspace.data_hub.api.download?code=%s&file=%s" % (code, f["name"])}
        if f.get("message"):
            files_by_msg.setdefault(f["message"], []).append(item)
        else:
            attachments.append(item)
    messages = []
    for m in msgs:
        try:
            tagged = json.loads(m.get("mentions") or "[]")
        except ValueError:
            tagged = []
        messages.append({"id": m["name"], "author": m.get("author"),
                         "author_name": names.get(m.get("author")) or m.get("author") or "",
                         "body": m.get("body") or "", "when": D.fmt_dt(m.get("creation")),
                         "me": m.get("author") == user, "files": files_by_msg.get(m["name"], []),
                         "mentions": [{"user": u, "name": names.get(u) or u} for u in tagged]})
    due, orig = D.as_date(t.get("due_date")), D.as_date(t.get("original_due_date"))
    out = dict(row)
    out.update({
        "description": t.get("description") or "", "data_used": t.get("data_used") or "",
        "reference_link": t.get("reference_link") or "", "output_link": t.get("output_link") or "",
        "urgent_reason": t.get("urgent_reason") or "", "acceptance": t.get("acceptance") or "",
        "cancel_reason": t.get("cancel_reason") or "", "created_fmt": D.fmt_dt(t.get("creation")),
        "start": D.iso(t.get("start_date")), "start_fmt": D.fmt_date_full(t.get("start_date")),
        "due_date": D.iso(due), "due_fmt": D.fmt_date_full(due),
        "original_due_fmt": D.fmt_date_full(orig) if orig and due and orig != due else "",
        "intake_due_fmt": D.fmt_date_full(t.get("intake_due_date")),
        "due_change_count": int(t.get("due_change_count") or 0), "sla_days": int(t.get("sla_days") or 0),
        "pm_task": t.get("pm_task") or "", "pm_url": ("/pm#task/" + t["pm_task"]) if t.get("pm_task") else "",
        "attachments": attachments, "messages": messages, "timeline": _timeline(t, logs, names),
        "followers": [{"user": u, "name": names.get(u) or u} for u in fol],
        "following": user in fol, "status_label": C.STATUS_LABEL.get(st, st),
        "paused_since_fmt": D.fmt_dt(t.get("paused_since")),
        "can": {
            "message": can_message(repo, user, t), "follow": True,
            "respond": st == C.ST_REVIEW and (user == t.get("requester") or repo.is_admin(user)),
            "cancel": st not in C.CLOSED and (operate or (user == t.get("requester") and st == C.ST_WAITING)),
            "cancel_needs_reason": operate,
            "operate": operate and st in (C.ST_DOING, C.ST_PAUSED, C.ST_REVIEW),
            "accept": operate and st == C.ST_WAITING,
        },
    })
    if st == C.ST_WAITING:
        q = D.queue(repo.open_rows(), team, today, hol, rules(repo)).get(code)
        if q:
            out["queue"] = {"position": q["position"], "expected_start": D.fmt_date_full(q["expected_start"]),
                            "expected_due": D.fmt_date_full(q["expected_due"]), "sla_days": q["sla_days"]}
    if t.get("kind") == C.KIND_AVAILABILITY or t.get("request_type") in C.LIBRARY_TYPES:
        # Dot 2: DA -> san / kenh / cach lay; Power BI -> muc Thu vien bao cao (avail_service).
        from ecentric_workspace.data_hub import avail_service
        out.update(avail_service.ticket_extra(repo, t))
        if out.get("plan"):
            out["type_short"] = C.DA_TYPE_LABEL
            out["team"] = out["plan"].get("team") or out["team"]
    if operate:
        out["team_members"] = [{"user": u, "name": names.get(u) or u} for u in team]
        out["team_statuses"] = [{"value": s, "label": C.STATUS_LABEL.get(s, s)} for s in C.TEAM_SET_STATUSES
                                if D.can_team_move(st, s)]
        if out.get("plan") and not out["plan"].get("needs_acceptance"):
            for s_ in out["team_statuses"]:
                if s_["value"] == C.ST_REVIEW:
                    s_["label"] = "Hoàn tất (ô chuyển “Có”)"
        out["priorities"] = list(C.PRIORITIES)
        if st == C.ST_WAITING:
            out["accept_defaults"] = accept_defaults(repo, t, today, hol)
    return out


def accept_defaults(repo, t, today=None, hol=None, start=None, priority=None):
    today = today or repo.today()
    hol = repo.holidays() if hol is None else hol
    r = rules(repo)
    pri = priority if priority in C.PRIORITIES else D.queue_priority(t)
    s = D.as_date(start) or D.default_start(today, hol)
    n = D.ticket_sla_days(r, t.get("request_type"), pri)
    return {"start": s.isoformat(), "due": D.due_from(s, n, hol).isoformat(), "sla_days": n, "priority": pri,
            "proposed_priority": t.get("proposed_priority") or C.PRI_NORMAL,
            "urgent_reason": t.get("urgent_reason") or ""}


def preview_due(user, code, start=None, priority=None, repo=None):
    repo = _repo(repo)
    require_operate(repo, user)
    return accept_defaults(repo, load(repo, code), start=start, priority=priority)


def gantt_data(user, start=None, repo=None):
    repo = _repo(repo)
    require_internal(repo, user)
    return _gantt(repo, start)


def _gantt(repo, start=None, rows=None, names=None):
    today, hol = repo.today(), repo.holidays()
    team = members(repo)
    rows = rows if rows is not None else repo.list_rows(None, limit=C.LIST_LIMIT)
    q = D.queue([t for t in rows if t.get("status") in C.OPEN], team, today, hol, rules(repo))
    names = names if names is not None else _names_for(repo, rows, team)
    return D.gantt(rows, team, names, today, hol, start=start, q=q)


# ------------------------------------------------------------------ trang ------------------
def _boot(data):
    """JSON nhung trong trang: chong dong </script> lot ra."""
    return json.dumps(data, ensure_ascii=False, default=str).replace("<", "\\u003c")


def tabs(repo, user, active):
    out = [{"key": "req", "label": "Yêu cầu dữ liệu", "href": C.ROUTE},
           {"key": "avail", "label": "Data availability", "href": C.ROUTE_AVAIL}]
    if can_operate(repo, user):
        out.append({"key": "ops", "label": "Điều phối", "href": C.ROUTE_OPS})
    if is_rule_viewer(repo, user):
        out.append({"key": "rules", "label": "Quy tắc thời hạn", "href": C.ROUTE_RULES})
    for t in out:
        t["active"] = t["key"] == active
    return out


def _base(repo, user, tab):
    names = repo.full_names([user])
    return {"me": user, "me_name": names.get(user) or user, "tabs": tabs(repo, user, tab),
            "is_team": can_operate(repo, user), "today": repo.today().isoformat(), "denied": False,
            "open_missing": "", "open_code": ""}


def index_page(user, code="", view="", repo=None):
    """/du-lieu - KPI, loc, Danh sach | Gantt, popup chi tiet (?ma=DR-...)."""
    repo = _repo(repo)
    require_internal(repo, user)
    ctx = _base(repo, user, "req")
    rows, raw, names = _rows(repo, user)
    today = repo.today()
    r = rules(repo)
    ctx.update({
        "kpis": D.kpis(raw, today), "rows": rows, "view": "gantt" if view == "gantt" else "list",
        "types": list(C.REQUEST_TYPES), "priorities": list(C.PRIORITIES),
        "teams": sorted({x["team"] for x in rows if x["team"]}),
        "type_hints": D.type_hints(r), "intake_days": r["days"][C.RULE_INTAKE],
    })
    open_detail = None
    code = (code or "").strip().upper()
    if code:
        try:
            open_detail = detail(user, code, repo=repo)
        except NotFound:
            ctx["open_missing"] = code
    ctx["open_code"] = open_detail["code"] if open_detail else ""
    boot = {"page": "index", "me": user, "today": ctx["today"], "is_team": ctx["is_team"],
            "type_hints": ctx["type_hints"], "rows": rows, "open": open_detail,
            "gantt": _gantt(repo) if ctx["view"] == "gantt" else None,
            "missing": ctx.get("open_missing") or ""}
    ctx["boot_json"] = _boot(boot)
    return ctx


def ops_page(user, repo=None):
    """/du-lieu/dieu-phoi - kanban 4 cot cho team Data."""
    repo = _repo(repo)
    require_internal(repo, user)
    ctx = _base(repo, user, "ops")
    if not can_operate(repo, user):
        ctx["denied"] = True
        ctx["boot_json"] = _boot({"page": "ops", "denied": True})
        return ctx
    today, hol = repo.today(), repo.holidays()
    team = members(repo)
    rows = repo.list_rows(None, limit=C.LIST_LIMIT)
    names = _names_for(repo, rows, team)
    q = D.queue([t for t in rows if t.get("status") in C.OPEN], team, today, hol, rules(repo))
    cols = D.ops_columns([t for t in rows if t.get("kind", C.KIND_REQUEST) == C.KIND_REQUEST], today)
    view, accept = {}, {}
    for key, items in cols.items():
        out = []
        for t in items:
            rv = row_view(t, user, names, today, hol)
            if key == "waiting":
                qi = q.get(t["name"]) or {}
                rv["queue_pos"] = qi.get("position")
                rv["expected_start"] = D.fmt_date(qi.get("expected_start"))
                rv["urgent_reason"] = t.get("urgent_reason") or ""
                accept[t["name"]] = accept_defaults(repo, t, today, hol)
            if key == "done":
                rv["done_label"] = "Xong " + D.fmt_date(t.get("done_at") or t.get("closed_at")) + (
                    " · đúng hạn" if D.on_time(t) else " · trễ hạn")
            if key == "paused":
                rv["paused_since"] = D.fmt_date(t.get("paused_since"))
            out.append(rv)
        view[key] = out
    ctx.update({"cols": view, "team_members": [{"user": u, "name": names.get(u) or u} for u in team],
                "priorities": list(C.PRIORITIES)})
    ctx["boot_json"] = _boot({"page": "ops", "me": user, "today": ctx["today"], "is_team": True,
                              "team": ctx["team_members"], "priorities": ctx["priorities"], "accept": accept})
    return ctx


def rules_page(user, repo=None):
    """/du-lieu/quy-tac - bang quy tac dang ap dung (chi doc o dot 1; sua + duyet o dot 3)."""
    repo = _repo(repo)
    require_internal(repo, user)
    ctx = _base(repo, user, "rules")
    if not is_rule_viewer(repo, user):
        ctx["denied"] = True
        ctx["boot_json"] = _boot({"page": "rules", "denied": True})
        return ctx
    rs = repo.rule_set() or {}
    r = rules(repo)
    ctx.update({
        "rule_rows": [{"label": r["labels"][k], "days": r["days"][k], "note": r["notes"][k]}
                      for k, *_x in C.RULE_DEFAULTS],
        "mult": [{"label": p, "value": ("%g" % r["mult"][p]).replace(".", ",")} for p in C.PRIORITIES],
        "rule_version": rs.get("name") or "v1 (mặc định)", "rule_status": rs.get("status") or C.RULE_ACTIVE,
        "rule_from": D.fmt_date_full(rs.get("effective_from")),
        "history": [dict(h, from_fmt=D.fmt_date_full(h.get("effective_from"))) for h in repo.rule_history()],
    })
    ctx["boot_json"] = _boot({"page": "rules", "me": user})
    return ctx


def avail_page(user, view="", prefill_ticket="", repo=None):
    """/du-lieu/san-co - dot 2: avail_service.page (ma tran, de xuat, ke hoach DA, Thu vien bao cao)."""
    from ecentric_workspace.data_hub import avail_service
    return avail_service.page(user, view=view, prefill_ticket=prefill_ticket, repo=repo)
