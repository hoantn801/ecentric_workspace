# Copyright (c) 2026, eCentric and contributors
"""Phan repo gia cua DOT 3 (quy tac co phien ban + duyet, chuyen phieu Data Request cu) - gan vao
FakeRepo bang install() (fake.py goi o cuoi file) de khong sua vao than lop dot 1 / dot 2 dang sua.

Quy tac: self.rules_ = {ten: ban ghi} (khoi tao tu self.rule cua dot 1). rule_set() tra ban dang ap dung
theo Settings.active_rule_set - dung nhu repository that.
Phieu cu: self.legacy = [phieu], self.legacy_acts = {approval_request: [action]}, self.legacy_file_rows =
{ma cu: [File]}, self.tasks_by_subject = {chuoi: task}. fail_insert = {ma cu} -> nem loi giua chung de
kiem savepoint.
"""
import copy
import datetime as dt

from ecentric_workspace.data_hub import constants as C


def _rules(self):
    if not hasattr(self, "rules_"):
        self.rules_ = {self.rule["name"]: copy.deepcopy(self.rule)}
    return self.rules_


def rule_set(self, name=None):
    store = _rules(self)
    n = name or self.settings_.get("active_rule_set")
    if not n or n not in store:
        act = [r for r in store.values() if r["status"] == C.RULE_ACTIVE]
        act.sort(key=lambda r: r["version_no"], reverse=True)
        return copy.deepcopy(act[0]) if act else None
    return copy.deepcopy(store[n])


def rule_doc(self, name):
    store = _rules(self)
    return copy.deepcopy(store[name]) if name in store else None


def rule_versions(self, statuses=None, limit=30):
    rows = [copy.deepcopy(r) for r in _rules(self).values() if not statuses or r["status"] in statuses]
    rows.sort(key=lambda r: r["version_no"], reverse=True)
    return rows[:limit]


def rule_history(self, limit=20):
    return [{k: r.get(k) for k in ("name", "version_no", "status", "effective_from", "proposed_by", "decided_by",
                                   "decided_at", "reason")} for r in rule_versions(self, limit=limit)]


def lock_rules(self):
    self.rule_locks = getattr(self, "rule_locks", 0) + 1


def next_rule_version(self):
    return max([r["version_no"] for r in _rules(self).values()] or [0]) + 1


def insert_rule(self, values):
    store = _rules(self)
    name = "SLA-v%d" % values["version_no"]
    if name in store:
        raise ValueError("Duplicate version")
    row = {"name": name, "effective_from": None, "supersedes": None, "proposed_by": None, "reason": "",
           "submitted_at": None, "decided_by": None, "decided_at": None, "decision_note": "",
           "creation": self.clock.strftime("%Y-%m-%d %H:%M:%S")}
    row.update(copy.deepcopy(values))
    store[name] = row
    return name


def update_rule(self, name, values):
    _rules(self)[name].update(copy.deepcopy(values))


def set_settings(self, values):
    self.settings_.update(values)


def notify_ref(self, event, recipient, title, message, url, ref_doctype, ref_name, dedupe_key, actor=None):
    self.notes.append({"event": event, "to": recipient, "title": title, "message": message, "url": url,
                       "code": ref_name, "doctype": ref_doctype, "key": dedupe_key, "actor": actor})
    return {"ok": True}


# ------------------------------------------------------------------ phieu cu ----------------
def find_by_legacy(self, ref):
    for c, t in self.tickets.items():
        if ref and t.get("legacy_ref") == ref:
            return c
    return None


def legacy_ready(self):
    return getattr(self, "legacy_on", True)


def legacy_requests(self):
    return [copy.deepcopy(r) for r in getattr(self, "legacy", [])]


def legacy_actions(self, approval_request):
    return [copy.deepcopy(a) for a in getattr(self, "legacy_acts", {}).get(approval_request, [])]


def legacy_files(self, ref, urls=()):
    out, seen = [], set()
    for f in getattr(self, "legacy_file_rows", {}).get(ref, []):
        if f["file_url"] not in seen:
            seen.add(f["file_url"])
            out.append({"file_url": f["file_url"], "file_name": f["file_name"], "file_size": f.get("file_size", 0),
                        "uploaded_by": f.get("owner"), "message": ""})
    for u in urls or ():
        if u and u not in seen:
            seen.add(u)
            out.append({"file_url": u, "file_name": u.rsplit("/", 1)[-1], "file_size": 0, "uploaded_by": None,
                        "message": ""})
    return out


def insert_migrated(self, values, created_at):
    v = dict(values)
    if v.get("legacy_ref") in getattr(self, "fail_insert", set()):
        # ghi do dang roi nem loi -> migration phai rollback (savepoint) ve trang thai truoc
        self.tickets["PARTIAL-" + v["legacy_ref"]] = {"legacy_ref": v["legacy_ref"], "status": v["status"],
                                                      "requester": "", "creation": "", "followers": []}
        raise RuntimeError("DB lỗi giữa chừng")
    code = self.insert_ticket(v)
    if created_at:
        self.tickets[code]["creation"] = created_at.strftime("%Y-%m-%d %H:%M:%S")
    return code


def link_files(self, code, rows):
    for r in rows:
        n = "FILE-%d" % (len(self.files) + 1)
        self.files[n] = dict(r, name=n, parent=code, content=b"legacy")


def insert_log_at(self, values, at):
    name = self.insert_log(values)
    if at:
        self.logs_[-1]["creation"] = at.strftime("%Y-%m-%d %H:%M:%S")
    return name


def savepoint(self, name):
    self.saved = (copy.deepcopy(self.tickets), list(self.logs_), copy.deepcopy(self.files))
    return name


def rollback_savepoint(self, name):
    self.tickets, self.logs_, self.files = copy.deepcopy(self.saved[0]), list(self.saved[1]), copy.deepcopy(self.saved[2])
    self.rollbacks = getattr(self, "rollbacks", 0) + 1


def task_for_legacy(self, ref):
    for subj, task in getattr(self, "tasks_by_subject", {}).items():
        if ref and ref in subj:
            return task
    return None


def approval_type_route(self, code):
    types = getattr(self, "approval_types", {"DATA_REQUEST": "/approvals/data-request"})
    return types.get(code)


def set_approval_type_route(self, code, route, note):
    if not hasattr(self, "approval_types"):
        self.approval_types = {"DATA_REQUEST": "/approvals/data-request"}
    self.approval_types[code] = route
    self.route_notes = getattr(self, "route_notes", []) + [note]


METHODS = (rule_set, rule_doc, rule_versions, rule_history, lock_rules, next_rule_version, insert_rule, update_rule,
           set_settings, notify_ref, find_by_legacy, legacy_ready, legacy_requests, legacy_actions, legacy_files,
           insert_migrated, link_files, insert_log_at, savepoint, rollback_savepoint, task_for_legacy,
           approval_type_route, set_approval_type_route)


def install(cls):
    for fn in METHODS:
        setattr(cls, fn.__name__, fn)
    return cls


def ts(y, m, d, h=9, mi=0):
    return dt.datetime(y, m, d, h, mi)
