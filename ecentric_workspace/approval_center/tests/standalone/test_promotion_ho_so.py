"""Promotion 29/09/2026: chon nhan su theo QUYEN XEM LUONG, thong tin hien tai lay o server,
duyet xong ghi chuc danh + tao SSA luong moi (khong sua SSA cu).

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_promotion_ho_so.py
"""
import importlib.util
import pathlib
import sys
import types

import pytest

APP = pathlib.Path(__file__).resolve().parents[2]
PKG = "ecentric_workspace.approval_center.features.promotion.application"


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


class Throw(Exception):
    pass


class Perm(Exception):
    pass


class W:
    pass


class Doc(Obj):
    @property
    def flags(self):
        return self.setdefault("_flags", Obj())

    def save(self, ignore_permissions=False):
        W.saved.append((self["doctype"], dict(self)))

    def insert(self, ignore_permissions=False):
        if W.boom_insert:
            raise RuntimeError("ssa loi")
        self["name"] = "SSA-NEW"
        W.inserted.append(dict(self))

    def submit(self):
        W.submitted.append(self["name"])

    def as_dict(self):
        return {k: v for k, v in self.items() if k != "_flags"}

    def set(self, k, v):
        self[k] = v


def build(visible=("E-A",)):
    W.saved, W.inserted, W.submitted, W.logs, W.notes, W.enq = [], [], [], [], [], []
    W.boom_insert = False
    W.visible = set(visible)
    W.emps = {"E-A": Doc(doctype="Employee", name="E-A", employee_name="An", department="Ops - EC",
                         designation="Engineer", grade="NV", employment_type="Full-time",
                         date_of_joining="2025-01-01", company="EC", user_id="an@x", status="Active"),
              "E-B": Doc(doctype="Employee", name="E-B", employee_name="Binh", department="Fin - EC",
                         designation="Accountant", company="EC", user_id="b@x", status="Active"),
              "E-ME": Doc(doctype="Employee", name="E-ME", employee_name="Me", user_id="me@x", status="Active")}
    W.ssa = [Obj(name="SSA-1", employee="E-A", docstatus=1, from_date="2026-01-01", base=20000000,
                 salary_structure="ST-1", company="EC", variable=0),
             Obj(name="SSA-2", employee="E-B", docstatus=1, from_date="2026-01-01", base=15000000,
                 salary_structure="ST-1", company="EC"),
             Obj(name="SSA-3", employee="E-ME", docstatus=1, from_date="2026-01-01", base=1, salary_structure="ST-1")]
    W.req = {}
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.PermissionError = Perm
    fr.session = types.SimpleNamespace(user="me@x")

    def throw(msg, exc=None):
        raise (exc or Throw)(msg)
    fr.throw = throw

    def get_list(dt, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None, distinct=False):
        assert dt == "Salary Structure Assignment"
        rows = [r for r in W.ssa if r.employee in W.visible]         # quyen cua nguoi dang nhap
        f = filters or {}
        if "employee" in f:
            rows = [r for r in rows if r.employee == f["employee"]]
        if "from_date" in f:
            rows = [r for r in rows if r.from_date <= f["from_date"][1]]
        rows = sorted(rows, key=lambda r: r.from_date, reverse=True)
        if pluck:
            return [r.get(pluck) for r in rows]
        return rows[:limit_page_length] if limit_page_length else rows
    fr.get_list = get_list

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None):
        if dt == "Salary Structure Assignment":                           # khong kiem quyen
            rows = [r for r in W.ssa if r.employee == filters["employee"] and r.from_date <= filters["from_date"][1]]
            rows = sorted(rows, key=lambda r: r.from_date, reverse=True)
            return [r.get(pluck) for r in rows][:1]
        if dt == "Employee":
            return [Obj(name=e.name, employee_name=e.employee_name, department=e.department,
                        designation=e.designation) for e in W.emps.values() if e.name in filters["name"][1]]
        if dt == "Designation":
            return ["Engineer", "Senior Engineer"]
        return ["cnb@x"]
    fr.get_all = get_all

    def get_value(dt, name, fields=None, as_dict=False, **k):
        if dt == "Employee":
            if isinstance(name, dict):
                return next((e.name for e in W.emps.values() if e.user_id == name["user_id"]), None)
            e = W.emps.get(name)
            if not e:
                return None
            return Obj({f: e.get(f) for f in fields}) if as_dict else e.get(fields)
        return W.req.get(name, {}).get(fields)
    fr.db = types.SimpleNamespace(get_value=get_value, exists=lambda dt, n: n in ("Engineer", "Senior Engineer"),
                                  set_value=lambda dt, n, v, *a, **k: W.req.setdefault(n, {}).update(v if isinstance(v, dict) else {v: a[0]}),
                                  commit=lambda: None, rollback=lambda: W.notes.append("rollback"))

    def get_doc(dt, name):
        if dt == "Employee":
            return W.emps[name]
        if dt == "Salary Structure Assignment":
            return Doc(doctype=dt, **next(r for r in W.ssa if r.name == name))
        return Doc(W.req[name])
    fr.get_doc = get_doc
    fr.new_doc = lambda dt: Doc(doctype=dt)
    fr.log_error = lambda title=None, message=None: W.logs.append(title)
    fr.get_traceback = lambda: "TB"
    fr.enqueue = lambda path, **k: W.enq.append((path, k))
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    utils = types.ModuleType("frappe.utils")
    import datetime
    utils.getdate = lambda v: datetime.date.fromisoformat(str(v)[:10])
    utils.nowdate = lambda: "2026-09-29"
    utils.now_datetime = lambda: "2026-09-29 10:00"
    fr.utils = utils
    eng = types.ModuleType("eng")
    eng.log_action = lambda *a, **k: None
    eng.notify = lambda users, msg, *a: W.notes.append((tuple(users), msg))
    wf = types.ModuleType("wf")
    wf.transitions = eng
    mods = {"frappe": fr, "frappe.utils": utils,
            "ecentric_workspace": types.ModuleType("a"), "ecentric_workspace.approval_center": types.ModuleType("b"),
            "ecentric_workspace.approval_center.shared": types.ModuleType("c"),
            "ecentric_workspace.approval_center.shared.workflow": wf,
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.features": types.ModuleType("d"),
            "ecentric_workspace.approval_center.features.promotion": types.ModuleType("e"),
            PKG: types.ModuleType("f")}
    sys.modules.update(mods)
    out = {}
    for n in ("employee_snapshot", "service"):
        spec = importlib.util.spec_from_file_location(PKG + "." + n, APP / "features" / "promotion" / "application" / (n + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[PKG + "." + n] = m
        setattr(mods[PKG], n, m)
        spec.loader.exec_module(m)
        out[n] = m
    return out["employee_snapshot"], out["service"]


@pytest.fixture
def env():
    saved = dict(sys.modules)
    yield build
    for k in list(sys.modules):
        if k not in saved:
            del sys.modules[k]
    sys.modules.update(saved)


def test_chi_thay_nguoi_minh_xem_duoc_luong_tru_chinh_minh(env):
    snap, _s = env(visible=("E-A", "E-ME"))
    assert [r.name for r in snap.candidates()] == ["E-A"]


def test_khong_quyen_luong_thi_khong_xem_duoc_thong_tin(env):
    snap, _s = env(visible=("E-A",))
    assert snap.snapshot("E-A")["current_salary"] == 20000000
    with pytest.raises(Perm):
        snap.snapshot("E-B")


def test_submit_ghi_de_thong_tin_hien_tai_bang_server(env):
    snap, s = env()
    d = Doc(doctype="EC Promotion Request", name="P-1", promoted_employee="E-A", full_name="Gia",
            current_salary=1, current_position="CEO", department="X")
    s._fill_from_employee(d)
    assert d.full_name == "An" and d.current_salary == 20000000 and d.current_position == "Engineer"
    assert d.department == "Ops - EC"


def test_submit_nguoi_khong_co_quyen_luong_bi_chan(env):
    snap, s = env(visible=())
    with pytest.raises(Perm):
        s._fill_from_employee(Doc(doctype="EC Promotion Request", name="P-1", promoted_employee="E-A"))


def _req(**kw):
    d = dict(doctype="EC Promotion Request", name="P-1", promoted_employee="E-A", proposed_position="Senior Engineer",
             current_salary=20000000, proposed_salary=28000000, effective_date_of_promotion="2026-10-01",
             approval_request="APR", requested_by="me@x")
    d.update(kw)
    W.req["P-1"] = d


def test_duyet_xong_chay_nen(env):
    snap, s = env()
    s.on_final_approval("P-1")
    assert W.enq[0][0].endswith("promotion.application.service.apply_to_employee") and W.enq[0][1]["enqueue_after_commit"]


def test_ghi_chuc_danh_va_tao_ssa_moi_khong_sua_ssa_cu(env):
    snap, s = env()
    _req()
    assert s.apply_to_employee("P-1") == {"applied": True, "ok": True}
    assert W.emps["E-A"]["designation"] == "Senior Engineer"
    (new,) = W.inserted
    assert new["base"] == 28000000 and new["from_date"] == "2026-10-01" and new["salary_structure"] == "ST-1"
    assert new["employee"] == "E-A" and new.get("docstatus") is None and W.submitted == ["SSA-NEW"]
    assert W.ssa[0].base == 20000000                                        # SSA cu giu nguyen
    assert W.req["P-1"]["applied_at"] and "Lương mới" in W.req["P-1"]["apply_result"]
    assert s.apply_to_employee("P-1") == {"skipped": True}                 # idempotent
    assert len(W.inserted) == 1


def test_luong_khong_doi_thi_khong_tao_ssa(env):
    snap, s = env()
    _req(proposed_salary=20000000)
    s.apply_to_employee("P-1")
    assert not W.inserted and W.emps["E-A"]["designation"] == "Senior Engineer"


def test_chuc_danh_khong_co_trong_danh_muc_thi_bao_tay(env):
    snap, s = env()
    _req(proposed_position="Chua co", proposed_salary=20000000)
    assert s.apply_to_employee("P-1")["ok"] is False
    assert W.emps["E-A"]["designation"] == "Engineer" and W.notes


def test_loi_tao_ssa_thi_rollback_va_bao(env):
    snap, s = env()
    _req()
    W.boom_insert = True
    assert s.apply_to_employee("P-1") == {"applied": False}
    assert "rollback" in W.notes and W.logs and "LỖI" in W.req["P-1"]["apply_result"]
    assert not W.req["P-1"].get("applied_at")
