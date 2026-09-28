"""Setup + patch cua chuoi Hiring -> Offer -> New Staff Preparation (28/09/2026).

  * OFFER_REQUEST-V1: L1 Line manager (Reference User Field line_manager) -> L2 EC CnB -> L3 EC HOF
    -> L4 EC CEO, moi cap Any One (Hoan chot 28/09);
  * NEW_STAFF_PREPARATION-V1: MOT cap "Each Group", 4 nhom Lead HR / HOF / CnB / Operation;
  * HIRING_REQUEST-V1: them Fulfiller Role EC Recruiter.
Harness chep tu test_cnb_role_approver.py (frappe gia, participants/user_rules THAT).
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_offer_nsp_setup.py
"""
import copy
import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TUAN, HUONG = "tuan.ly@ecentric.vn", "huong.pham@ecentric.vn"


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return dict.get(self, k)

    def __setattr__(self, k, v):
        self[k] = v


class World:
    def __init__(self, cnb=(TUAN, HUONG), disabled=(), empty_roles=()):
        self.users = {u: Obj(enabled=0 if u in disabled else 1, user_type="System User")
                      for u in (TUAN, HUONG, "phuong.nguyen1@ecentric.vn", "lam.nguyen@ecentric.vn",
                                "cnb.ecentric@ecentric.vn", "dong.diep@ecentric.vn", "Administrator")}
        self.roles = {"EC CnB", "EC HOF", "EC CEO", "EC CnB Payroll", "EC Ops System", "EC Recruiter"}
        self.has_role = [("EC CnB", u) for u in cnb] + [
            ("EC HOF", "phuong.nguyen1@ecentric.vn"), ("EC CEO", "lam.nguyen@ecentric.vn"),
            ("EC CnB Payroll", "cnb.ecentric@ecentric.vn"), ("EC Ops System", "dong.diep@ecentric.vn")]
        self.has_role = [(r, u) for r, u in self.has_role if r not in empty_roles]
        self.procs, self.levels = {}, {}
        self.saved = None
        self.saves = []
        self.boom = None


def make_frappe(w):
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    fr.PermissionError = PermissionError
    fr.session = types.SimpleNamespace(user="hoan.tran@ecentric.vn")
    fr.get_roles = lambda u=None: ["System Manager"]

    def throw(msg, exc=None):
        raise (exc or Exception)(msg)
    fr.throw = throw

    class Doc(Obj):
        def set(self, f, v):
            self[f] = list(v)

        def append(self, f, row):
            self.setdefault(f, [])
            self[f].append(Obj(row))

        def save(self, ignore_permissions=False):
            if w.boom and self.get("approval_process") == w.boom:
                raise RuntimeError("boom")
            if self.doctype == "EC Approval Level":
                self.name = self.name or "%s-L%s" % (self.approval_process, self.level_no)
                w.levels[self.name] = self
            else:
                self.name = self.name or self.process_code
                w.procs[self.name] = self
            w.saves.append(self.name)

    fr.new_doc = lambda dt: Doc(doctype=dt, participants=[])
    fr.get_doc = lambda dt, name: copy.deepcopy((w.levels if dt == "EC Approval Level" else w.procs)[name])

    def exists(dt, name=None):
        if dt == "Role":
            return name in w.roles
        if dt == "EC Approval Type":
            return True
        if dt == "EC Approval Process":
            return name in w.procs
        return False

    def get_value(dt, name, field=None, as_dict=False, **k):
        if dt == "User":
            u = w.users.get(name)
            return Obj(u) if u else None
        if dt == "EC Approval Process":
            key = name.get("process_code") if isinstance(name, dict) else name
            p = w.procs.get(key)
            if not p:
                return None
            if isinstance(field, (list, tuple)):
                return Obj({f: p.get(f) for f in field})
            return p.get(field)
        return None

    fr.db = types.SimpleNamespace(exists=exists, get_value=get_value, commit=lambda: None,
                                  rollback=lambda: None)

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None, distinct=False, limit=None, **k):
        f = filters or {}
        if dt == "Has Role":
            rows = [Obj(parent=u) for r, u in w.has_role if r == f.get("role")]
        elif dt == "EC Approval Level":
            rows = sorted([l for l in w.levels.values() if l.approval_process == f.get("approval_process")
                           and ("level_no" not in f or l.level_no == f["level_no"])],
                          key=lambda l: l.level_no)
        elif dt == "EC Approval Participant":
            lvl = w.levels.get(f.get("parent"))
            rows = [p for p in (lvl.participants if lvl else [])
                    if p.participant_purpose == f.get("participant_purpose")]
        else:
            rows = []
        if pluck:
            return [r.get(pluck) for r in rows]
        # Nhu Frappe that: chi tra cac cot duoc xin (quen xin "role" -> role = None).
        return [Obj({k: r.get(k) for k in fields}) if fields else Obj(r) for r in rows]
    fr.get_all = get_all
    fr.log_error = lambda title=None, message=None, **k: w.saves.append(("log", title, message))
    fr.get_traceback = lambda: "tb"
    return fr


