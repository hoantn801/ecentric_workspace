# Copyright (c) 2026, eCentric and contributors
"""Frappe GIA trong bo nho cho test Dot 0 HR (phieu rieng tu, nguoi theo doi, chan tu duyet,
chuyen nguoi duyet, gan phieu, Phe duyet dot xuat). Chay CODE THAT cua engine / privacy /
approval_links: cai `frappe` gia vao sys.modules TRUOC khi import, roi import module that tu repo.

Khong phai frappe day du: chi nhung gi cac module tren goi. Thieu ham -> AttributeError ro rang."""
import datetime as _dt
import json
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))


class Err(Exception):
    pass


class PermErr(Err):
    pass


class D(dict):
    def __getattr__(self, k):
        try:
            return self[k]
        except KeyError:
            raise AttributeError(k)

    def __setattr__(self, k, v):
        self[k] = v


class Doc(object):
    def __init__(self, world, doctype, row):
        object.__setattr__(self, "_w", world)
        object.__setattr__(self, "doctype", doctype)
        object.__setattr__(self, "_row", row)

    def __getattr__(self, k):
        row = object.__getattribute__(self, "_row")
        if k in row:
            return row[k]
        if k == "meta":
            return self._w.get_meta(self.doctype)
        return None

    def __setattr__(self, k, v):
        self._row[k] = v

    def get(self, k, d=None):
        v = self._row.get(k, d)
        return d if v is None else v

    def set(self, k, v):
        self._row[k] = v

    def update(self, d):
        self._row.update(d)

    def append(self, k, v):
        self._row.setdefault(k, []).append(D(v))

    def as_dict(self):
        return dict(self._row)

    def insert(self, ignore_permissions=False):
        self._w._insert(self.doctype, self._row)
        return self

    def save(self, ignore_permissions=False):
        if not self._row.get("name"):
            return self.insert()
        self._w.store.setdefault(self.doctype, {})[self._row["name"]] = self._row
        return self

    def is_new(self):
        return not self._row.get("name")

    def get_doc_before_save(self):
        return self._row.get("_before")


class Meta(object):
    def __init__(self, fields):
        self.fields = [types.SimpleNamespace(fieldname=f, fieldtype="Data") for f in fields]
        self.title_field = "request_title" if "request_title" in fields else None

    def has_field(self, f):
        return any(x.fieldname == f for x in self.fields)


class World(object):
    def __init__(self):
        self.reset()

    def reset(self):
        self.store = {}
        self.roles = {}
        self.metas = {}
        self.notified = []
        self.logs = []
        self.shares = []
        self.conf = {}
        self._seq = 0
        self.now = _dt.datetime(2026, 11, 23, 10, 0, 0)

    # ---- seed helpers ----
    def add(self, doctype, row):
        row = D(row)
        if not row.get("name"):
            self._seq += 1
            row["name"] = "%s-%04d" % (doctype.replace(" ", "-"), self._seq)
        self.store.setdefault(doctype, {})[row["name"]] = row
        return row

    def user(self, name, roles=(), enabled=1):
        self.add("User", {"name": name, "enabled": enabled, "user_type": "System User",
                          "full_name": name.split("@")[0]})
        self.roles[name] = list(roles)
        for r in roles:
            self.add("Has Role", {"parent": name, "parenttype": "User", "role": r})

    def rows(self, doctype, **flt):
        return [r for r in self.store.get(doctype, {}).values() if self._match(r, flt)]

    # ---- matching ----
    def _match(self, row, filters):
        if filters is None:
            return True
        if isinstance(filters, (list, tuple)):
            filters = {f[0]: [f[1], f[2]] for f in filters}
        for k, v in filters.items():
            cur = row.get(k)
            if isinstance(v, (list, tuple)) and len(v) == 2 and isinstance(v[0], str) \
                    and v[0] in ("in", "not in", ">", "<", ">=", "<=", "!=", "is", "like"):
                op, val = v
                if op == "in" and cur not in val:
                    return False
                if op == "not in" and cur in val:
                    return False
                if op == "!=" and cur == val:
                    return False
                if op == ">" and not (cur is not None and cur > val):
                    return False
                if op == "<" and not (cur is not None and cur < val):
                    return False
                if op == "is" and ((val == "set") != bool(cur)):
                    return False
                if op == "like" and str(val).strip("%") not in str(cur or ""):
                    return False
            elif cur != v:
                return False
        return True

    def _insert(self, doctype, row):
        if not row.get("name"):
            self._seq += 1
            row["name"] = "%s-%04d" % (doctype.replace(" ", "-"), self._seq)
        row.setdefault("creation", self.now + _dt.timedelta(seconds=self._seq))
        self.store.setdefault(doctype, {})[row["name"]] = D(row) if not isinstance(row, D) else row
        return row

    # ---- frappe API ----
    def get_all(self, doctype, filters=None, fields=None, pluck=None, order_by=None,
                limit_page_length=None, distinct=False, limit=None, **kw):
        rows = [r for r in self.store.get(doctype, {}).values() if self._match(r, filters)]
        rows.sort(key=lambda r: (r.get("level_no") or 0, str(r.get("creation") or ""), r["name"]))
        n = limit_page_length or limit
        if n:
            rows = rows[:n]
        if pluck:
            return [r.get(pluck) for r in rows]
        if fields:
            return [D({f: r.get(f) for f in fields}) for r in rows]
        return [D({"name": r["name"]}) for r in rows]

    get_list = get_all

    def get_value(self, doctype, name, fieldname="name", as_dict=False, for_update=False, **kw):
        if isinstance(name, dict):
            hit = [r for r in self.store.get(doctype, {}).values() if self._match(r, name)]
            row = hit[0] if hit else None
        else:
            row = self.store.get(doctype, {}).get(name)
        if row is None:
            return None
        if isinstance(fieldname, (list, tuple)):
            out = D({f: row.get(f) for f in fieldname})
            return out if as_dict else tuple(out.values())
        return row.get(fieldname)

    def exists(self, doctype, name=None):
        if name is None:
            return doctype in self.store or doctype in ("Web Page",)
        if isinstance(name, dict):
            hit = [r for r in self.store.get(doctype, {}).values() if self._match(r, name)]
            return hit[0]["name"] if hit else None
        return name if name in self.store.get(doctype, {}) else None

    def count(self, doctype, filters=None):
        return len([r for r in self.store.get(doctype, {}).values() if self._match(r, filters)])

    def set_value(self, doctype, name, field, value=None, update_modified=True):
        row = self.store[doctype][name]
        if isinstance(field, dict):
            row.update(field)
        else:
            row[field] = value

    def has_column(self, doctype, col):
        return self.get_meta(doctype).has_field(col)

    def sql(self, *a, **k):
        return []

    def commit(self):
        pass

    def rollback(self):
        pass

    def get_meta(self, doctype):
        return self.metas.get(doctype) or Meta([])

    def get_doc(self, doctype, name=None):
        if isinstance(doctype, dict):
            d = D(doctype)
            dt = d.pop("doctype")
            return Doc(self, dt, d)
        row = self.store.get(doctype, {}).get(name)
        if row is None:
            raise Err("%s %s not found" % (doctype, name))
        return Doc(self, doctype, row)

    def new_doc(self, doctype):
        return Doc(self, doctype, D())

    def delete_doc(self, doctype, name, **kw):
        self.store.get(doctype, {}).pop(name, None)

    def get_roles(self, user=None):
        return list(self.roles.get(user or self.session.user, []))

    def throw(self, msg, exc=None):
        raise (exc or Err)(msg)

    def log_error(self, *a, **k):
        self.logs.append((a, k))

    def get_traceback(self):
        return ""

    def logger(self, *a, **k):
        return types.SimpleNamespace(info=lambda *x, **y: None, warning=lambda *x, **y: None)


