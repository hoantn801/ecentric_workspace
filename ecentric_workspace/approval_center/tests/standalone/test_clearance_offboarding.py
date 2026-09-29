"""Nghi viec 29/09/2026: Don duyet xong -> ghi ngay nghi vao ho so + tu tao Clearance;
job 00:30 -> Left + khoa tai khoan (tru System Manager / tai khoan dich vu).

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_clearance_offboarding.py
"""
import datetime
import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]           # ecentric_workspace/


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


class Throw(Exception):
    pass


class W:
    pass


class Doc(Obj):
    @property
    def flags(self):
        return self.setdefault("_flags", Obj())

    def save(self, ignore_permissions=False):
        if W.fail_save.get(self.get("doctype"), set()) & {self.get("name")}:
            raise RuntimeError("save loi")
        if self.get("name") is None:
            W.seq += 1
            self["name"] = "%s-%d" % (self["doctype"][:3], W.seq)
        W.tables.setdefault(self["doctype"], {})[self["name"]] = self
        W.saves.append((self["doctype"], self["name"], dict(self)))

    def is_new(self):
        return self.get("name") is None

    def set(self, k, v):
        self[k] = v


def load(relpath, modname):
    spec = importlib.util.spec_from_file_location(modname, ROOT / relpath)
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m


def build(today="2026-10-01"):
    W.tables = {"Employee": {}, "User": {}, "EC Approval Request": {}, "EC Resignation Request": {},
                "EC Clearance Request": {},
                "Has Role": {"hr1": Obj(name="hr1", role="HR Manager", parenttype="User", parent="hr@x")}}
    W.roles, W.saves, W.logs, W.notes, W.enq, W.events, W.fail_save = {}, [], [], [], [], [], {}
    W.seq, W.submitted, W.conf, W.actions = 0, [], {}, []
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.session = types.SimpleNamespace(user="Administrator")
    fr.flags = Obj()
    fr.conf = W.conf

    def throw(msg, *a):
        raise Throw(msg)
    fr.throw = throw
    fr.get_roles = lambda u=None: W.roles.get(u, [])

    def _match(row, filters):
        for k, v in (filters or {}).items():
            if isinstance(v, list):
                op, val = v
                if op == "<" and not (row.get(k) and str(row.get(k)) < val):
                    return False
                if op == "in" and row.get(k) not in val:
                    return False
            elif row.get(k) != v:
                return False
        return True

    def get_value(dt, filt, fields=None, as_dict=False, for_update=False):
        rows = W.tables.get(dt, {})
        row = rows.get(filt) if isinstance(filt, str) else next(
            (r for r in rows.values() if _match(r, filt)), None)
        if row is None:
            return None
        if isinstance(fields, (list, tuple)):
            return Obj({f: row.get(f) for f in fields})
        return row.get(fields)

    def set_value(dt, name, vals, *a, **k):
        if isinstance(vals, str):
            vals = {vals: a[0]}
        W.tables[dt][name].update(vals)
    fr.db = types.SimpleNamespace(get_value=get_value, set_value=set_value, commit=lambda: None,
                                  rollback=lambda: W.notes.append("rollback"),
                                  exists=lambda dt, n: n in W.tables.get(dt, {}))
    W.tables["User"]["hr@x"] = Doc(doctype="User", name="hr@x", enabled=1)
    fr.get_doc = lambda dt, name: W.tables[dt][name]
    fr.new_doc = lambda dt: Doc(doctype=dt, name=None)

    def get_all(dt, filters=None, fields=None, pluck=None, **k):
        rows = [r for r in W.tables.get(dt, {}).values() if _match(r, filters)]
        if pluck:
            return [r.get(pluck) for r in rows]
        return [Obj(r) for r in rows]
    fr.get_all = get_all
    fr.log_error = lambda title=None, message=None: W.logs.append(title)
    fr.get_traceback = lambda: "TB"
    fr.enqueue = lambda path, **k: W.enq.append((path, k))
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    utils = types.ModuleType("frappe.utils")
    utils.getdate = lambda v: v if isinstance(v, datetime.date) else datetime.date.fromisoformat(str(v)[:10])
    utils.nowdate = lambda: today
    utils.now_datetime = lambda: "2026-09-29 10:00:00"
    utils.add_days = lambda d, n: d
    fr.utils = utils
    eng = types.ModuleType("eng")
    eng.submit = lambda dt, name, t, user: W.submitted.append((dt, name, t, user)) or "APR-CLR"
    eng.notify = lambda users, msg, *a: W.notes.append((tuple(users), msg))
    eng.log_action = lambda *a, **k: W.actions.append(a)
    eng.request_label = lambda dt, n: n
    ncev = types.ModuleType("ncev")
    ncev.publish_notification_event = lambda *a, **k: W.events.append((a, k))
    pk = {}
    for name in ("ecentric_workspace", "ecentric_workspace.hr", "ecentric_workspace.hr.offboarding",
                 "ecentric_workspace.approval_center", "ecentric_workspace.approval_center.shared",
                 "ecentric_workspace.approval_center.features",
                 "ecentric_workspace.approval_center.features.clearance_request",
                 "ecentric_workspace.approval_center.features.clearance_request.application",
                 "ecentric_workspace.approval_center.features.resignation",
                 "ecentric_workspace.approval_center.features.resignation.application",
                 "ecentric_workspace.notification_center"):
        pk[name] = types.ModuleType(name)
    wf = types.ModuleType("wf")
    wf.transitions = eng
    sys.modules.update(pk)
    sys.modules.update({"frappe": fr, "frappe.utils": utils,
                        "ecentric_workspace.approval_center.shared.workflow": wf,
                        "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
                        "ecentric_workspace.notification_center.events": ncev})
    off = load("hr/offboarding/service.py", "ecentric_workspace.hr.offboarding.service")
    pk["ecentric_workspace.hr.offboarding"].service = off
    job = load("hr/offboarding/lock_left_employees_job.py", "ecentric_workspace.hr.offboarding.lock_left_employees_job")
    clr = load("approval_center/features/clearance_request/application/service.py",
               "ecentric_workspace.approval_center.features.clearance_request.application.service")
    pk["ecentric_workspace.approval_center.features.clearance_request.application"].service = clr
    res = load("approval_center/features/resignation/application/service.py",
               "ecentric_workspace.approval_center.features.resignation.application.service")
    return fr, off, job, clr, res