def load(w, relpath):
    """Nap module that thanh ban RIENG, voi frappe gia + participants/user_rules that."""
    fr = make_frappe(w)
    pkg = "ecentric_workspace.approval_center.shared.workflow"
    mods = {"frappe": fr, "ecentric_workspace": types.ModuleType("ecentric_workspace"),
            "ecentric_workspace.approval_center": types.ModuleType("a"),
            "ecentric_workspace.approval_center.shared": types.ModuleType("b"),
            pkg: types.ModuleType("c")}
    old = {k: sys.modules.get(k) for k in list(mods) + [pkg + ".participants", pkg + ".user_rules"]}
    sys.modules.update(mods)
    try:
        for leaf in ("user_rules", "participants"):
            spec = importlib.util.spec_from_file_location(pkg + "." + leaf, ROOT / "shared/workflow" / (leaf + ".py"))
            m = importlib.util.module_from_spec(spec)
            sys.modules[pkg + "." + leaf] = m
            setattr(mods[pkg], leaf, m)
            spec.loader.exec_module(m)
        spec = importlib.util.spec_from_file_location("_rieng_" + relpath.replace("/", "_"), ROOT / relpath)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        # participants.validate_seed_entries import user_rules LUC CHAY, nen sys.modules phai
        # tro vao ban rieng suot test; fixture _tra_sys_modules tra lai sau moi test.
        return mod, sys.modules[pkg + ".participants"]
    except Exception:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
        raise


@pytest.fixture(autouse=True)
def _tra_sys_modules():
    keys = [k for k in sys.modules if k == "frappe" or k.startswith("ecentric_workspace")]
    snap = {k: sys.modules[k] for k in keys}
    yield
    for k in [k for k in sys.modules if k == "frappe" or k.startswith("ecentric_workspace")]:
        if k not in snap:
            del sys.modules[k]
    sys.modules.update(snap)



@pytest.fixture(autouse=True)
def _tra_sys_modules():
    keys = [k for k in sys.modules if k == "frappe" or k.startswith("ecentric_workspace")]
    snap = {k: sys.modules[k] for k in keys}
    yield
    for k in [k for k in sys.modules if k == "frappe" or k.startswith("ecentric_workspace")]:
        if k not in snap:
            del sys.modules[k]
    sys.modules.update(snap)


def _parts(w, key):
    return [(p.source_type, p.get("role") or p.get("user") or p.get("reference_field"), p.get("group_label"))
            for p in w.levels[key].participants if p.participant_purpose == "Approver"]


