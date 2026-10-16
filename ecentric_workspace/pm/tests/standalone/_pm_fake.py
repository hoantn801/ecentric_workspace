# -*- coding: utf-8 -*-
"""In-memory fake `frappe` for the PM redesign standalone tests (no bench, no DB).

Covers exactly the API surface pm.api.tasks / pm_inbox / dashboard / projects / assignment and
pm.task_flow use: get_all (dict/list filters, or_filters, like/in/not in/is set/between, order,
paging, pluck), db.get_value/set_value/exists/count/delete, get_doc (load / new) with insert/save,
child tables, unique keys, before_save doc hooks, cache with TTL, session/roles, throw, utils.

Usage (see test files):
    fk = _pm_fake.install()          # puts fake frappe + stubs into sys.modules, purges PM modules
    tasks = fk.load("ecentric_workspace.pm.api.tasks")
"""
import copy
import datetime
import importlib
import itertools
import json
import os
import re
import sys
import types

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))  # .../src
TODAY = "2026-10-16"


class _dict(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        try:
            return self[k]
        except KeyError:
            return None

    def __setattr__(self, k, v):
        self[k] = v


# ----------------------------------------------------------------------------- exceptions
class ValidationError(Exception):
    pass


class PermissionError(Exception):  # noqa: A001 - mirrors frappe.PermissionError
    pass


class DoesNotExistError(ValidationError):
    pass


class DuplicateEntryError(Exception):
    pass


class LinkExistsError(ValidationError):
    pass


class QueryDeadlockError(Exception):
    pass


class WorkflowTransitionError(ValidationError):
    pass


# ----------------------------------------------------------------------------- filters
def _norm(v):
    if isinstance(v, (datetime.datetime, datetime.date)):
        return str(v)
    return v


def _match_one(row, field, op, val):
    rv = _norm(row.get(field))
    op = (op or "=").lower()
    if op in ("=", "=="):
        return rv == _norm(val) or (rv in (None, "") and val in (None, ""))
    if op == "!=":
        return (rv if rv is not None else "") != _norm(val)
    if op == "in":
        vals = [_norm(x) for x in (val or [])]
        return rv in vals or (rv in (None, "") and any(x in (None, "") for x in vals))
    if op == "not in":
        vals = [_norm(x) for x in (val or [])]
        return (rv if rv is not None else "") not in vals
    if op in ("like", "not like"):
        rx = "^" + re.escape(str(val)).replace("%", ".*").replace("_", ".") + "$"
        hit = rv is not None and re.match(rx, str(rv), re.S) is not None
        return hit if op == "like" else not hit
    if op == "is":
        isset = rv not in (None, "")
        return isset if val == "set" else not isset
    if op == "between":
        a, b = val
        return rv is not None and str(a)[:10] <= str(rv)[:10] <= str(b)[:10]
    if rv is None:
        return False
    a, b = str(rv), str(_norm(val))
    return {"<": a < b, ">": a > b, "<=": a <= b, ">=": a >= b}[op]


def _conds(filters):
    if not filters:
        return []
    out = []
    if isinstance(filters, dict):
        for k, v in filters.items():
            if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str) \
                    and v[0].lower() in ("=", "!=", "in", "not in", "like", "not like", "is",
                                         "between", "<", ">", "<=", ">="):
                out.append((k, v[0], v[1]))
            else:
                out.append((k, "=", v))
        return out
    for f in filters:
        if len(f) == 4:
            f = f[1:]
        out.append((f[0], f[1], f[2]))
    return out