@pytest.fixture
def env():
    saved = dict(sys.modules)
    yield build
    for k in list(sys.modules):
        if k not in saved:
            del sys.modules[k]
    sys.modules.update(saved)


def emp(name, user, status="Active", relieving=None, reports_to=None, **kw):
    W.tables["Employee"][name] = Doc(doctype="Employee", name=name, user_id=user, status=status,
                                     relieving_date=relieving, employee_name=name.lower(),
                                     reports_to=reports_to, department="Ops - EC", company="EC", **kw)
    if user:
        W.tables["User"][user] = Doc(doctype="User", name=user, enabled=1)


# --------------------------- job 00:30 ---------------------------
def test_qua_ngay_cuoi_thi_left_va_khoa(env):
    fr, off, job, _c, _r = env()
    emp("E1", "a@x", relieving="2026-09-30")
    emp("E2", "b@x", relieving="2026-10-01")          # hom nay la ngay cuoi -> CHUA khoa
    emp("E3", "c@x", relieving=None)
    out = job.run()
    assert out["results"] == [("E1", "locked")]
    assert W.tables["Employee"]["E1"]["status"] == "Left" and W.tables["User"]["a@x"]["enabled"] == 0
    assert W.tables["Employee"]["E2"]["status"] == "Active" and W.tables["User"]["b@x"]["enabled"] == 1
    assert W.events                                           # thong bao tong


def test_khong_go_role_va_idempotent(env):
    fr, off, job, _c, _r = env()
    emp("E1", "a@x", relieving="2026-09-30")
    W.tables["User"]["a@x"]["roles"] = ["EC CnB"]
    job.run()
    assert W.tables["User"]["a@x"]["roles"] == ["EC CnB"]
    assert job.run()["due"] == 0                              # da Left -> khong lay lai


