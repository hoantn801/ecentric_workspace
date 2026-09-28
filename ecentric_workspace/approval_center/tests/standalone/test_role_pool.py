"""Nhom nguoi duyet theo ROLE (25/09/2026) - xem shared/workflow/role_pool.py.

Hai lo hong da xay ra that:
  * EC-CTR-2026-00023: anh Lam bi go EC Finance luc 17:39 24/09, 25/09 van duyet duoc cap
    Finance vi dong "Role: EC Finance" duoc chot luc nop.
  * EC-CTR-2026-00014/00022/00026: chi Phuong (HOF dich danh o cap 3) nam trong nhom
    EC Finance o cap 2, duyet cap 2 xong thi cap HOF tu bo qua.
Chay doc lap, frappe gia, moi module nap thanh ban RIENG:
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_role_pool.py
"""
import copy
import io
import os
import sys
import types
from datetime import datetime

import pytest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_WF = os.path.join(_ROOT, "approval_center", "shared", "workflow")
FIN, HOF, CEO = "Role: EC Finance", "phuong.nguyen1@x", "lam.nguyen@x"


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return dict.get(self, k)

    def __setattr__(self, k, v):
        self[k] = v


def _frappe(roles, store=None, log=None):
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr._dict = Obj
    fr.session = types.SimpleNamespace(user="hoan@x")
    fr.get_roles = lambda u=None: sorted(roles.get(u, ()))
    fr.log_error = lambda title=None, message=None, **k: (log if log is not None else []).append((title, message))
    fr.get_traceback = lambda: "tb"
    fr.throw = lambda m, *a, **k: (_ for _ in ()).throw(RuntimeError(m))
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: datetime(2026, 9, 25, 10, 0)
    utils.add_to_date = lambda d, **k: d
    utils.getdate = lambda v: v
    fr.utils = utils
    st = store if store is not None else {}

    def match(r, f):
        for k, v in (f or {}).items():
            if isinstance(v, list):
                op, val = v
                if op == "in" and r.get(k) not in val:
                    return False
                if op == "like" and not str(r.get(k) or "").startswith(val.rstrip("%")):
                    return False
            elif r.get(k) != v:
                return False
        return True

    def get_all(dt, filters=None, fields=None, pluck=None, **k):
        rows = [Obj(r) for r in st.get(dt, {}).values() if match(r, filters)]
        return [r[pluck] for r in rows] if pluck else rows

    def set_value(dt, name, f, v=None, update_modified=True):
        st[dt][name].update(f if isinstance(f, dict) else {f: v})

    fr.get_all = get_all
    fr.db = types.SimpleNamespace(set_value=set_value, get_value=lambda *a, **k: None,
                                  exists=lambda *a, **k: None, commit=lambda: None,
                                  rollback=lambda: None)
    return fr


def _exec(path, fr, name, extra_mods=None):
    saved = {k: sys.modules.get(k) for k in ["frappe", "frappe.utils"] + list(extra_mods or {})}
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = fr.utils
    sys.modules.update(extra_mods or {})
    try:
        mod = types.ModuleType(name)
        exec(compile(io.open(path, encoding="utf-8").read(), path, "exec"), mod.__dict__)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _engine(roles=None, store=None):
    return _exec(os.path.join(_WF, "transitions.py"), _frappe(roles or {}, store), "_eng_rieng")


# ------------------------------------------------------------------ luat thuan
def test_role_of_va_row_still_eligible():
    e = _engine()
    assert e.role_of("Role: EC Finance") == "EC Finance"
    assert e.role_of("Configured User") is None and e.role_of(None) is None
    assert e.row_still_eligible("Role: EC Finance", "a", roles=["EC Finance"])
    assert not e.row_still_eligible("Role: EC Finance", "a", roles=["EC CEO"])
    assert e.row_still_eligible("Configured User", "a", roles=[])          # dich danh: khong hoi role


def _lvl(no, *parts):
    return Obj(level_no=no, participants=[Obj(participant_purpose="Approver", **p) for p in parts])


