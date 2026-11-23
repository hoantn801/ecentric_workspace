# Copyright (c) 2026, eCentric and contributors
"""Repository gia trong bo nho cho test module Ky luat - cung chu ky voi
hr/ky_luat/infrastructure/repository.py. Khong can bench."""
import copy
import datetime as dt
import sys
import types


def install_fake_frappe():
    if "frappe" in sys.modules:
        return
    fr = types.ModuleType("frappe")
    for n in ("ValidationError", "PermissionError", "DoesNotExistError"):
        setattr(fr, n, type(n, (Exception,), {}))
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr.flags = types.SimpleNamespace()
    utils = types.ModuleType("frappe.utils")
    utils.strip_html = lambda s: s
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils


install_fake_frappe()

from ecentric_workspace.hr.ky_luat import constants as C  # noqa: E402

HR = "hr@x"
LM = "lm@x"
NV = "nv@x"
CEO = "ceo@x"
OUT = "out@x"
UNION = "union@x"


class FakeRepo:
    def __init__(self, today=dt.date(2026, 11, 23)):
        self._today = today
        self.hols = set()
        self.notices_ = {}
        self.cases_ = {}
        self.sent = []          # (users, subject, email)
        self.errors = []
        self.leaves = {}        # employee -> [(a, b)]
        self.relieving = {}
        self.clearance_result = None
        self.clearance_calls = []
        self.decisions = {}     # decision -> status
        self.decision_calls = []
        self.bad_files = set()
        self.seq = 0
        self.settings_ = {"union_rep_user": UNION, "notice_reply_days": 3, "hr_review_days": 3,
                          "meeting_notice_days": 5, "ceo_sign_days": 2, "limitation_warn_days": 14,
                          "legal_note": C.LEGAL_NOTE}
        self.emps = {
            "EMP-NV": {"name": "EMP-NV", "employee_name": "Nhan Vien", "user": NV, "user_id": NV,
                       "department": "Ops", "designation": "Staff", "reports_to": "EMP-LM",
                       "reports_to_user": LM, "status": "Active"},
            "EMP-LM": {"name": "EMP-LM", "employee_name": "Quan Ly", "user": LM, "user_id": LM,
                       "department": "Ops", "reports_to": None, "reports_to_user": None, "status": "Active"},
            "EMP-HR": {"name": "EMP-HR", "employee_name": "Nhan Su", "user": HR, "user_id": HR,
                       "department": "HR", "reports_to": None, "reports_to_user": None, "status": "Active"},
            "EMP-OUT": {"name": "EMP-OUT", "employee_name": "Nguoi Ngoai", "user": OUT, "user_id": OUT,
                        "department": "Sales", "reports_to": None, "reports_to_user": None, "status": "Active"},
        }
        self.roles = {HR: ["HR Manager", "Employee"], LM: ["Employee"], NV: ["Employee"],
                      CEO: ["EC CEO"], OUT: ["Employee"], UNION: ["Employee"]}
        self.rules = {"R1": {"name": "R1", "title": "Di muon", "finance_related": 0, "is_active": 1, "is_sample": 1},
                      "RF": {"name": "RF", "title": "Tai san", "finance_related": 1, "is_active": 1, "is_sample": 1}}

    # thoi gian
    def now(self):
        return dt.datetime.combine(self._today, dt.time(9, 0))

    def today(self):
        return self._today

    def holidays(self):
        return set(self.hols)

    def settings(self):
        return dict(self.settings_)

    def rule(self, name):
        return copy.deepcopy(self.rules.get(name))

    def active_rules(self):
        return [dict(r) for r in self.rules.values()]

    # nhan su
    def employee(self, name):
        e = self.emps.get(name)
        return dict(e) if e else None

    def employee_of_user(self, user):
        for e in self.emps.values():
            if e["user"] == user:
                return e["name"]
        return None

    def team_of(self, employee):
        out, front = set(), [employee]
        while front:
            nxt = [e["name"] for e in self.emps.values() if e.get("reports_to") in front and e["name"] not in out]
            out.update(nxt)
            front = nxt
        return out

    def roles_of(self, user):
        return list(self.roles.get(user, []))

    def users_with_roles(self, roles):
        return sorted(u for u, rs in self.roles.items() if set(rs) & set(roles))

    def active_employees(self, names=None):
        rows = [dict(e) for e in self.emps.values() if names is None or e["name"] in names]
        return rows

    def set_relieving_date(self, employee, day):
        self.relieving[employee] = day

    def leave_periods(self, employee, start, end):
        return [(a, b) for a, b in self.leaves.get(employee, []) if a <= end and b >= start]

    def file_ok(self, url, user):
        return url not in self.bad_files

    # the vang
    def _id(self, p):
        self.seq += 1
        return "%s-%05d" % (p, self.seq)

    def get_notice(self, name):
        return copy.deepcopy(self.notices_.get(name))

    def insert_notice(self, row, log):
        name = self._id("TV")
        self.notices_[name] = dict(row, name=name, logs=[log])
        return name

    def update_notice(self, name, values, log):
        self.notices_[name].update(values)
        if log:
            self.notices_[name]["logs"].append(log)
        return name

    def notices(self, employees=None, issued_by=None, limit=500):
        rows = list(self.notices_.values())
        if employees is None and issued_by is None:
            return copy.deepcopy(rows)
        return copy.deepcopy([r for r in rows if (employees and r["employee"] in employees)
                              or (issued_by and r.get("issued_by") == issued_by)])

    def notice_dates(self, employee):
        return [r["incident_date"] for r in self.notices_.values()
                if r["employee"] == employee and r["status"] != C.NOTICE_CANCELLED]

    def overdue_notices(self, today):
        return [dict(r) for r in self.notices_.values() if r["status"] == C.NOTICE_PENDING and r["reply_due"] < today]

    # ho so
    def get_case(self, name):
        return copy.deepcopy(self.cases_.get(name))

    def insert_case(self, row, log):
        name = self._id("KL")
        self.cases_[name] = dict(row, name=name, logs=[log])
        return name

    def update_case(self, name, values, log):
        self.cases_[name].update(copy.deepcopy(values))
        if log:
            self.cases_[name]["logs"].append(log)
        return name

    def cases(self, employees=None, extra_or=None, limit=500, statuses=None):
        rows = list(self.cases_.values())
        if employees is None and not extra_or:
            return copy.deepcopy(rows)
        out = []
        for r in rows:
            ok = bool(employees) and r["employee"] in employees
            for f, _op, v in extra_or or []:
                ok = ok or r.get(f) == v
            if ok:
                out.append(r)
        return copy.deepcopy(out)

    def cases_of_employee(self, employee, statuses=None):
        return copy.deepcopy([r for r in self.cases_.values() if r["employee"] == employee
                              and (not statuses or r["status"] in statuses)])

    def open_cases(self):
        return copy.deepcopy([r for r in self.cases_.values() if r["status"] in C.CASE_OPEN])

    def issued_due_for_expunge(self, today):
        return copy.deepcopy([r for r in self.cases_.values() if r["status"] == C.S_ISSUED
                              and r.get("expunge_due") and r["expunge_due"] <= today])

    # engine
    def decision_status(self, decision):
        return self.decisions.get(decision)

    def create_decision(self, case, actor):
        name = self._id("QD")
        self.decisions[name] = "Pending"
        self.decision_calls.append(("create", case["name"], actor))
        return name

    def resubmit_decision(self, case, actor):
        self.decisions[case["decision_request"]] = "Pending"
        self.decision_calls.append(("resubmit", case["name"], actor))

    def create_clearance(self, employee, reason, last_day):
        self.clearance_calls.append((employee, reason, last_day))
        return self.clearance_result

    def notify(self, users, subject, doctype, name, message="", url=None, email=False, severity=None):
        self.sent.append(([u for u in users if u], subject, email))

    def log_error(self, title):
        self.errors.append(title)

    # tien ich test
    def to(self, *users):
        return [s for s in self.sent if set(users) & set(s[0])]