def test_system_manager_khong_tu_khoa(env):
    fr, off, job, _c, _r = env()
    emp("E1", "boss@x", relieving="2026-09-30")
    W.roles["boss@x"] = ["System Manager"]
    out = job.run()
    assert out["results"] == [("E1", "skipped_protected")]
    assert W.tables["User"]["boss@x"]["enabled"] == 1 and W.tables["Employee"]["E1"]["status"] == "Active"
    assert "KHÔNG khoá" in W.events[0][1]["message"]


def test_mot_nguoi_loi_khong_chan_nguoi_khac(env):
    fr, off, job, _c, _r = env()
    emp("E1", "a@x", relieving="2026-09-29")
    emp("E2", "b@x", relieving="2026-09-30")
    W.fail_save["Employee"] = {"E1"}
    out = job.run()
    assert ("E1", "error") in out["results"] and ("E2", "locked") in out["results"]
    assert any("E1" in (t or "") for t in W.logs)


def test_kill_switch(env):
    fr, off, job, _c, _r = env()
    emp("E1", "a@x", relieving="2026-09-29")
    W.conf["ec_offboarding_lock_disabled"] = 1
    assert job.run() == {"skipped": "disabled"}
    assert W.tables["User"]["a@x"]["enabled"] == 1


def test_administrator_bo_qua(env):
    fr, off, job, _c, _r = env()
    emp("E1", "Administrator", relieving="2026-09-29")
    assert job.run()["results"] == [("E1", "skipped_service")]


# --------------------------- don duyet xong ---------------------------
def _resn(status="Approved"):
    W.tables["EC Approval Request"]["APR-R"] = Obj(name="APR-R", approval_status=status)
    W.tables["EC Resignation Request"]["RESN-1"] = Doc(
        doctype="EC Resignation Request", name="RESN-1", approval_request="APR-R",
        employee_email="a@x", last_working_day="2026-10-15", submitted_at="2026-09-20 09:00:00",
        resignation_reason="Personal", requested_by="a@x", creation="2026-09-20 09:00:00")


def test_duyet_xong_chay_nen_sau_commit(env):
    fr, off, job, clr, res = env()
    res.on_final_approval("RESN-1")
    path, k = W.enq[0]
    assert path.endswith("resignation.application.service.after_approval") and k["enqueue_after_commit"]


def test_sau_duyet_ghi_ngay_va_tao_clearance(env):
    fr, off, job, clr, res = env()
    emp("E1", "a@x", reports_to="EM")
    emp("EM", "lm@x")
    _resn()
    res.after_approval("RESN-1")
    e = W.tables["Employee"]["E1"]
    assert str(e["relieving_date"]) == "2026-10-15" and str(e["resignation_letter_date"]) == "2026-09-20"
    assert e["status"] == "Active"                            # chua doi status
    (c,) = W.tables["EC Clearance Request"].values()
    assert c["requested_by"] == "a@x" and c["line_manager"] == "lm@x" and c["approval_request"] == "APR-CLR"
    assert W.submitted[0][2] == "CLEARANCE_REQUEST"
    res.after_approval("RESN-1")                              # chay lai: khong tao them
    assert len(W.tables["EC Clearance Request"]) == 1 and len(W.submitted) == 1


def test_don_chua_duyet_khong_tao_clearance_va_bao(env):
    fr, off, job, clr, res = env()
    emp("E1", "a@x")
    _resn(status="Pending")
    res.after_approval("RESN-1")
    assert not W.tables["EC Clearance Request"] and any("Clearance" in (t or "") for t in W.logs)
    assert any("Clearance" in n[1] for n in W.notes if isinstance(n, tuple))


def test_khong_co_ho_so_van_tao_clearance(env):
    fr, off, job, clr, res = env()
    _resn()
    res.after_approval("RESN-1")
    assert len(W.tables["EC Clearance Request"]) == 1         # requested_by fallback nguoi nop
    assert any("ho so" in (t or "") for t in W.logs)


def test_khong_tao_clearance_bang_tay(env):
    fr, off, job, clr, res = env()
    with pytest.raises(Throw):
        clr.prepare_draft(Doc(doctype="EC Clearance Request", name=None))