# ----------------------------------------------------------------------------- db
class FakeDB(object):
    def __init__(self, fk):
        self.fk = fk
        self.tables = {}
        self.sqls = []
        self._seq = itertools.count(1)

    def t(self, dt):
        return self.tables.setdefault(dt, {})

    def rows(self, dt, filters=None, or_filters=None):
        out = []
        ands, ors = _conds(filters), _conds(or_filters)
        for r in self.t(dt).values():
            if not all(_match_one(r, *c) for c in ands):
                continue
            if ors and not any(_match_one(r, *c) for c in ors):
                continue
            out.append(r)
        return out

    def get_value(self, dt, name, fieldname="name", as_dict=False, **kw):
        if dt == "Workflow":
            return None
        if isinstance(name, dict):
            rows = self.rows(dt, name)
            row = rows[0] if rows else None
        else:
            row = self.t(dt).get(name)
        if row is None:
            return None
        if isinstance(fieldname, (list, tuple)):
            d = _dict({f: copy.deepcopy(row.get(f)) for f in fieldname})
            return d if as_dict else tuple(d[f] for f in fieldname)
        val = copy.deepcopy(row.get(fieldname))
        return _dict({fieldname: val}) if as_dict else val

    def set_value(self, dt, name, field, val=None, update_modified=True):
        row = self.t(dt).get(name)
        if row is None:
            raise DoesNotExistError("%s %s" % (dt, name))
        vals = field if isinstance(field, dict) else {field: val}
        row.update(copy.deepcopy(vals))
        if update_modified:
            row["modified"] = str(self.fk.utils.now_datetime())
        self.fk.writes.append((dt, name, dict(vals)))

    def exists(self, dt, name=None, *a, **kw):
        if dt == "DocType":
            return name if name in self.fk.doctypes else None
        if isinstance(name, dict):
            rows = self.rows(dt, name)
            return rows[0]["name"] if rows else None
        return name if name in self.t(dt) else None

    def count(self, dt, filters=None):
        return len(self.rows(dt, filters))

    def delete(self, dt, filters=None):
        for r in self.rows(dt, filters):
            self.t(dt).pop(r["name"], None)

    def sql(self, q, *a, **kw):
        self.sqls.append(q)
        return []

    def commit(self):
        pass

    def rollback(self):
        pass

    def get_single_value(self, *a):
        return None

    def escape(self, s):
        return "'" + str(s).replace("'", "\\'") + "'"


# ----------------------------------------------------------------------------- documents
CHILD_TABLES = {"events": "PM Assignment Request Event", "pm_checklist": "PM Task Checklist Item"}


class FakeDoc(_dict):
    def __init__(self, fk, data):
        super(FakeDoc, self).__init__()
        object.__setattr__(self, "_fk", fk)
        object.__setattr__(self, "_before", None)
        for k, v in data.items():
            if k in CHILD_TABLES and isinstance(v, list):
                v = [_dict(x) for x in v]
            self[k] = v

    def get(self, k, default=None):
        return dict.get(self, k, default)

    def set(self, k, v):
        self[k] = v

    def as_dict(self):
        return _dict(copy.deepcopy(dict(self)))

    def append(self, table, row):
        rows = self.setdefault(table, [])
        r = _dict(row)
        r.setdefault("name", "%s-row-%d" % (table, next(self._fk.db._seq)))
        r["idx"] = len(rows) + 1
        rows.append(r)
        return r

    def remove(self, row):
        for k, v in list(self.items()):
            if isinstance(v, list) and row in v:
                v.remove(row)

    def get_doc_before_save(self):
        return self._before

    def add_comment(self, comment_type="Comment", text=None, **kw):
        self._fk.comments.append((self.get("doctype"), self.get("name"), comment_type, text))

    def _run_hooks(self):
        for fn in self._fk.hooks.get(self.get("doctype"), []):
            fn(self, "before_save")

    def _check_unique(self):
        dt = self.get("doctype")
        for f in self._fk.unique.get(dt, ()):
            v = self.get(f)
            if v in (None, ""):
                continue
            for r in self._fk.db.t(dt).values():
                if r["name"] != self.get("name") and r.get(f) == v:
                    raise DuplicateEntryError("%s.%s=%s" % (dt, f, v))

    def _store(self):
        dt = self.get("doctype")
        data = copy.deepcopy(dict(self))
        for table, cdt in CHILD_TABLES.items():
            if table in data:
                self._fk.db.delete(cdt, {"parent": self.get("name")})
                for r in data[table]:
                    c = dict(r, parent=self.get("name"), parenttype=dt)
                    self._fk.db.t(cdt)[c["name"]] = c
        self._fk.db.t(dt)[self.get("name")] = data

    def insert(self, ignore_permissions=False, **kw):
        fk, dt = self._fk, self.get("doctype")
        namer = fk.autoname.get(dt)
        if namer:
            self["name"] = namer(self)
        if not self.get("name"):
            self["name"] = "%s-%04d" % (dt.replace(" ", "")[:6].upper(), next(fk.db._seq))
        if self["name"] in fk.db.t(dt):
            raise DuplicateEntryError(self["name"])
        now = str(fk.utils.now_datetime())
        self.setdefault("owner", fk.session.user)
        self.setdefault("creation", now)
        self["modified"] = now
        for table in CHILD_TABLES:
            for i, r in enumerate(self.get(table) or []):
                r.setdefault("name", "%s-row-%d" % (table, next(fk.db._seq)))
                r["idx"] = i + 1
        self._run_hooks()
        self._check_unique()
        self._store()
        fk.inserted.append((dt, self["name"]))
        return self

    def save(self, ignore_permissions=False, **kw):
        fk, dt = self._fk, self.get("doctype")
        stored = fk.db.t(dt).get(self.get("name"))
        object.__setattr__(self, "_before", FakeDoc(fk, copy.deepcopy(stored)) if stored else None)
        self._run_hooks()
        self._check_unique()
        self["modified"] = str(fk.utils.now_datetime())
        self._store()
        fk.saved.append((dt, self["name"]))
        return self

    def reload(self):
        fresh = self._fk.get_doc(self.get("doctype"), self.get("name"))
        self.clear()
        self.update(fresh)