LEVELS = [_lvl(1, dict(source_type="Reference Department Head")),
          _lvl(2, dict(source_type="Role", role="EC Finance")),
          _lvl(3, dict(source_type="User", user=HOF)),
          _lvl(4, dict(source_type="User", user=CEO))]


def test_named_seats_after_chi_tinh_cap_SAU_va_chi_dich_danh():
    s = _engine().named_seats_after(LEVELS)
    assert s[1] == {HOF, CEO} and s[2] == {HOF, CEO} and s[3] == {CEO} and s[4] == set()


def test_drop_own_seat_bo_nguoi_co_ghe_sau_nhung_khong_de_cap_rong():
    e = _engine()
    pool = [("a@x", FIN), (HOF, FIN), (CEO, FIN)]
    assert e.drop_own_seat(pool, {HOF, CEO}) == [("a@x", FIN)]
    assert e.drop_own_seat([(HOF, FIN)], {HOF}) == [(HOF, FIN)]            # con moi minh -> giu
    assert e.drop_own_seat([(HOF, "Configured User")], {HOF}) == [(HOF, "Configured User")]


def test_build_snapshot_loai_HOF_va_CEO_khoi_nhom_finance():
    store = {"EC Approval Request Level": {}, "EC Approval Request Approver": {}}
    e = _engine(store=store)
    made = []

    class Doc(Obj):
        def insert(self, ignore_permissions=False):
            self.name = "D%d" % len(made)
            made.append(dict(self))
            return self
    e.frappe.get_doc = lambda d: Doc(d)
    pools = {1: [("tp@x", "Reference Department Head")],
             2: [("a@x", FIN), (HOF, FIN), (CEO, FIN), ("b@x", FIN)],
             3: [(HOF, "Configured User")], 4: [(CEO, "Configured User")]}
    e.resolve_participants = lambda parts, req, context=None: list(
        pools[{("Reference Department Head",): 1, ("Role",): 2}.get(
            tuple(p.source_type for p in parts), 3 if parts[0].get("user") == HOF else 4)])
    e._skip_earlier_duplicate_levels = lambda req: None
    e.grant_read_to_snapshot_approvers = lambda req: None
    e.build_snapshot(Obj(name="AR", reference_doctype="X", reference_name="Y"), None, LEVELS, "req@x")
    got = [(m["level_no"], m["approver"]) for m in made if m["doctype"] == "EC Approval Request Approver"]
    assert (2, HOF) not in got and (2, CEO) not in got
    assert (2, "a@x") in got and (2, "b@x") in got and (3, HOF) in got and (4, CEO) in got


def test_actor_pending_row_chan_dong_role_da_mat():
    store = {"EC Approval Request Approver": {
        "R1": dict(name="R1", approval_request="AR", level_no=2, approver=CEO, status="Pending", source=FIN),
        "R2": dict(name="R2", approval_request="AR", level_no=2, approver="a@x", status="Pending", source=FIN),
        "R3": dict(name="R3", approval_request="AR", level_no=4, approver=CEO, status="Pending",
                   source="Configured User")}}
    e = _engine(roles={CEO: {"EC CEO"}, "a@x": {"EC Finance"}}, store=store)
    assert e._actor_pending_row("AR", 2, CEO) is None                     # 00023: mat role -> khong bam duoc
    assert e._actor_pending_row("AR", 2, "a@x") == "R2"
    assert e._actor_pending_row("AR", 4, CEO) == "R3"                     # ghe CEO dich danh van nguyen
    assert "_actor_pending_row(request_name" in io.open(os.path.join(_WF, "transitions.py")).read()


# ------------------------------------------------------------------ nut tren giao dien
def _cap(roles, source):
    fr = _frappe(roles)
    fr.db.get_value = lambda dt, f, field: source
    return _exec(os.path.join(_ROOT, "approval_center", "shared", "requests", "capabilities.py"),
                 fr, "_cap_rieng", {"ecentric_workspace.approval_center.shared.workflow.permissions":
                                    types.SimpleNamespace(can_view_request=lambda *a, **k: True)})


