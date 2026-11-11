# Copyright (c) 2026, eCentric and contributors
"""Trung tam Du lieu dot 2 - Data availability (/du-lieu/san-co) + de xuat data can crawl + ke hoach bo
sung (DA-) + do tuoi + Thu vien bao cao + goi y "da co dashboard tuong tu" (PO Hoan chot 09/11/2026).

Quyen (kiem o day, TRUOC khi goi repo - repo dung ignore_permissions):
  * doc trang / gui de xuat / goi y tieu de        -> nhan vien Active, team Data, System Manager
  * duyet / tu choi de xuat, len ke hoach, sua dong ma tran, them / sua / an muc thu vien
                                                  -> team Data (role trong Settings) + System Manager
Ke hoach bo sung = EC Data Ticket kind=availability (DA-...), dung LAI luong dot 1: tao o "Chờ tiếp
nhận" roi ops_service.accept (nguoi xu ly, bat dau, han; tao task /pm, len Gantt thanh xanh ngoc "DA").
Hoan tat:
  * DA do team Data tu len (khong tu de xuat)      -> dong luon (Hoàn tất), khong can nghiem thu;
  * DA tu de xuat da duyet (nguoi gui = nguoi de xuat) -> Chờ nghiệm thu, nguoi de xuat Đạt / Chưa đạt
    (3 ngay lam viec tu dong Dat) nhu yeu cau thuong.
Khi DA Hoan tat: cac o da chon bat kenh da chon + "cap nhat lan cuoi" = luc do (on_ticket_closed).
Yeu cau Power BI (moi / sua) "Đạt" co link ket qua -> tu them vao Thu vien bao cao (cung on_ticket_closed).
"""
import json
from urllib.parse import quote

from ecentric_workspace.data_hub import avail_domain as A
from ecentric_workspace.data_hub import constants as C
from ecentric_workspace.data_hub import domain as D
from ecentric_workspace.data_hub import service as S


def _repo(repo):
    """repo dot 1 (module repository) khong co ham dot 2 -> dung avail_repository (bao ca ham dot 1).
    Test truyen FakeRepo (co du ca hai)."""
    if repo is not None and hasattr(repo, "avail_rows"):
        return repo
    from ecentric_workspace.data_hub import avail_repository
    return avail_repository


def _fail(errors):
    S._fail(errors)


def _validate(fn, *a, **k):
    try:
        return fn(*a, **k)
    except D.Invalid as e:
        _fail(e.errors)


def _url(path=C.ROUTE_AVAIL):
    return path


def _send(repo, event, recipients, title, message, key, actor, url=C.ROUTE_AVAIL):
    sent = []
    for r in recipients or ():
        if not r or r == actor or r in sent or r in ("Guest", C.SYSTEM_USER):
            continue
        try:
            repo.notify(event, r, title, message, url, None, "datahub|%s|%s" % (key, r), actor=actor)
            sent.append(r)
        except Exception:
            repo.log_error("Data Hub notify %s" % key)
    return sent


def _stamp(repo):
    try:
        return repo.now().strftime("%Y%m%d%H%M%S%f")
    except Exception:
        return ""


# ------------------------------------------------------------------ doc: trang ------------
def _tickets_for(repo, rows, proposals):
    codes = {r.get("planned_ticket") for r in rows if r.get("planned_ticket")}
    codes |= {p.get("resulting_ticket") for p in proposals if p.get("resulting_ticket")}
    codes = [c for c in codes if c]
    if not codes:
        return {}
    return {t["name"]: t for t in repo.list_rows({"name": ["in", codes]})}


def view_data(repo, user):
    """Du lieu dung chung cho trang + test: ma tran, KPI, Can bo sung, de xuat, thu vien."""
    now, today = repo.now(), repo.today()
    rows = repo.avail_rows()
    props = repo.proposal_rows()
    tickets = _tickets_for(repo, rows, props)
    plans = A.open_plans(rows, tickets.values())
    users = {r.get("data_owner") for r in rows} | {p.get("proposer") for p in props} | \
        {p.get("decided_by") for p in props} | {t.get("assignee") for t in tickets.values()}
    team = S.members(repo)
    operate = S.can_operate(repo, user)
    lib = repo.library_rows(include_inactive=operate)
    users |= {x.get("report_owner") for x in lib} | set(team) | {user}
    names = repo.full_names({u for u in users if u})
    teams = A.matrix(rows, plans, now, names)
    pending = [p for p in props if p.get("status") == C.PROP_PENDING]
    shown = pending + [p for p in props if p.get("status") != C.PROP_PENDING][:C.PROPOSAL_RECENT]
    files = repo.proposal_files([p["name"] for p in shown])
    cov = A.coverage(rows, now)
    cov["pending"] = len(pending)
    cov["pending_late"] = sum(1 for p in pending if A.countdown(p.get("due_at"), now)[1])
    return {
        "today": today, "now": now, "rows": rows, "names": names, "teams": teams, "coverage": cov,
        "gaps": A.gaps(teams, props, tickets, names),
        "proposals": [A.proposal_view(p, now, names, tickets, _files_view(files.get(p["name"]), p["name"],
                                                                     can_see_proposal_files(repo, user, p)))
                      for p in shown],
        "library": [library_view(x, names) for x in lib],
        "team_members": [{"user": u, "name": names.get(u) or u} for u in team],
        "operate": operate, "tickets": tickets,
    }