# ----------------------------------------------------------------------------- frappe module
class _Flags(_dict):
    pass


class _Cache(object):
    def __init__(self, fk):
        self.fk = fk
        self.d = {}

    def get_value(self, k):
        hit = self.d.get(k)
        if not hit:
            return None
        v, exp = hit
        if exp is not None and self.fk.utils.now_datetime() >= exp:
            return None
        return v

    def set_value(self, k, v, expires_in_sec=None):
        exp = None
        if expires_in_sec:
            exp = self.fk.utils.now_datetime() + datetime.timedelta(seconds=expires_in_sec)
        self.d[k] = (v, exp)


class _Meta(object):
    def __init__(self, fields):
        self.fields = set(fields or ())

    def has_field(self, f):
        return f in self.fields


def _make_utils(fk):
    u = types.ModuleType("frappe.utils")
    fk._now = datetime.datetime(2026, 10, 16, 10, 0, 0)

    def getdate(v=None):
        if v is None:
            return datetime.date.fromisoformat(TODAY)
        if isinstance(v, datetime.datetime):
            return v.date()
        if isinstance(v, datetime.date):
            return v
        return datetime.date.fromisoformat(str(v)[:10])

    def get_datetime(v=None):
        if v is None:
            return fk._now
        if isinstance(v, datetime.datetime):
            return v
        if isinstance(v, datetime.date):
            return datetime.datetime(v.year, v.month, v.day)
        s = str(v).replace("T", " ")
        if len(s) == 10:
            s += " 00:00:00"
        return datetime.datetime.strptime(s[:19], "%Y-%m-%d %H:%M:%S")

    u.getdate = getdate
    u.get_datetime = get_datetime
    u.nowdate = lambda: str(fk._now.date())
    u.today = u.nowdate
    u.now_datetime = lambda: fk._now
    u.now = lambda: str(fk._now)
    u.add_days = lambda d, n: getdate(d) + datetime.timedelta(days=int(n))
    u.add_months = lambda d, n: getdate(d)
    u.get_last_day = lambda d: getdate(d)
    u.get_url = lambda *a: "https://team.example"
    u.cint = lambda v: int(v or 0)
    return u