@pytest.mark.parametrize("source,roles,ok", [
    (FIN, {"EC Finance"}, True), (FIN, {"EC CEO"}, False),
    ("Configured User", set(), True), (None, set(), True)])
def test_capabilities_va_engine_cung_mot_luat(source, roles, ok):
    cap = _cap({"u": roles}, source)
    assert bool(cap.still_holds_role("AR", 2, "u")) is ok
    assert _engine().row_still_eligible(source, "u", roles=roles) is ok


@pytest.mark.parametrize("roles,ok", [({"EC Finance"}, True), ({"EC CEO"}, False)])
def test_nut_tren_giao_dien_tat_khi_mat_role(roles, ok):
    cap = _cap({"u": roles}, FIN)
    cap.frappe.db.exists = lambda dt, f=None: "R1"
    req = Obj(name="AR", approval_status="Pending", current_level=2)
    assert bool(cap._pending_row(req, "u")) is ok


# ------------------------------------------------------------------ don dong tren phieu dang mo
def _world():
    ap = {}

    def add(n, req, lv, u, st, src):
        ap[n] = dict(name=n, approval_request=req, level_no=lv, approver=u, status=st, source=src)
    # Phieu 1: dang o cap 2 - chi Phuong co ghe HOF, bot mat role, 2 nguoi finance that.
    add("a1", "AR1", 2, "fa@x", "Pending", FIN)
    add("a2", "AR1", 2, "fb@x", "Pending", FIN)
    add("a3", "AR1", 2, HOF, "Pending", FIN)
    add("a4", "AR1", 2, "bot@x", "Pending", FIN)
    add("a5", "AR1", 3, HOF, "Pending", "Configured User")
    add("a6", "AR1", 4, CEO, "Pending", "Configured User")
    # Phieu 2: con dung cap 1 - cap 2 chua mo (khong dong ToDo, khong SLA).
    add("b1", "AR2", 2, "fa@x", "Pending", FIN)
    add("b2", "AR2", 2, HOF, "Pending", FIN)
    add("b3", "AR2", 3, HOF, "Pending", "Configured User")
    # Phieu 3: da Approved - khong ai dung.
    add("c1", "AR3", 2, HOF, "Pending", FIN)
    add("c2", "AR3", 2, "fa@x", "Pending", FIN)
    add("c3", "AR3", 3, HOF, "Pending", "Configured User")
    # Phieu 4: nguoi duy nhat mat role -> GIU.
    add("d1", "AR4", 2, "bot@x", "Pending", FIN)
    store = {"EC Approval Request Approver": ap,
             "EC Approval Request": {
                 "AR1": dict(name="AR1", approval_status="Pending", current_level=2,
                             reference_doctype="EC Contract Review Request", reference_name="CTR1"),
                 "AR2": dict(name="AR2", approval_status="Pending", current_level=1,
                             reference_doctype="EC Contract Review Request", reference_name="CTR2"),
                 "AR3": dict(name="AR3", approval_status="Approved", current_level=0,
                             reference_doctype="EC Contract Review Request", reference_name="CTR3"),
                 "AR4": dict(name="AR4", approval_status="Pending", current_level=2,
                             reference_doctype="EC Contract Review Request", reference_name="CTR4")},
             "ToDo": {"t1": dict(name="t1", reference_type="EC Contract Review Request", reference_name="CTR1",
                                 allocated_to=HOF, status="Open"),
                      "t2": dict(name="t2", reference_type="EC Contract Review Request", reference_name="CTR1",
                                 allocated_to="fa@x", status="Open"),
                      "t3": dict(name="t3", reference_type="EC Contract Review Request", reference_name="CTR1",
                                 allocated_to="bot@x", status="Open")}}
    roles = {"fa@x": {"EC Finance"}, "fb@x": {"EC Finance"}, HOF: {"EC Finance", "EC HOF"},
             "bot@x": set(), CEO: {"EC CEO"}}
    return store, roles


