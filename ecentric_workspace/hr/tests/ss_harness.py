# Copyright (c) 2026, eCentric and contributors
"""Chay THAT mot Server Script trong fixtures/server_script.json voi `frappe` gia - KHONG can
bench. Dung cho test hanh vi (khong chi soi chuoi nguon) cua cac script ec_hr_*.

    fr = FakeFrappe(user="hr@x", form={"name": "LA-1", "action": "approve"})
    fr.on_sql("from `tabHas Role`", lambda q, p: [(1,)])
    fr.values[("Employee", "E1", "reports_to")] = "M1"
    fr.docs[("Leave Application", "LA-1")] = Doc(doctype="Leave Application", name="LA-1", ...)
    run("ec_hr_leave_decide", fr)

Truy van khong khai bao -> tra ve [] (rong). get_value khong khai bao -> None.
"""
import io
import json
import os
import types

APP = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def script(name):
    with io.open(os.path.join(APP, "fixtures", "server_script.json"), encoding="utf-8") as fh:
        return [r for r in json.load(fh) if r["name"] == name][0]["script"]


class Thrown(Exception):
    pass


class Doc(dict):
    """Ban ghi gia: doc/ghi ca kieu thuoc tinh lan kieu dict."""

    def __init__(self, fr=None, **kw):
        super().__init__(kw)
        object.__setattr__(self, "_fr", fr)
        object.__setattr__(self, "flags", types.SimpleNamespace())
        self.setdefault("docstatus", 0)

    def __getattr__(self, k):
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v

    def insert(self, ignore_permissions=False):
        fr = self._fr
        if fr is not None:
            fr.inserted.append(self)
            if not self.get("name"):
                self["name"] = "%s-%d" % (self.get("doctype"), len(fr.inserted))
            fr.docs[(self.get("doctype"), self["name"])] = self
        return self

    def save(self, ignore_permissions=False):
        if self._fr is not None:
            self._fr.saved.append(dict(self))
        return self

    def submit(self):
        self["docstatus"] = 1
        if self._fr is not None:
            self._fr.submitted.append(self.get("name"))
        return self

    def add_comment(self, *a, **k):
        if self._fr is not None:
            self._fr.comments.append(a)


class FakeFrappe(types.SimpleNamespace):
    def __init__(self, user="Guest", form=None, today="2026-11-03"):
        super().__init__()
        self.session = types.SimpleNamespace(user=user)
        self.form_dict = dict(form or {})
        self.response = {}
        self.docs = {}
        self.values = {}
        self.inserted, self.saved, self.submitted, self.comments = [], [], [], []
        self.set_values, self.logs = [], []
        self._sql = []
        fr = self

        def sql(q, params=None, *a, **k):
            for key, fn in fr._sql:
                if key in q:
                    return fn(q, params)
            return []

        def get_value(dt_, name, field=None, *a, **k):
            if isinstance(field, (list, tuple)):
                return fr.values.get((dt_, name, tuple(field)))
            return fr.values.get((dt_, name, field))

        def set_value(dt_, name, field, value=None, *a, **k):
            vals = field if isinstance(field, dict) else {field: value}
            fr.set_values.append((dt_, name, vals))
            d = fr.docs.get((dt_, name))
            if d is not None:
                d.update(vals)
            for f, v in vals.items():
                fr.values[(dt_, name, f)] = v

        self.db = types.SimpleNamespace(sql=sql, get_value=get_value, set_value=set_value,
                                        exists=lambda *a, **k: None,
                                        get_single_value=lambda *a, **k: None)
        utils = types.SimpleNamespace(nowdate=lambda: today)
        self.utils = utils

    def on_sql(self, key, fn):
        self._sql.append((key, fn))

    def throw(self, msg, *a, **k):
        raise Thrown(msg)

    def get_doc(self, dt_, name=None):
        if isinstance(dt_, dict):
            return Doc(self, **dt_)
        return self.docs[(dt_, name)]

    def log_error(self, *a, **k):
        self.logs.append(a)

    def get_traceback(self):
        return "tb"

    def notes_for(self, user):
        return [d for d in self.inserted
                if d.get("doctype") == "Notification Log" and d.get("for_user") == user]


def run(name, fr):
    exec(compile(script(name), name, "exec"), {"frappe": fr})
    return fr.response.get("message")
