"""Frappe gia lap trong bo nho cho test HR v2 (23/11/2026) - KHONG can bench.

Nap module THAT tu repo (sys.path = goc repo) voi `frappe` gia + engine (transitions) gia +
participants gia. Moi test goi `boot()` de co mot the gioi sach."""
import datetime
import pathlib
import sys
import types

ROOT = pathlib.Path(__file__).resolve().parents[4]          # goc repo (chua ecentric_workspace/)


class Throw(Exception):
    pass


class PermErr(Throw):
    pass


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


def _d(v):
    if isinstance(v, datetime.datetime):
        return v.date()
    if isinstance(v, datetime.date):
        return v
    return datetime.date.fromisoformat(str(v)[:10])


class World:
    pass


W = World()


def _cmp(cur, op, val):
    if op == "=":
        return cur == val
    if op == "!=":
        return cur != val
    if op == "in":
        return cur in val
    if op == "not in":
        return cur not in val
    if op == "is":
        return bool(cur) if val == "set" else not cur
    if op == "like":
        return str(val).strip("%").lower() in str(cur or "").lower()
    if op == "between":
        return cur is not None and str(val[0]) <= str(cur) <= str(val[1])
    if cur is None:
        return False
    a, b = str(cur), str(val)
    return {">=": a >= b, "<=": a <= b, ">": a > b, "<": a < b}[op]


def match(row, filters):
    if not filters:
        return True
    items = filters.items() if isinstance(filters, dict) else [(f[0], f[1:]) for f in filters]
    for k, v in items:
        if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str) and v[0] in (
                "=", "!=", "in", "not in", "is", "like", "between", ">=", "<=", ">", "<"):
            if not _cmp(row.get(k), v[0], v[1]):
                return False
        elif row.get(k) != v:
            return False
    return True


class Doc(Obj):
    @property
    def flags(self):
        return self.setdefault("_flags", Obj())

    def is_new(self):
        return not self.get("name") or self["name"] not in W.tables.get(self["doctype"], {})

    def set(self, k, v):
        self[k] = v

    def append(self, k, row):
        self.setdefault(k, []).append(Obj(row))

    def save(self, ignore_permissions=False):
        dt = self["doctype"]
        hook = W.hooks.get(dt)
        if hook:
            hook(self)
        auto = {"EC Approval Process": "process_code", "EC Approval SLA Policy": "policy_code",
                "EC Approval Business Calendar": "calendar_code"}.get(dt)
        if not self.get("name") and auto and self.get(auto):
            self["name"] = self[auto]                     # autoname field:<x> nhu DocType that
        if not self.get("name"):
            W.seq += 1
            self["name"] = "%s-%d" % (dt.replace(" ", "")[:6].upper(), W.seq)
        W.tables.setdefault(dt, {})[self["name"]] = self
        W.saves.append((dt, self["name"]))
        return self

    insert = save

    def add_comment(self, *a, **k):
        W.comments.append((self.get("doctype"), self.get("name"), a))

    def as_dict(self):
        return Obj(self)


def put(dt, name, **vals):
    d = Doc(doctype=dt, name=name, **vals)
    W.tables.setdefault(dt, {})[name] = d
    return d


def _get_value(dt, filt, fields=None, as_dict=False, for_update=False, **k):
    rows = W.tables.get(dt, {})
    if isinstance(filt, str):
        row = rows.get(filt)
    else:
        row = next((r for r in rows.values() if match(r, filt)), None)
    if row is None:
        return None
    if isinstance(fields, (list, tuple)):
        return Obj({f: row.get(f) for f in fields})
    return row.get(fields or "name")


def _set_value(dt, name, vals, val=None, update_modified=True):
    if isinstance(vals, str):
        vals = {vals: val}
    W.tables[dt][name].update(vals)
    W.sets.append((dt, name, dict(vals)))


def _get_all(dt, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, **k):
    rows = [r for r in W.tables.get(dt, {}).values() if match(r, filters)]
    if order_by:
        key, _, direction = order_by.partition(" ")
        rows.sort(key=lambda r: str(r.get(key) or ""), reverse=direction.strip() == "desc")
    if limit_page_length:
        rows = rows[:limit_page_length]
    if pluck:
        return [r.get(pluck) for r in rows]
    if fields:
        return [Obj({f: r.get(f) for f in fields}) for r in rows]
    return [Obj(name=r.get("name")) for r in rows]