class FakeFrappe(object):
    """State holder; .module is the object placed in sys.modules['frappe']."""

    def __init__(self):
        self.writes, self.inserted, self.saved, self.comments, self.errors = [], [], [], [], []
        self.notifications = []
        self.roles = {}
        self.departments = {}
        self.hooks = {}
        self.unique = {"PM Assignment Request": ("open_request_key", "open_task_key")}
        self.autoname = {"PM Task Seen": lambda d: "%s::%s" % (d["task"], d["user"])}
        self.doctypes = {"PM Task Seen", "PM Assignment Request", "Project", "Task"}
        self.meta_fields = {}
        self.utils = _make_utils(self)
        self.db = FakeDB(self)
        self.session = _dict(user="Administrator")
        self.module = self._build_module()

    # -- helpers for tests
    def set_user(self, user):
        self.session.user = user
        self.module.session.user = user

    def advance(self, **kw):
        self._now = self._now + datetime.timedelta(**kw)

    def add(self, dt, **row):
        row.setdefault("doctype", dt)
        row.setdefault("owner", "Administrator")
        row.setdefault("creation", str(self._now))
        row.setdefault("modified", str(self._now))
        children = {k: row.pop(k) for k in list(row) if k in CHILD_TABLES}
        self.db.t(dt)[row["name"]] = row
        for table, items in children.items():
            row[table] = []
            for i, it in enumerate(items):
                c = dict(it, name=it.get("name") or "%s-%s-%d" % (row["name"], table, i),
                         idx=i + 1, parent=row["name"], parenttype=dt)
                row[table].append(dict(c))
                self.db.t(CHILD_TABLES[table])[c["name"]] = c
        return row

    def row(self, dt, name):
        return self.db.t(dt).get(name)

    def load(self, modname):
        return importlib.import_module(modname)

    # -- module
    def _build_module(self):
        fk = self
        m = types.ModuleType("frappe")
        m.__path__ = []
        m._dict = _dict
        m.ValidationError = ValidationError
        m.PermissionError = PermissionError
        m.DoesNotExistError = DoesNotExistError
        m.DuplicateEntryError = DuplicateEntryError
        m.LinkExistsError = LinkExistsError
        exc = types.ModuleType("frappe.exceptions")
        for n in ("ValidationError", "PermissionError", "DoesNotExistError", "DuplicateEntryError",
                  "LinkExistsError", "QueryDeadlockError"):
            setattr(exc, n, globals()[n])
        m.exceptions = exc
        m.session = fk.session
        m.flags = _Flags()
        m.local = types.SimpleNamespace(flags=_Flags(), form_dict={})
        m.db = fk.db
        m.utils = fk.utils
        m._ = lambda s, *a: s
        m.whitelist = lambda *a, **k: (lambda f: f)
        m.cache = lambda: fk._cache
        fk._cache = _Cache(fk)
        m.as_json = lambda v, **k: json.dumps(v, default=str)
        m.get_traceback = lambda: "traceback"
        m.clear_cache = lambda **k: None
        m.enqueue = lambda *a, **k: None

        def throw(msg, exc=ValidationError, *a, **k):
            raise exc(msg)
        m.throw = throw

        def log_error(*a, **k):
            fk.errors.append(a or k)
        m.log_error = log_error

        def parse_json(v):
            return json.loads(v) if isinstance(v, str) else v
        m.parse_json = parse_json

        def get_roles(user=None):
            return list(fk.roles.get(user or fk.session.user, []))
        m.get_roles = get_roles

        def get_all(dt, filters=None, or_filters=None, fields=None, pluck=None, order_by=None,
                    start=0, page_length=None, limit_page_length=None, limit=None, **kw):
            if dt == "Employee":
                user = (filters or {}).get("user_id") if isinstance(filters, dict) else None
                return []
            if dt == "Workflow Document State":
                return []
            rows = fk.db.rows(dt, filters, or_filters)
            if order_by:
                for part in reversed([p.strip() for p in order_by.split(",") if p.strip()]):
                    bits = part.split()
                    f, desc = bits[0], (len(bits) > 1 and bits[1].lower() == "desc")
                    rows = sorted(rows, key=lambda r: str(_norm(r.get(f)) or ""), reverse=desc)
            lim = limit if limit is not None else (page_length if page_length is not None
                                                   else limit_page_length)
            rows = rows[int(start or 0):]
            if lim:
                rows = rows[:int(lim)]
            if pluck:
                return [r.get(pluck) for r in rows]
            fields = fields or ["name"]
            return [_dict({f: copy.deepcopy(r.get(f)) for f in fields}) for r in rows]
        m.get_all = get_all
        m.get_list = get_all

        def get_doc(dt, name=None, *a, **k):
            if isinstance(dt, dict):
                return FakeDoc(fk, copy.deepcopy(dt))
            row = fk.db.t(dt).get(name)
            if row is None:
                raise DoesNotExistError("%s %s not found" % (dt, name))
            return FakeDoc(fk, copy.deepcopy(row))
        m.get_doc = get_doc
        fk.get_doc = get_doc

        def get_meta(dt, cached=True):
            return _Meta(fk.meta_fields.get(dt))
        m.get_meta = get_meta

        def delete_doc(dt, name, **k):
            fk.db.t(dt).pop(name, None)
        m.delete_doc = delete_doc
        return m