def _files_view(rows, name, can):
    """Tep cua de xuat -> [{name, size, url}]; url chi co khi nguoi xem duoc tai."""
    out = []
    for f in rows or ():
        url = ""
        if can:
            url = "/api/method/ecentric_workspace.data_hub.api.download_proposal_file?name=%s&file=%s" % (
                quote(name), quote(f["name"]))
        out.append({"name": f["file_name"], "size": int(f.get("file_size") or 0), "url": url})
    return out


def library_view(x, names):
    return {"name": x["name"], "title": x.get("title") or "", "link": x.get("link") or "", "team": x.get("team") or "",
            "owner": x.get("report_owner") or "", "owner_name": names.get(x.get("report_owner")) or x.get("report_owner") or "",
            "data_sources": x.get("data_sources") or "", "from_ticket": x.get("from_ticket") or "",
            "tags": x.get("tags") or "", "active": bool(int(x.get("active") or 0)),
            "updated": D.fmt_date_full(x.get("modified")),
            "search": " ".join([x.get("title") or "", x.get("team") or "", x.get("tags") or "",
                                x.get("data_sources") or "", names.get(x.get("report_owner")) or "",
                                x.get("from_ticket") or ""]).lower()}


def plan_defaults(repo, start=None, priority=None):
    """Ngay bat dau mac dinh + ket thuc theo quy tac "Crawl data mới" (x he so muc) - o form Len ke hoach."""
    today, hol = repo.today(), repo.holidays()
    pri = priority if priority in C.PRIORITIES else C.PRI_NORMAL
    s = D.as_date(start) or D.default_start(today, hol)
    n = D.ticket_sla_days(S.rules(repo), C.DA_REQUEST_TYPE, pri)
    return {"start": s.isoformat(), "due": D.due_from(s, n, hol).isoformat(), "sla_days": n, "priority": pri}


def _prop_boot(p):
    """Chi tiet de xuat cho hop "Chi tiết" + "Lên kế hoạch" (JS ve, moi gia tri escape o JS)."""
    keys = ("name", "team", "department", "data_type", "platforms", "platform_text", "purpose", "urgency",
            "urgency_reason", "urgency_note", "frequency", "scope", "links", "channels", "channel_text", "range_text",
            "needed_by_fmt", "files", "proposer_name", "created_fmt", "label", "css", "reason", "decided_by_name",
            "ticket", "brief", "status")
    return {k: p.get(k) for k in keys}


