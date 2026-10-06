"""Promotion 29/09/2026: chon nhan su theo QUYEN XEM LUONG (has_permission tren SSA MOI NHAT),
thong tin hien tai lay o server, duyet xong ghi chuc danh + tao SSA luong moi o DRAFT (khong sua
SSA cu). Review Phan quyen P1-P3: an luong voi nguoi xem khong xem duoc, buoc 1 = nguoi dau tien
tren chuoi reports_to xem duoc luong, khong ghi so tien vao nhat ky, SSA moi khong chep so du
thue / phong / chuc danh.

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
        if getattr(W, "boom_save", False):
            raise RuntimeError("save loi")
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


def build(visible=("E-A",), perms=None):
    W.saved, W.inserted, W.submitted, W.logs, W.notes, W.enq = [], [], [], [], [], []
    W.boom_insert = False
    W.boom_save = False
    W.slip = False
    W.visible = set(visible)
    #: quyen doc SSA theo user: {user: set(ten SSA)}; nguoi dang nhap = me@x
    W.perms = perms or {}
    W.emps = {"E-A": Doc(doctype="Employee", name="E-A", employee_name="An", department="Ops - EC",
                         designation="Engineer", grade="NV", employment_type="Full-time",
                         date_of_joining="2025-01-01", company="EC", user_id="an@x", status="Active",
                         reports_to="E-LEAD"),
              "E-LEAD": Doc(doctype="Employee", name="E-LEAD", user_id="lead@x", status="Active", reports_to="E-HEAD"),
              "E-HEAD": Doc(doctype="Employee", name="E-HEAD", user_id="head@x", status="Active", reports_to=None),
              "E-B": Doc(doctype="Employee", name="E-B", employee_name="Binh", department="Fin - EC",
                         designation="Accountant", company="EC", user_id="b@x", status="Active"),
              "E-ME": Doc(doctype="Employee", name="E-ME", employee_name="Me", user_id="me@x", status="Active")}
    W.ssa = [Obj(name="SSA-0", employee="E-A", docstatus=1, from_date="2025-01-01", base=15000000,
                 salary_structure="ST-0", company="EC", department="Old - EC"),
             Obj(name="SSA-1", employee="E-A", docstatus=1, from_date="2026-01-01", base=20000000,
                 salary_structure="ST-1", company="EC", variable=0, department="Ops - EC",
                 designation="Engineer", grade="NV", taxable_earnings_till_date=5, tax_deducted_till_date=1),
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

    def has_permission(dt, ptype="read", doc=None, user=None):
        user = user or fr.session.user
        if doc is None:
            return bool(W.perms.get(user)) or (user == "me@x" and bool(W.visible))
        allowed = W.perms.get(user)
        if allowed is None and user == "me@x":
            allowed = {r.name for r in W.ssa if r.employee in W.visible}
        return doc in (allowed or set())
    fr.has_permission = has_permission
    fr.get_list = lambda *a, **k: (_ for _ in ()).throw(AssertionError("khong duoc dung get_list"))

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None):
        if dt == "Salary Structure Assignment":                           # khong kiem quyen
            rows = [r for r in W.ssa if r.docstatus == filters.get("docstatus", 1)]
            if "employee" in filters:
                rows = [r for r in rows if r.employee == filters["employee"]]
            if "from_date" in filters:
                rows = [r for r in rows if r.from_date <= filters["from_date"][1]]
            rows = sorted(rows, key=lambda r: r.from_date, reverse=True)
            vals = [r.get(pluck) for r in rows]
            return vals[:limit_page_length] if limit_page_length else vals
        if dt == "Employee":
            return [Obj(name=e.name, employee_name=e.employee_name, department=e.department,
                        designation=e.designation) for e in W.emps.values() if e.name in filters["name"][1]]
        if dt == "Designation":
            return ["Engineer", "Senior Engineer"]
        return ["cnb@x"]
    fr.get_all = get_all

    def get_value(dt, name, fields=None, as_dict=False, **k):
        if dt == "Salary Structure Assignment":
            r = next(x for x in W.ssa if x.name == name)
            return Obj({f: r.get(f) for f in fields}) if as_dict else r.get(fields)
        if dt == "User":
            return 1
        if dt == "Employee":
            if isinstance(name, dict):
                return next((e.name for e in W.emps.values() if e.user_id == name["user_id"]), None)
            e = W.emps.get(name)
            if not e:
                return None
            return Obj({f: e.get(f) for f in fields}) if as_dict else e.get(fields)
        return W.req.get(name, {}).get(fields)
    fr.db = types.SimpleNamespace(get_value=get_value, exists=lambda dt, n: (n in ("Engineer", "Senior Engineer")) if isinstance(n, str) else W.slip,
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


def test_quyen_theo_ssa_MOI_NHAT_khong_theo_ssa_cu(env):
    # truong phong cu doc duoc SSA-0 (phong cu) nhung khong doc duoc SSA-1 hien hanh
    snap, _s = env(perms={"me@x": {"SSA-0"}})
    assert snap.can_view_salary("E-A") is False and snap.candidates() == []


def test_khong_quyen_luong_thi_khong_xem_duoc_thong_tin(env):
    snap, _s = env(visible=("E-A",))
    x = snap.snapshot("E-A")
    assert x["base_salary"] == 20000000 and "current_salary" not in x   # 01/10: base chi de tham khao
    with pytest.raises(Perm):
        snap.snapshot("E-B")


def test_submit_ghi_de_thong_tin_hien_tai_bang_server_nhung_GIU_luong_gross_tu_nhap(env):
    snap, s = env()
    d = Doc(doctype="EC Promotion Request", name="P-1", promoted_employee="E-A", full_name="Gia",
            current_salary=35000000, current_position="CEO", department="X")
    s._fill_from_employee(d)
    assert d.full_name == "An" and d.current_position == "Engineer"
    assert d.current_salary == 35000000           # 01/10: gross do nguoi de xuat nhap, KHONG lay base
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


def test_ghi_chuc_danh_va_KHONG_tao_ssa_ma_bao_cnb(env):
    # 01/10/2026: luong tren phieu la GROSS -> khong ghi vao SSA.base; C&B tu tach base/thuong.
    snap, s = env()
    _req()
    assert s.apply_to_employee("P-1") == {"applied": True, "ok": False}
    assert W.emps["E-A"]["designation"] == "Senior Engineer"
    assert W.inserted == [] and W.submitted == []                          # khong tao SSA nao
    assert W.ssa[1].base == 20000000                                        # SSA cu giu nguyen
    res = W.req["P-1"]["apply_result"]
    assert W.req["P-1"]["applied_at"] and "gross" in res and "C&B" in res and "2026-10-01" in res
    assert "28000000" not in res and "28.000.000" not in res and "20000000" not in res   # P2
    assert W.notes                                                          # bao C&B
    assert s.apply_to_employee("P-1") == {"skipped": True}                 # idempotent


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


def test_loi_ghi_ho_so_thi_rollback_va_bao(env):
    snap, s = env()
    _req()
    W.boom_save = True
    assert s.apply_to_employee("P-1") == {"applied": False}
    assert "rollback" in W.notes and W.logs and "LỖI" in W.req["P-1"]["apply_result"]
    assert not W.req["P-1"].get("applied_at")


def test_ky_luong_da_chot_thi_canh_bao(env):
    snap, s = env()
    _req()
    W.slip = True
    s.apply_to_employee("P-1")
    assert "phiếu lương đã chốt" in W.req["P-1"]["apply_result"]


def test_buoc_1_la_nguoi_dau_tien_tren_chuoi_xem_duoc_luong(env):
    snap, s = env(perms={"lead@x": set(), "head@x": {"SSA-1"}})
    assert snap.salary_reviewer("E-A", "me@x") == "head@x"                 # bo qua Lead
    assert snap.salary_reviewer("E-A", "head@x") is None                   # trung nguoi gui -> bo buoc
    snap2, _ = env(perms={"lead@x": set(), "head@x": set()})
    assert snap2.salary_reviewer("E-A", "me@x") is None


def test_an_luong_voi_nguoi_xem_khong_co_quyen(env):
    snap, s = env(perms={"me@x": set()})
    b = {"promoted_employee": "E-A", "current_salary": 1, "proposed_salary": 2, "incentives": "x"}
    s.redact_business(b)
    assert b["current_salary"] is None and b["proposed_salary"] is None and b["incentives"] is None
    assert b["salary_hidden"] == 1
    snap, s = env(perms={"me@x": {"SSA-1"}})
    b = {"promoted_employee": "E-A", "current_salary": 1, "proposed_salary": 2}
    s.redact_business(b)
    assert b["current_salary"] == 1 and "salary_hidden" not in b


def test_an_luong_loi_thi_an_het(env):
    snap, s = env()
    b = {"promoted_employee": "E-KHONG-CO", "current_salary": 1}
    s.redact_business(b)
    assert b["current_salary"] is None