def _pool(store, roles, log=None):
    fr = _frappe(roles, store, log)
    calls = []
    eng = _engine(roles, store)
    tr = types.ModuleType("tr")
    for k in ("ROLE_LABEL", "drop_own_seat", "named_seats_after", "role_of", "row_still_eligible"):
        setattr(tr, k, getattr(eng, k))
    tr.log_action = lambda req, action, actor, level_no=None, **k: calls.append(
        ("log", req, action, actor, level_no, k.get("related_user"), k.get("comment")))
    tr._engine_maintain_assign = lambda dt, name, user, add=True: calls.append(("assign", name, user, add))
    tr._sla = lambda: types.SimpleNamespace(on_approver_removed=lambda **k: calls.append(("sla", k["user"], k["level_no"])))
    pkg = "ecentric_workspace.approval_center.shared.workflow"
    wf = types.ModuleType(pkg)
    wf.transitions = tr
    mods = {"ecentric_workspace": types.ModuleType("e"), "ecentric_workspace.approval_center": types.ModuleType("a"),
            "ecentric_workspace.approval_center.shared": types.ModuleType("s"), pkg: wf, pkg + ".transitions": tr}
    m = _exec(os.path.join(_WF, "role_pool.py"), fr, "_pool_rieng", mods)
    return m, calls, mods, fr


def _run(m, mods, fn, *a, **k):
    saved = {x: sys.modules.get(x) for x in list(mods) + ["frappe"]}
    sys.modules.update(mods)
    sys.modules["frappe"] = m.frappe
    try:
        return fn(*a, **k)
    finally:
        for x, v in saved.items():
            if v is None:
                sys.modules.pop(x, None)
            else:
                sys.modules[x] = v


def st(store, n):
    return store["EC Approval Request Approver"][n]["status"]


def test_tidy_don_dung_dong_va_giu_lich_su():
    store, roles = _world()
    log = []
    m, calls, mods, fr = _pool(store, roles, log)
    kq = _run(m, mods, m.tidy_open_rows, actor="hoan@x")
    assert (st(store, "a3"), st(store, "a4")) == ("Skipped", "Skipped")        # HOF + bot khoi cap 2
    assert (st(store, "a1"), st(store, "a2"), st(store, "a5"), st(store, "a6")) == ("Pending",) * 4
    assert st(store, "b2") == "Skipped" and st(store, "b1") == "Pending"
    assert st(store, "c1") == "Pending"                                          # phieu da xong: khong dung
    assert st(store, "d1") == "Pending"                                          # nguoi cuoi: giu
    assert any("nguoi duyet cuoi" in (t or "") for t, _m in log)
    assert "vai tro EC Finance" in store["EC Approval Request Approver"]["a4"]["comment"]
    assert "ghe rieng" in store["EC Approval Request Approver"]["a3"]["comment"]
    todo = store["ToDo"]
    assert (todo["t1"]["status"], todo["t3"]["status"], todo["t2"]["status"]) == ("Cancelled", "Cancelled", "Open")
    assert ("sla", HOF, 2) in calls and ("sla", "bot@x", 2) in calls
    assert not [c for c in calls if c[0] == "sla" and c[2] != 2]               # AR2 chua mo cap 2
    assert not [c for c in calls if c[0] == "assign" and c[1] == "CTR2"]      # ... nen khong dung _assign
    logs = [c for c in calls if c[0] == "log"]
    assert {(c[1], c[5]) for c in logs} == {("AR1", HOF), ("AR1", "bot@x"), ("AR2", HOF)}
    assert all(c[2] == "Skipped" and c[3] == "hoan@x" for c in logs)
    assert len([k for k in kq if k[4] == "Skipped"]) == 3


def test_tidy_chay_lai_khong_lam_gi_them():
    store, roles = _world()
    m, calls, mods, fr = _pool(store, roles)
    _run(m, mods, m.tidy_open_rows, actor="hoan@x")
    snap, n = copy.deepcopy(store), len(calls)
    _run(m, mods, m.tidy_open_rows, actor="hoan@x")
    assert store == snap and len(calls) == n


def test_tidy_loc_theo_nguoi():
    store, roles = _world()
    m, calls, mods, fr = _pool(store, roles)
    _run(m, mods, m.tidy_open_rows, users=["bot@x"], actor="hoan@x")
    assert st(store, "a4") == "Skipped" and st(store, "a3") == "Pending"