def page(user, view="", prefill_ticket="", repo=None):
    """/du-lieu/san-co - ma tran + KPI + Can bo sung + de xuat (?xem=thu-vien: Thu vien bao cao)."""
    repo = _repo(repo)
    S.require_internal(repo, user)
    ctx = S._base(repo, user, "avail")
    v = view_data(repo, user)
    me = repo.employee(user) or {}
    dopts, _depts = dept_options(repo)
    teams_all = [t["team"] for t in v["teams"]]
    dtypes = sorted({g["data_type"] for g in A.groups_flat(v["teams"])}, key=lambda s: s.lower())
    others = sorted({c["platform"] for g in A.groups_flat(v["teams"]) for c in g["others"]})
    lib_teams = sorted({x["team"] for x in v["library"] if x["team"]})
    ctx.update({
        "sub": "library" if view in ("thu-vien", "library") else "matrix",
        "cov": v["coverage"], "mteams": v["teams"], "gaps": v["gaps"], "proposals": v["proposals"],
        "library": v["library"], "team_options": teams_all, "dtype_options": dtypes, "other_platforms": others,
        "lib_teams": lib_teams, "platforms": list(C.MAIN_PLATFORMS), "channels": [
            {"key": k, "field": C.CHANNEL_FIELD[k], "label": C.CHANNEL_LABEL[k]} for k in C.CHANNEL_KEYS],
        "methods": list(C.METHODS), "frequencies": list(C.FREQUENCIES), "urgencies": list(C.PROP_URGENCIES),
        "team_members": v["team_members"], "my_team": S.dept_label(me.get("department")),
        "departments": dopts, "my_department": me.get("department") or "",
        "prop_frequencies": list(C.PROP_FREQUENCIES), "dtype_new": C.DTYPE_NEW,
        "urgency_need_reason": list(C.PROP_URGENCY_NEED_REASON),
        "pending_count": v["coverage"]["pending"],
        "proposal_days": S.rules(repo)["days"][C.RULE_PROPOSAL],
        "lib_count": sum(1 for x in v["library"] if x["active"]),
    })
    boot = {"page": "avail", "me": user, "today": ctx["today"], "is_team": ctx["is_team"], "sub": ctx["sub"],
            "need_reason": list(C.PROP_URGENCY_NEED_REASON), "dtype_new": C.DTYPE_NEW,
            "channel_labels": {k: C.CHANNEL_SHORT[k] for k in C.CHANNEL_KEYS},
            "proposals": {p["name"]: _prop_boot(p) for p in v["proposals"]}}
    if ctx["is_team"]:
        rows = {}
        for r in v["rows"]:
            rows[r["name"]] = {"name": r["name"], "team": r.get("team") or "", "data_type": r.get("data_type") or "",
                               "platform": r.get("platform") or "", "frequency": r.get("frequency") or "",
                               "data_owner": r.get("data_owner") or "", "note": r.get("note") or "",
                               "front_priority": int(r.get("front_priority") or 0),
                               "last_updated": str(r.get("last_updated") or "")[:16].replace(" ", "T")}
            for k in C.CHANNEL_KEYS:
                rows[r["name"]][C.CHANNEL_FIELD[k]] = int(r.get(C.CHANNEL_FIELD[k]) or 0)
        # hop "Thêm dữ liệu đã có": loai du lieu theo team + san da co cua tung (team, loai) -> JS khoa chip trung
        team_types, group_plats = {}, {}
        for g in A.groups_flat(v["teams"]):
            team_types.setdefault(g["team"], []).append(g["data_type"])
            group_plats[(g["team"] + "|" + g["data_type"]).lower()] = [
                c["platform"] for c in list(g["cells"].values()) + g["others"] if c]
        boot.update({"team_types": team_types, "group_plats": group_plats})
        boot.update({"rows": rows, "team": v["team_members"], "plan_defaults": plan_defaults(repo),
                     "gaps": {g["key"]: {"team": g["team"], "data_type": g["data_type"], "platforms": g["unplanned"],
                                         "proposal": g["proposal"] if g.get("proposal_open") else "",
                                         "urgency": g["urgency"]} for g in v["gaps"]},
                     "library": {x["name"]: {k: x[k] for k in ("name", "title", "link", "team", "owner", "data_sources",
                                                               "from_ticket", "tags", "active")} for x in v["library"]}})
        code = (prefill_ticket or "").strip().upper()
        if code:
            t = repo.get(code)
            if t and t.get("kind", C.KIND_REQUEST) == C.KIND_REQUEST:
                boot["prefill"] = {"title": t.get("title") or "", "link": t.get("output_link") or "",
                                   "team": S.dept_label(t.get("requester_department")),
                                   "owner": t.get("assignee") or "", "data_sources": t.get("data_used") or "",
                                   "from_ticket": t["name"], "tags": C.TYPE_SHORT.get(t.get("request_type"), "")}
                ctx["sub"] = boot["sub"] = "library"
    ctx["boot_json"] = S._boot(boot)
    return ctx


# ------------------------------------------------------------------ de xuat ---------------
def dept_options(repo):
    """Phong ban ERP cho o "Phòng ban cần dữ liệu" -> ([{name, label}], {name: department_name}).
    Trung department_name giua cac cong ty -> hien ten day du ("Service - EC") de khong nham."""
    rows = repo.departments() or []
    count = {}
    for r in rows:
        count[r["label"]] = count.get(r["label"], 0) + 1
    opts = [{"name": r["name"], "label": r["label"] if count[r["label"]] == 1 else r["name"]} for r in rows]
    return opts, {r["name"]: r["label"] for r in rows}