def boot(today="2026-11-23", user="u@x", roles=None):
    W.tables, W.seq, W.saves, W.sets, W.logs, W.notes, W.actions = {}, 0, [], [], [], [], []
    W.comments, W.submitted, W.cancelled, W.enq, W.hooks, W.attrs = [], [], [], [], {}, {}
    W.roles = roles or {}
    W.role_users = {}
    W.today = _d(today)
    for k in [m for m in sys.modules if m == "frappe" or m.startswith("frappe.")
              or m.startswith("ecentric_workspace")]:
        del sys.modules[k]
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    fr = types.ModuleType("frappe")
    fr._ = lambda s, *a: s
    fr.session = Obj(user=user)
    fr.flags = Obj()
    fr.PermissionError = PermErr
    fr.DoesNotExistError = Throw
    fr.ValidationError = Throw

    def throw(msg, exc=None, *a, **k):
        raise (exc if isinstance(exc, type) and issubclass(exc, Exception) else Throw)(msg)
    fr.throw = throw
    fr.get_roles = lambda u=None: list(W.roles.get(u or fr.session.user, []))

    def get_doc(dt, name=None):
        if isinstance(dt, dict):
            d = Doc(dt)
            return d
        return W.tables[dt][name]
    fr.get_doc = get_doc
    fr.new_doc = lambda dt: Doc(doctype=dt, name=None)
    fr.delete_doc = lambda dt, name, **k: W.tables[dt].pop(name, None)
    fr.log_error = lambda *a, **k: W.logs.append(k.get("title") or (a[0] if a else None))
    fr.get_traceback = lambda: "TB"
    fr.enqueue = lambda path, **k: W.enq.append((path, k))
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    fr.parse_json = lambda v: __import__("json").loads(v)

    def get_attr(path):
        if path in W.attrs:
            return W.attrs[path]
        raise AttributeError(path)
    fr.get_attr = get_attr
    fr.get_module = lambda p: __import__(p, fromlist=["x"])
    fr.logger = lambda *a, **k: types.SimpleNamespace(info=lambda *x: None)
    fr.defaults = types.SimpleNamespace(get_global_default=lambda k: "EC")
    fr.db = types.SimpleNamespace(
        get_value=_get_value, set_value=_set_value, get_all=_get_all,
        exists=lambda dt, f=None: (f in W.tables.get(dt, {})) if isinstance(f, str) else (
            any(match(r, f) for r in W.tables.get(dt, {}).values()) if f is not None else bool(W.tables.get(dt))),
        count=lambda dt, f=None: len([r for r in W.tables.get(dt, {}).values() if match(r, f)]),
        sql=lambda *a, **k: [], commit=lambda: W.notes.append("commit"),
        rollback=lambda: W.notes.append("rollback"), has_column=lambda *a: True,
        get_single_value=lambda *a: "EC")
    fr.get_all = _get_all
    fr.get_list = _get_all
    utils = types.ModuleType("frappe.utils")
    utils.getdate = lambda v=None: _d(v) if v else W.today
    utils.nowdate = lambda: str(W.today)
    utils.now_datetime = lambda: datetime.datetime.combine(W.today, datetime.time(10, 0))
    utils.add_days = lambda d, n: _d(d) + datetime.timedelta(days=n)
    utils.strip_html = lambda s: s
    utils.get_url = lambda: "https://x"
    fr.utils = utils
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils

    # --- engine gia (transitions) - ghi lai moi loi goi
    import ecentric_workspace.approval_center.shared.workflow as wf_pkg     # noqa: real __init__
    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")

    def submit(dt, name, atype, requester, process_code=None, activate_first_level=True,
               skip_level_nos=None, skip_reason=None):
        W.seq += 1
        req = "AR-%d" % W.seq
        put("EC Approval Request", req, approval_status="Pending", requested_by=requester,
            reference_doctype=dt, reference_name=name, approval_type=atype, current_level=1)
        W.submitted.append(Obj(dt=dt, name=name, atype=atype, requester=requester,
                               skip=skip_level_nos, skip_reason=skip_reason, req=req))
        return req

    def cancel(req, actor=None, reason=None):
        if not (reason or "").strip():
            raise Throw("reason")
        r = W.tables["EC Approval Request"][req]
        if r.approval_status in ("Approved", "Rejected", "Cancelled"):
            raise Throw("terminal")
        r.approval_status = "Cancelled"
        W.cancelled.append((req, actor, reason))
    eng.submit = submit
    eng.cancel = cancel
    eng.resubmit = lambda req, actor=None, restart=False: W.notes.append(("resubmit", req, restart))
    eng.log_action = lambda req, action, actor, *a, **k: W.actions.append(
        Obj(req=req, action=action, actor=actor, comment=k.get("comment")))
    eng.notify = lambda users, subject, *a, **k: W.notes.append(("notify", tuple(users), subject))
    eng.request_label = lambda dt, n, *a: n
    eng.role_of = lambda s: (s or "")[6:].strip() if (s or "").startswith("Role: ") else None
    sys.modules[eng.__name__] = eng
    wf_pkg.transitions = eng
    parts = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.participants")
    parts.active_role_users = lambda role: sorted(W.role_users.get(role, []))

    def participant_rows(entries):
        out = []
        for e in entries:
            if e.lower().startswith("role:"):
                out.append({"source_type": "Role", "role": e[5:].strip()})
            else:
                out.append({"source_type": "User", "user": e})
        return out
    parts.participant_rows = participant_rows
    sys.modules[parts.__name__] = parts
    wf_pkg.participants = parts
    return fr


def user(name, roles=(), enabled=1):
    put("User", name, enabled=enabled, user_type="System User")
    W.roles[name] = list(roles)
    for r in roles:
        W.role_users.setdefault(r, []).append(name)
        put("Role", r)


def load(dotted):
    import importlib
    return importlib.import_module(dotted)