def install(world=None):
    """Cai frappe gia vao sys.modules. Tra (world, frappe_module)."""
    world = world or World()
    fr = types.ModuleType("frappe")
    fr._world = world
    fr.db = world
    fr.session = types.SimpleNamespace(user="Administrator")
    world.session = fr.session
    fr.local = types.SimpleNamespace(message_log=[])
    fr.flags = types.SimpleNamespace(mute_messages=False, ignore_permissions=False)
    fr.conf = world.conf
    fr.ValidationError = Err
    fr.PermissionError = PermErr
    fr.DoesNotExistError = Err
    fr._ = lambda s, *a: s
    for name in ("get_all", "get_list", "get_doc", "new_doc", "delete_doc", "get_roles", "throw",
                 "log_error", "get_traceback", "logger", "get_meta"):
        setattr(fr, name, getattr(world, name))
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    fr.parse_json = lambda s: json.loads(s) if isinstance(s, str) else s
    fr.as_json = json.dumps
    fr.get_attr = lambda p: (lambda *a, **k: None)
    fr.get_module = lambda p: __import__(p, fromlist=["x"])
    fr.enqueue = lambda *a, **k: None
    fr.msgprint = lambda *a, **k: None
    fr.defaults = types.SimpleNamespace(get_global_default=lambda k: None)
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: world.now
    utils.add_to_date = lambda d, hours=0, minutes=0, days=0, **k: d + _dt.timedelta(
        hours=hours, minutes=minutes, days=days)
    utils.getdate = lambda v=None: (v if isinstance(v, _dt.date) and not isinstance(v, _dt.datetime)
                                    else (v.date() if isinstance(v, _dt.datetime)
                                          else _dt.date.fromisoformat(str(v)[:10])))
    utils.nowdate = lambda: world.now.date().isoformat()
    utils.get_url = lambda: "https://x"
    utils.get_datetime = lambda v: v
    fr.utils = utils
    share = types.ModuleType("frappe.share")

    def _add_docshare(dt, name, user, read=1, flags=None, **k):
        world.shares.append((dt, name, user))
        world.add("DocShare", {"share_doctype": dt, "share_name": name, "user": user, "read": read})
    share.add_docshare = _add_docshare
    share.add = _add_docshare
    fr.share = share
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    sys.modules["frappe.share"] = share
    nc = types.ModuleType("ecentric_workspace.notification_center.events")

    def _publish(event_type, user, subject, **kw):
        world.notified.append((user, subject, kw.get("severity")))
    nc.publish_notification_event = _publish
    sys.modules["ecentric_workspace.notification_center.events"] = nc
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    return world, fr