def create_proposal(user, data, files=None, repo=None):
    """Moi nhan vien: "+ Đề xuất data cần crawl" -> Chờ duyệt, han = N ngay lam viec (quy tac
    "Duyệt đề xuất data cần crawl"), bao team Data. files = [{name, content, size}] (anh / file huong dan,
    da giai base64 o api). -> {name, due_at}."""
    repo = _repo(repo)
    S.require_internal(repo, user)
    now = repo.now()
    _opts, depts = dept_options(repo)
    v = _validate(A.normalize_proposal, data or {}, repo.proposal_sent_today(user, repo.today()), depts, now)
    errs = D.check_files(files or ())
    if errs:
        _fail(errs)
    r = S.rules(repo)
    due = A.proposal_due(now, r, repo.holidays())
    name = repo.proposal_insert({
        "team": v["team"], "department": v["department"], "data_type": v["data_type"],
        "platforms": json.dumps(v["platforms"], ensure_ascii=False), "purpose": v["purpose"],
        "urgency": v["urgency"], "urgency_reason": v["urgency_reason"], "urgency_note": v["urgency_note"],
        "frequency": v["frequency"], "scope": v["scope"],
        "source_links": json.dumps(v["source_links"], ensure_ascii=False) if v["source_links"] else "",
        "channels": json.dumps(v["channels"]) if v["channels"] else "",
        "data_from": v["data_from"], "data_to": v["data_to"], "needed_by": v["needed_by"],
        "proposer": user, "status": C.PROP_PENDING, "due_at": due, "rule_version": r["version"]})
    if files:
        repo.proposal_add_files(name, files, user)
    who = repo.full_names([user]).get(user) or user
    bits = [who + " đề xuất", A.platform_label(v["platforms"]), v["frequency"], v["urgency"]]
    if v["urgency_reason"]:
        bits[-1] += " (" + D.one_line(v["urgency_reason"], 80) + ")"
    if v["needed_by"]:
        bits.append("cần trước " + A.fmt_need(v["needed_by"]))
    _send(repo, C.EV_PROPOSAL, S.members(repo), "Đề xuất data cần crawl: %s (%s)" % (v["data_type"], v["team"]),
          "%s. Hạn duyệt %s." % (" · ".join(b for b in bits if b), D.fmt_dt(due)), "proposal|" + name, user)
    return {"name": name, "due_at": str(due)}


def can_see_proposal_files(repo, user, p):
    return bool(p) and (user == p.get("proposer") or S.can_operate(repo, user) or repo.is_admin(user))


def download_proposal_file(user, name, row, repo=None):
    """Tai anh / file huong dan cua de xuat: nguoi de xuat, team Data, System Manager."""
    repo = _repo(repo)
    S.require_internal(repo, user)
    p = repo.proposal_get(name)
    if not p:
        raise S.NotFound(name)
    if not can_see_proposal_files(repo, user, p):
        raise S.Forbidden("Chỉ người đề xuất và team Data tải được tệp này.")
    got = repo.proposal_file_content(name, str(row or ""))
    if not got:
        raise S.NotFound(name)
    return got


def _ensure_rows(repo, team, data_type, platforms, user=None):
    """Dong (team, loai, san) chua co -> tao dong trong (moi kenh = 0). -> ([ten dong], [san moi tao])."""
    rows = repo.avail_rows()
    names, created = [], []
    for p in platforms:
        hit = next((r for r in rows if A.same(r.get("team"), team) and A.same(r.get("data_type"), data_type)
                    and A.same(A.norm_platform(r.get("platform")), p)), None)
        if hit:
            names.append(hit["name"])
            continue
        n = repo.avail_insert({"team": team, "data_type": data_type, "platform": p, "in_sharepoint": 0, "in_dw": 0,
                               "in_powerbi": 0, "front_priority": 0})
        rows.append({"name": n, "team": team, "data_type": data_type, "platform": p})
        names.append(n)
        created.append(p)
    return names, created


def review_proposal(user, name, verdict, reason="", repo=None):
    """Team Data: "Duyệt" -> tao dong ma tran (o "Chua co") cho cac san de xuat neu chua co - de xuat
    hien trong "Cần bổ sung" voi nguon "Đề xuất đã duyệt", cho Len ke hoach; "Từ chối" + ly do.
    Bao nguoi de xuat. -> {status, created}."""
    repo = _repo(repo)
    S.require_operate(repo, user)
    p = repo.proposal_lock(name)
    if not p:
        _fail("Không tìm thấy đề xuất này (có thể đã bị xoá).")
    if p.get("status") != C.PROP_PENDING:
        _fail("Đề xuất đã được xử lý (đang: {0}). Tải lại trang.".format(p.get("status")))
    reason = D.clean_text(reason, C.REASON_MAX)
    now = repo.now()
    plats = A.load_list(p.get("platforms"))
    who = repo.full_names([user]).get(user) or user
    title = "%s (%s)" % (p.get("data_type"), p.get("team"))
    if verdict == C.PROP_APPROVED:
        _names, created = _ensure_rows(repo, p.get("team"), p.get("data_type"), plats, user)
        repo.proposal_set(name, {"status": C.PROP_APPROVED, "decided_by": user, "decided_at": now, "reason": reason})
        msg = "%s duyệt đề xuất · %s. Team Data sẽ lên kế hoạch bổ sung, bạn được báo hạn." % (
            who, A.platform_label(plats))
        if reason:
            msg += " · " + reason
        _send(repo, C.EV_UPDATE, [p.get("proposer")], "Đề xuất được duyệt: " + title, msg,
              "proposal_ok|" + name, user)
        return {"status": C.PROP_APPROVED, "created": created}
    if verdict == C.PROP_REJECTED:
        if not reason:
            _fail("Từ chối cần ghi lý do (người đề xuất sẽ thấy).")
        repo.proposal_set(name, {"status": C.PROP_REJECTED, "decided_by": user, "decided_at": now, "reason": reason})
        _send(repo, C.EV_UPDATE, [p.get("proposer")], "Đề xuất chưa được duyệt: " + title,
              "%s: %s" % (who, reason), "proposal_no|" + name, user)
        return {"status": C.PROP_REJECTED, "created": []}
    _fail("Chọn Duyệt hoặc Từ chối.")