def test_on_user_update_chi_chay_khi_bi_go_role_va_nuot_loi():
    store, roles = _world()
    m, calls, mods, fr = _pool(store, roles)
    seen = []
    m.tidy_open_rows = lambda users=None, actor=None: seen.append(users)

    def user(r_before, r_after):
        d = Obj(name="bot@x", roles=[Obj(role=r) for r in r_after])
        d.get_doc_before_save = lambda: Obj(roles=[Obj(role=r) for r in r_before])
        return d
    m.on_user_update(user(["EC Finance", "X"], ["X"]))
    m.on_user_update(user(["X"], ["X", "EC Finance"]))                          # them role: khong don
    assert seen == [["bot@x"]]
    def hong(**k):
        raise RuntimeError("hong")
    m.tidy_open_rows = hong
    m.on_user_update(user(["EC Finance"], []))                                   # khong duoc nem


# ------------------------------------------------------------------ SLA + hooks + patch
def test_sla_exclude_chi_dau_viec_cua_nguoi_do():
    fr = _frappe({})
    obl = types.SimpleNamespace(exclude_obligation=lambda n, r: done.append((n, r)) or "Excluded")
    done = []
    const = types.SimpleNamespace(DT_OBLIGATION="O", EXCL_ANY_ONE="x", PAUSE_WAITING_INFO="p",
                                  STATUS_OPEN="Open", TYPE_APPROVAL_STEP="t")
    mods = {"ecentric_workspace": types.ModuleType("e"), "ecentric_workspace.sla": types.ModuleType("s"),
            "ecentric_workspace.sla.application": types.SimpleNamespace(obligation_service=obl),
            "ecentric_workspace.sla.application.obligation_service": obl,
            "ecentric_workspace.sla.constants": const}
    h = _exec(os.path.join(_ROOT, "sla", "application", "hooks.py"), fr, "_sla_rieng", mods)
    h._open_rows = lambda dt, name, lv, attempt=None: [{"name": "o1", "owner_user": "a"},
                                                        {"name": "o2", "owner_user": "b"}]
    assert h.exclude_approver_obligation("X", "Y", 2, "b", "mat role") == 1
    assert done == [("o2", "mat role")]


def test_hooks_gan_User_on_update():
    src = io.open(os.path.join(_ROOT, "hooks.py"), encoding="utf-8").read()
    src = src.replace("from . import __version__ as app_version", "app_version = 'x'", 1)
    ns = {"__name__": "_hooks_rieng"}
    exec(compile(src, "hooks.py", "exec"), ns)
    assert "ecentric_workspace.approval_center.shared.workflow.role_pool.on_user_update" in \
        ns["doc_events"]["User"]["on_update"]


def test_p209_goi_dung_ham_cua_hook_va_khong_nem():
    got, log = [], []
    fr = _frappe({}, log=log)
    rp = types.SimpleNamespace(tidy_open_rows=lambda actor=None, users=None: got.append(actor) or
                               [("AR1", 2, "u", "ly do", "Skipped")])
    pkg = "ecentric_workspace.approval_center.shared.workflow"
    wf = types.ModuleType(pkg)
    wf.role_pool = rp
    mods = {"ecentric_workspace": types.ModuleType("e"), "ecentric_workspace.approval_center": types.ModuleType("a"),
            "ecentric_workspace.approval_center.shared": types.ModuleType("s"), pkg: wf, pkg + ".role_pool": rp}
    m = _exec(os.path.join(_ROOT, "approval_center", "patches", "p209_tidy_role_rows.py"), fr, "_p209", mods)
    _run(types.SimpleNamespace(frappe=fr), mods, m.execute)
    assert got == ["hoan.tran@ecentric.vn"] and "AR1 L2 u" in log[-1][1]
    rp.tidy_open_rows = lambda **k: 1 / 0
    _run(types.SimpleNamespace(frappe=fr), mods, m.execute)
    assert log[-1][1].startswith("LOI")