def _submodules(fk):
    m = fk.module
    desk = types.ModuleType("frappe.desk")
    desk.__path__ = []
    form = types.ModuleType("frappe.desk.form")
    form.__path__ = []
    asg = types.ModuleType("frappe.desk.form.assign_to")

    def add(args):
        dt, name = args["doctype"], args["name"]
        row = fk.db.t(dt)[name]
        cur = json.loads(row.get("_assign") or "[]")
        for u in args["assign_to"]:
            if u not in cur:
                cur.append(u)
        row["_assign"] = json.dumps(cur)

    def remove(dt, name, user):
        row = fk.db.t(dt)[name]
        cur = [u for u in json.loads(row.get("_assign") or "[]") if u != user]
        row["_assign"] = json.dumps(cur)
    asg.add, asg.remove = add, remove
    model = types.ModuleType("frappe.model")
    model.__path__ = []
    wf = types.ModuleType("frappe.model.workflow")

    def apply_workflow(doc, action):
        raise AssertionError("apply_workflow must not be called by the redesign paths")
    wf.apply_workflow = apply_workflow
    wf.get_transitions = lambda doc: []
    wf.WorkflowTransitionError = WorkflowTransitionError
    document = types.ModuleType("frappe.model.document")
    document.Document = object
    m.desk, m.model = desk, model
    return {"frappe": m, "frappe.utils": fk.utils, "frappe.exceptions": m.exceptions,
            "frappe.desk": desk, "frappe.desk.form": form, "frappe.desk.form.assign_to": asg,
            "frappe.model": model, "frappe.model.workflow": wf,
            "frappe.model.document": document}


def _stub_pm_modules(fk):
    notif = types.ModuleType("ecentric_workspace.pm.api.notifications")

    def notify_users(users, subject, task_name, from_user=None, dedup_key=None,
                     event_type="task_assigned", severity=None, message="", due_suffix=None,
                     action_url=None):
        from_user = from_user or fk.session.user
        for u in users or []:
            if u and u != from_user and u != "Administrator":
                fk.notifications.append({"event_type": event_type, "user": u, "task": task_name,
                                         "subject": subject, "message": message,
                                         "suffix": due_suffix})

    def notify_task_assignment(users, task_name, subject="", actor=None):
        for u in users or []:
            fk.notifications.append({"event_type": "task_assigned", "user": u, "task": task_name,
                                     "subject": subject, "message": "", "suffix": None})

    def _task_recipients(doc, exclude=None):
        users = [doc.get("owner")] if doc.get("owner") else []
        users += json.loads(doc.get("_assign") or "[]")
        return [u for u in users if u and u != exclude]
    notif.notify_users = notify_users
    notif.notify_task_assignment = notify_task_assignment
    notif._task_recipients = _task_recipients
    labels = types.ModuleType("ecentric_workspace.pm.api.labels")
    labels.labels_for_tasks = lambda names: {}
    return {"ecentric_workspace.pm.api.notifications": notif,
            "ecentric_workspace.pm.api.labels": labels}


def install():
    """Fresh fake frappe + stubs; purge every cached ecentric_workspace module so each test
    module imports the CURRENT source (no stale state between test files)."""
    if SRC not in sys.path:
        sys.path.insert(0, SRC)
    for name in list(sys.modules):
        if name == "frappe" or name.startswith("frappe.") or name.startswith("ecentric_workspace"):
            sys.modules.pop(name, None)
    fk = FakeFrappe()
    sys.modules.update(_submodules(fk))
    sys.modules.update(_stub_pm_modules(fk))
    return fk


# ----------------------------------------------------------------------------- fixtures
GIVER = "giver@ec.vn"
ALICE = "alice@ec.vn"
BOB = "bob@ec.vn"
LEADER = "boss@ec.vn"
OUTSIDER = "out@ec.vn"


def seed_users(fk):
    for u, name in ((GIVER, "Gia Ver"), (ALICE, "Alice"), (BOB, "Bob"), (LEADER, "Boss"),
                    (OUTSIDER, "Out Sider")):
        fk.add("User", name=u, full_name=name, enabled=1, user_type="System User")
        fk.roles[u] = ["PM Member"]
    fk.roles[LEADER] = ["PM Member", "System Manager"]
    fk.roles["nopm@ec.vn"] = []


def task(fk, name, owner=GIVER, assign=None, state="To Do", **kw):
    row = dict(name=name, subject=kw.pop("subject", "Viec " + name), owner=owner,
               workflow_state=state, status="Completed" if state == "Done" else "Open",
               _assign=json.dumps(assign or []), project=kw.pop("project", None),
               parent_task=kw.pop("parent_task", None), exp_start_date=kw.pop("start", None),
               exp_end_date=kw.pop("end", None), completed_on=kw.pop("completed_on", None),
               is_group=kw.pop("is_group", 0), ec_auto_close=kw.pop("auto_close", 0),
               ec_review_required=kw.pop("review", 0), ec_split_parent=kw.pop("split", 0))
    row.update(kw)
    return fk.add("Task", **row)