# ------------------------------------------------------------------ ke hoach DA ----------
def plan(user, data, repo=None, pm=None):
    """Team Data "Lên kế hoạch" (tu danh sach Can bo sung hoac o "Chua co"): tao DA-... qua luong nhan
    viec dot 1 (task /pm, Gantt), gan cac dong ma tran (o hien "Đang làm · hạn ..."). -> {code, due, pm_task,
    warning}."""
    from ecentric_workspace.data_hub import ops_service as O
    repo = _repo(repo)
    S.require_operate(repo, user)
    v = _validate(A.normalize_plan, data or {})
    today, hol = repo.today(), repo.holidays()
    team = S.members(repo)
    errs = []
    assignee = v["assignee"] or (user if user in team else "")
    if not assignee:
        errs.append("Chọn người xử lý.")
    elif assignee not in team:
        errs.append("Người xử lý phải thuộc team Data.")
    start = D.as_date(v["start_date"]) if v["start_date"] else D.default_start(today, hol)
    if not start:
        errs.append("Ngày bắt đầu không hợp lệ.")
    elif start < today:
        errs.append("Ngày bắt đầu không được trước hôm nay.")
    due = D.as_date(v["due_date"]) if v["due_date"] else None
    if v["due_date"] and not due:
        errs.append("Ngày kết thúc không hợp lệ.")
    elif due and start and due < start:
        errs.append("Ngày kết thúc không được trước ngày bắt đầu.")
    proposal = None
    if v["proposal"]:
        proposal = repo.proposal_lock(v["proposal"])
        if not proposal or proposal.get("status") != C.PROP_APPROVED:
            errs.append("Đề xuất này chưa được duyệt.")
        elif proposal.get("resulting_ticket"):
            errs.append("Đề xuất đã có kế hoạch {0}.".format(proposal["resulting_ticket"]))
    pri = v["priority"] or (proposal or {}).get("urgency") or C.PRI_NORMAL
    if pri not in C.PRIORITIES:
        errs.append("Mức ưu tiên không hợp lệ.")
    if errs:
        _fail(errs)
    names, _created = _ensure_rows(repo, v["team"], v["data_type"], v["platforms"], user)
    rows = repo.avail_lock(names)
    tickets = _tickets_for(repo, rows, [])
    busy = A.open_plans(rows, tickets.values())
    if busy:
        taken = sorted({"%s (%s)" % (A.norm_platform(r.get("platform")), busy[r["name"]]["name"])
                        for r in rows if r["name"] in busy})
        _fail("Đã có kế hoạch đang làm cho: {0}. Mở kế hoạch đó để đổi hạn / người.".format(", ".join(taken)))
    if all(all(int(r.get(C.CHANNEL_FIELD[k]) or 0) for k in v["channels"]) for r in rows):
        _fail("Các sàn đã chọn đều đã có trên kênh đã chọn - không cần bổ sung.")
    requester = (proposal or {}).get("proposer") or user
    emp = repo.employee(requester) or {}
    r = S.rules(repo)
    n = D.ticket_sla_days(r, C.DA_REQUEST_TYPE, pri)
    code = repo.insert_ticket({
        "kind": C.KIND_AVAILABILITY, "naming_series": C.SERIES[C.KIND_AVAILABILITY],
        "title": A.da_title(v["team"], v["data_type"], v["platforms"]), "request_type": C.DA_REQUEST_TYPE,
        "description": A.da_description(v["team"], v["data_type"], v["platforms"], v["channels"], v["method"],
                                        v["note"], proposal),
        "requester": requester, "requester_department": emp.get("department") or "", "status": C.ST_WAITING,
        "proposed_priority": pri, "priority": "", "urgent_reason": "", "data_used": "", "reference_link": "",
        "rule_version": r["version"], "sla_days": n, "intake_due_date": today,
        "platforms": json.dumps(v["platforms"], ensure_ascii=False), "channels": json.dumps(v["channels"]),
        "method": v["method"], "availability_rows": json.dumps(names)})
    S.log(repo, code, C.EV_CREATED, user, to_value=pri,
          note=("Kế hoạch bổ sung data từ đề xuất " + proposal["name"]) if proposal else "Kế hoạch bổ sung data")
    for nm in names:
        repo.avail_set(nm, {"planned_ticket": code})
    if proposal:
        repo.proposal_set(proposal["name"], {"resulting_ticket": code})
    # Luong nhan viec dot 1: nguoi xu ly, bat dau, han (ly do = ghi chu ke hoach), task /pm, bao nguoi de xuat.
    out = O.accept(user, code, assignee, start.isoformat(), due.isoformat() if due else "", pri,
                   v["note"] or "Theo kế hoạch bổ sung data", repo=repo, pm=pm)
    return {"code": code, "due": out["due"], "pm_task": out.get("pm_task") or "", "warning": out.get("warning") or "",
            "rows": names}