def test_offer_setup_bon_cap_dung_nguon():
    w = World()
    m, _P = load(w, "features/offer_request/infrastructure/setup.py")
    rep = m.setup_offer_request_v1(apply=1)
    assert not rep["errors"], rep
    lv = {l.level_no: l for l in w.levels.values()}
    assert [lv[i].level_name for i in (1, 2, 3, 4)] == [
        "Line Manager Review", "HR & CnB Review", "HOF Review", "CEO Review"]
    assert all(lv[i].approval_mode == "Any One" for i in lv)
    assert _parts(w, "OFFER_REQUEST-V1-L1") == [("Reference User Field", "line_manager", None)]
    assert _parts(w, "OFFER_REQUEST-V1-L2") == [("Role", "EC CnB", None)]
    assert _parts(w, "OFFER_REQUEST-V1-L3") == [("Role", "EC HOF", None)]
    assert _parts(w, "OFFER_REQUEST-V1-L4") == [("Role", "EC CEO", None)]
    assert w.procs["OFFER_REQUEST-V1"].status == "Draft"
    v = m.validate_offer_request_v1()
    assert v["ok"], [c for c in v["checks"] if not c["ok"]]


def test_offer_setup_chan_role_rong():
    w = World(empty_roles=("EC HOF",))
    m, _P = load(w, "features/offer_request/infrastructure/setup.py")
    rep = m.setup_offer_request_v1(apply=1)
    assert any("EC HOF" in e for e in rep["errors"]) and not w.levels


def test_nsp_setup_mot_cap_each_group_bon_nhom():
    w = World()
    m, _P = load(w, "features/new_staff_preparation/infrastructure/setup.py")
    rep = m.setup_new_staff_preparation_v1(apply=1)
    assert not rep["errors"], rep
    assert list(w.levels) == ["NEW_STAFF_PREPARATION-V1-L1"]
    lvl = w.levels["NEW_STAFF_PREPARATION-V1-L1"]
    assert lvl.approval_mode == "Each Group" and lvl.level_name == "Chuẩn bị onboard"
    assert _parts(w, "NEW_STAFF_PREPARATION-V1-L1") == [
        ("User", TUAN, "Lead HR"), ("Role", "EC HOF", "HOF"), ("Role", "EC CnB Payroll", "CnB"),
        ("Role", "EC Ops System", "Operation")]
    v = m.validate_new_staff_preparation_v1()
    assert v["ok"], [c for c in v["checks"] if not c["ok"]]


def test_nsp_moi_nhom_dung_mot_muc():
    w = World()
    m, _P = load(w, "features/new_staff_preparation/infrastructure/setup.py")
    rep = m.setup_new_staff_preparation_v1(operation=[TUAN, HUONG], apply=1)
    assert any("Operation" in e and "MOT" in e for e in rep["errors"]) and not w.levels


def test_nsp_validate_do_khi_mot_nhom_khong_con_ai():
    w = World()
    m, _P = load(w, "features/new_staff_preparation/infrastructure/setup.py")
    m.setup_new_staff_preparation_v1(apply=1)
    w.has_role = [x for x in w.has_role if x[0] != "EC Ops System"]
    v = m.validate_new_staff_preparation_v1()
    assert not v["ok"] and any("Operation" in c["check"] and not c["ok"] for c in v["checks"])


def test_hiring_setup_co_fulfiller_ec_recruiter():
    w = World()
    m, _P = load(w, "features/hiring_request/infrastructure/setup.py")
    m.setup_hiring_request_v1(apply=1)
    ff = [p for p in w.procs["HIRING_REQUEST-V1"].participants if p.get("participant_purpose") == "Fulfiller"]
    assert [(p.get("source_type"), p.get("role")) for p in ff] == [("Role", "EC Recruiter")]
    assert m.validate_hiring_request_v1()["ok"]
    w.procs["HIRING_REQUEST-V1"]["participants"] = []
    v = m.validate_hiring_request_v1()
    assert not v["ok"] and any("EC Recruiter" in c["check"] for c in v["checks"] if not c["ok"])