def needs_acceptance(repo, t):
    """DA do team Data tu len -> khong can nghiem thu; DA tu de xuat -> nguoi de xuat nghiem thu."""
    if t.get("kind", C.KIND_REQUEST) != C.KIND_AVAILABILITY:
        return True
    try:
        return bool(_repo(repo).proposal_by_ticket(t["name"]))
    except Exception:
        repo.log_error("Data Hub needs_acceptance %s" % t.get("name"))
        return True


def on_ticket_closed(repo, t, actor=None):
    """Goi tu ops_service khi ticket sang Hoàn tất. Nuot moi loi (khong lam hong dong viec).
    DA -> bat o ma tran; yeu cau Power BI Dat co link -> them vao Thu vien bao cao."""
    try:
        r = _repo(repo)
        if t.get("kind", C.KIND_REQUEST) == C.KIND_AVAILABILITY:
            return {"flipped": _flip(r, t, actor)}
        if t.get("request_type") in C.LIBRARY_TYPES and t.get("acceptance") in (C.ACC_OK, C.ACC_AUTO):
            return {"library": _auto_library(r, t)}
    except Exception:
        repo.log_error("Data Hub on_ticket_closed %s" % t.get("name"))
    return {}


def _flip(repo, t, actor):
    now = repo.now()
    chans = [k for k in A.load_list(t.get("channels")) if k in C.CHANNEL_KEYS]
    done = []
    for name in A.load_list(t.get("availability_rows")):
        row = repo.avail_get(name)
        if not row:
            continue
        vals = A.flip_values(row, chans, now)
        if not row.get("data_owner") and t.get("assignee"):
            vals["data_owner"] = t["assignee"]
        repo.avail_set(name, vals)
        done.append(name)
    # Dau vet: Version cua tung dong (track_changes) + nhat ky "Hoàn tất" cua DA (ops_service).
    return done


def _auto_library(repo, t):
    link = (t.get("output_link") or "").strip()
    if not link or not D.valid_link(link) or repo.library_by_link(link) or repo.library_by_ticket(t["name"]):
        return ""
    return repo.library_insert({
        "title": (t.get("title") or "")[:C.TITLE_MAX], "link": link, "report_owner": t.get("assignee") or None,
        "team": S.dept_label(t.get("requester_department")), "data_sources": (t.get("data_used") or "")[:C.SOURCES_MAX],
        "from_ticket": t["name"], "tags": C.TYPE_SHORT.get(t.get("request_type"), ""), "active": 1,
        "added_by": C.SYSTEM_USER})


def da_closed_notify(repo, t, actor):
    """DA dong luon (khong can nghiem thu): bao nguoi theo doi + nguoi len ke hoach (neu khong phai minh)."""
    try:
        from ecentric_workspace.data_hub import notify
        return notify._send(repo, C.EV_UPDATE, [t.get("requester")] + notify._followers(t),
                            "Đã bổ sung data: " + notify._title(t),
                            "Hoàn tất - các ô trong Data availability đã chuyển “Có”.", t["name"], "da_done", actor)
    except Exception:
        repo.log_error("Data Hub notify da_done %s" % t.get("name"))
        return []


def ticket_extra(repo, t):
    """Them vao popup chi tiet (service.detail): DA -> san / kenh / cach lay / o ma tran; yeu cau Power BI
    -> muc Thu vien bao cao (neu da co). Loi -> {} (popup van mo)."""
    try:
        r = _repo(repo)
        if t.get("kind", C.KIND_REQUEST) == C.KIND_AVAILABILITY:
            rows = [x for x in (r.avail_get(n) for n in A.load_list(t.get("availability_rows"))) if x]
            team = rows[0].get("team") if rows else ""
            return {"plan": {"platforms": A.platform_label(A.load_list(t.get("platforms"))),
                             "channels": A.channel_text(A.load_list(t.get("channels")), short=False),
                             "method": t.get("method") or "", "team": team or "",
                             "data_type": rows[0].get("data_type") if rows else "",
                             "needs_acceptance": needs_acceptance(r, t)}}
        if t.get("request_type") in C.LIBRARY_TYPES:
            x = r.library_by_ticket(t["name"])
            return {"library": {"name": x["name"], "title": x.get("title") or "", "link": x.get("link") or "",
                                "active": bool(int(x.get("active") or 0))} if x else None}
    except Exception:
        repo.log_error("Data Hub ticket_extra %s" % t.get("name"))
    return {}


# ------------------------------------------------------------------ sua dong ma tran -------
def save_row(user, data, repo=None):
    """Team Data them / sua mot dong (kenh, tan suat, nguoi phu trach, cap nhat lan cuoi, ghi chu, ★).
    -> {name, created}."""
    repo = _repo(repo)
    S.require_operate(repo, user)
    data = data or {}
    v = _validate(A.normalize_row, data)
    if v["data_owner"] and not repo.enabled_users([v["data_owner"]]):
        _fail("Người phụ trách không hợp lệ.")
    if not v["data_owner"]:
        v["data_owner"] = None
    name = (data.get("name") or "").strip()
    rows = repo.avail_rows()
    dup = next((r for r in rows if r["name"] != name and A.same(r.get("team"), v["team"])
                and A.same(r.get("data_type"), v["data_type"]) and A.same(A.norm_platform(r.get("platform")), v["platform"])),
               None)
    if dup:
        _fail("Đã có dòng {0} · {1} · {2}.".format(v["team"], v["data_type"], v["platform"]))
    if name:
        cur = repo.avail_get(name)
        if not cur:
            _fail("Không tìm thấy dòng dữ liệu này. Tải lại trang.")
        if not v["last_updated"] and not A.has_data(cur) and any(v[C.CHANNEL_FIELD[k]] for k in C.CHANNEL_KEYS):
            v["last_updated"] = repo.now()     # vua co du lieu lan dau
        repo.avail_set(name, v)
        return {"name": name, "created": False}
    if not v["last_updated"] and any(v[C.CHANNEL_FIELD[k]] for k in C.CHANNEL_KEYS):
        v["last_updated"] = repo.now()
    return {"name": repo.avail_insert(v), "created": True}


def add_rows(user, data, repo=None):
    """Team Data "+ Thêm dữ liệu đã có" ngay tren ma tran (11/11/2026, PO Hoan): mot lan nhieu san cho
    cung (team, loai du lieu), KHONG qua de xuat / duyet. Moi thong tin (kenh, tan suat, nguoi phu trach,
    cap nhat lan cuoi, ghi chu, Front) ap cho moi san. Kiem het truoc khi ghi; san da co dong -> bo qua
    (bao lai), tat ca da co -> loi. -> {created: [ten dong], skipped: [san]}."""
    repo = _repo(repo)
    S.require_operate(repo, user)
    data = dict(data or {})
    raw = data.get("platforms") if isinstance(data.get("platforms"), list) else []
    plats = A.parse_platforms(raw, data.get("other_platform") or "")
    errs, vals = [], []
    for p in plats or [""]:
        try:
            vals.append(A.normalize_row(dict(data, platform=p, name="")))
        except D.Invalid as e:
            errs += [x for x in e.errors if x not in errs]
    if not plats:
        errs = [x for x in errs if not x.startswith("Ghi tên sàn")]
        errs.insert(0, "Chọn ít nhất một sàn / nguồn.")
    if errs:
        _fail(errs)
    owner = vals[0]["data_owner"]
    if owner and not repo.enabled_users([owner]):
        _fail("Người phụ trách không hợp lệ.")
    rows = repo.avail_rows()
    todo, skipped = [], []
    for v in vals:
        hit = next((r for r in rows if A.same(r.get("team"), v["team"]) and A.same(r.get("data_type"), v["data_type"])
                    and A.same(A.norm_platform(r.get("platform")), v["platform"])), None)
        (skipped if hit else todo).append(v["platform"] if hit else v)
    if not todo:
        _fail("Đã có đủ các dòng này ({0} · {1} · {2}). Bấm vào ô trong bảng để sửa.".format(
            vals[0]["team"], vals[0]["data_type"], ", ".join(skipped)))
    now = repo.now()
    created = []
    for v in todo:
        v["data_owner"] = v["data_owner"] or None
        if not v["last_updated"] and any(v[C.CHANNEL_FIELD[k]] for k in C.CHANNEL_KEYS):
            v["last_updated"] = now
        created.append(repo.avail_insert(v))
    return {"created": created, "skipped": skipped}


# ------------------------------------------------------------------ thu vien bao cao ------
def save_library(user, data, repo=None):
    """Team Data them / sua muc Thu vien bao cao. -> {name, created}."""
    repo = _repo(repo)
    S.require_operate(repo, user)
    data = data or {}
    v = _validate(A.normalize_library, data)
    if v["report_owner"] and not repo.enabled_users([v["report_owner"]]):
        _fail("Người phụ trách không hợp lệ.")
    v["report_owner"] = v["report_owner"] or None
    if v["from_ticket"]:
        t = repo.get(v["from_ticket"])
        if not t:
            _fail("Không có yêu cầu {0}.".format(v["from_ticket"]))
    else:
        v["from_ticket"] = None
    name = (data.get("name") or "").strip()
    same = repo.library_by_link(v["link"])
    if same and same["name"] != name:
        _fail("Link này đã có trong thư viện: {0}.".format(same.get("title") or same["name"]))
    if name:
        if not repo.library_get(name):
            _fail("Không tìm thấy báo cáo này. Tải lại trang.")
        repo.library_set(name, v)
        return {"name": name, "created": False}
    v.update({"active": 1, "added_by": user})
    return {"name": repo.library_insert(v), "created": True}


def set_library_active(user, name, active, repo=None):
    """An / hien lai (khong xoa - giu lich su)."""
    repo = _repo(repo)
    S.require_operate(repo, user)
    if not repo.library_get(name):
        _fail("Không tìm thấy báo cáo này. Tải lại trang.")
    on = 0 if active in (0, "0", False, "false", "False") else 1
    repo.library_set(name, {"active": on})
    return {"name": name, "active": bool(on)}


# ------------------------------------------------------------------ goi y tuong tu --------
def suggest(user, q, repo=None):
    """Form tao yeu cau: go tieu de -> "Đã có dashboard tương tự" (Thu vien) + yeu cau dang mo tuong tu."""
    repo = _repo(repo)
    S.require_internal(repo, user)
    q = D.one_line(q, C.TITLE_MAX)
    if len(q) < C.SUGGEST_MIN_CHARS:
        return {"library": [], "requests": []}
    lib = repo.library_rows()
    hits = A.similar(q, lib, lambda x: " ".join([x.get("title") or "", x.get("tags") or "", x.get("data_sources") or ""]))
    reqs = repo.list_rows({"kind": C.KIND_REQUEST, "status": ["in", list(C.OPEN)]}, limit=C.LIST_LIMIT)
    rh = A.similar(q, reqs, lambda t: t.get("title") or "")
    return {"library": [{"title": x.get("title") or "", "link": x.get("link") or "", "team": x.get("team") or "",
                         "score": s} for s, x in hits],
            "requests": [{"code": t["name"], "title": t.get("title") or "",
                          "status": C.STATUS_LABEL.get(t.get("status"), t.get("status")), "url": "%s?ma=%s" % (C.ROUTE, t["name"]),
                          "score": s} for s, t in rh]}


# ------------------------------------------------------------------ job 09:00 ---------------
def run_daily(repo=None):
    """Nhac team Data de xuat qua han duyet (moi ngay lam viec, mot tin / de xuat / nguoi / ngay)."""
    repo = _repo(repo)
    today, now = repo.today(), repo.now()
    out = {"proposal_overdue": 0}
    if not D.is_working_day(today, repo.holidays()):
        return out
    team = S.members(repo)
    for p in repo.proposal_pending():
        try:
            label, late = A.countdown(p.get("due_at"), now)
            if not late:
                continue
            if _send(repo, C.EV_OVERDUE, team, "Đề xuất chờ duyệt %s: %s (%s)" % (label, p.get("data_type"), p.get("team")),
                     "Duyệt hoặc từ chối (kèm lý do) ở Data availability.", "proposal_late|%s|%s" % (p["name"], today),
                     C.SYSTEM_USER):
                out["proposal_overdue"] += 1
        except Exception:
            repo.log_error("Data Hub proposal reminder %s" % p.get("name"))
    return out


def _gop_tin_job(fn):
    try:
        from ecentric_workspace.notification_center.nhip_gui import gop_tin_job
        return gop_tin_job(fn)
    except Exception:
        return fn


@_gop_tin_job
def daily():
    """Scheduler cron "0 9 * * *" (hooks.py, noi them): nhac de xuat qua han duyet."""
    from ecentric_workspace.data_hub import avail_repository as R
    try:
        out = run_daily(R)
        R.commit()
        return out
    except Exception:
        R.log_error("Data Hub avail daily job")
