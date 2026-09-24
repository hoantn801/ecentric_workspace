"""Cap CnB/HR cua 7 luong HR resolve theo role `EC CnB` thay vi gan cung tuan.ly (25/09/2026).

Phu: helper dung chung (participants.py), 7 setup + validate, va patch p208 doi cau hinh live.
Chay doc lap (frappe gia, moi module nap thanh ban RIENG - khong phu thuoc thu tu test):
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_cnb_role_approver.py
"""
import copy
import importlib.util
import pathlib
import sys
import types

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
TUAN, HUONG = "tuan.ly@ecentric.vn", "huong.pham@ecentric.vn"
SETUPS = {  # feature: (ham setup, tham so cap CnB, cap, ham validate)
    "promotion": ("setup_promotion_v1", "cnb", 2, "validate_promotion_v1"),
    "special_bonus": ("setup_special_bonus_v1", "cnb", 2, "validate_special_bonus_v1"),
    "hiring_request": ("setup_hiring_request_v1", "hr", 2, "validate_hiring_request_v1"),
    "lateral_move": ("setup_lateral_move_v1", "hr", 3, "validate_lateral_move_v1"),
    "hr_activity": ("setup_hr_activity_v1", "hr_manager", 1, "validate_hr_activity_v1"),
    "employee_info_update": ("setup_employee_info_update_v1", "review_approvers", 1,
                             "validate_employee_info_update_v1"),
    "employee_referral": ("setup_employee_referral_v1", "careers", 1, "validate_employee_referral_v1"),
}


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return dict.get(self, k)

    def __setattr__(self, k, v):
        self[k] = v


class World:
    def __init__(self, cnb=(TUAN, HUONG), disabled=()):
        self.users = {u: Obj(enabled=0 if u in disabled else 1, user_type="System User")
                      for u in (TUAN, HUONG, "phuong.nguyen1@ecentric.vn", "lam.nguyen@ecentric.vn",
                                "web@x.com", "Administrator")}
        self.users["web@x.com"].user_type = "Website User"
        self.roles = {"EC CnB", "EC Finance"}
        self.has_role = [("EC CnB", u) for u in cnb]
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


# ------------------------------------------------------------------ helper dung chung
def test_participant_rows_email_va_role():
    _m, P = load(World(), "shared/workflow/participants.py")
    assert P.participant_rows([TUAN, "role:EC CnB", " Role: EC Finance "]) == [
        {"source_type": "User", "user": TUAN},
        {"source_type": "Role", "role": "EC CnB"},
        {"source_type": "Role", "role": "EC Finance"}]
    assert P.role_ref(P.CNB_ROLE) == "role:EC CnB"


def test_active_role_users_loc_nhu_luc_chay():
    w = World(cnb=(TUAN, HUONG, "web@x.com", "Administrator", "khong.ton.tai@x"), disabled=(HUONG,))
    _m, P = load(w, "shared/workflow/participants.py")
    assert P.active_role_users("EC CnB") == [TUAN]


@pytest.mark.parametrize("entries,loi", [
    (["role:EC CnB"], []),
    ([TUAN], []),
    (["role:Khong Co"], ["does not exist"]),
    ([], ["No X users"]),
])
def test_validate_seed_entries(entries, loi):
    _m, P = load(World(), "shared/workflow/participants.py")
    rep = {"errors": []}
    P.validate_seed_entries("X", entries, rep)
    assert len(rep["errors"]) == len(loi) and all(a in b for a, b in zip(loi, rep["errors"]))


def test_validate_seed_entries_role_rong_la_loi():
    _m, P = load(World(cnb=()), "shared/workflow/participants.py")
    rep = {"errors": []}
    P.validate_seed_entries("CnB", ["role:EC CnB"], rep)
    assert rep["errors"] and "no active System User" in rep["errors"][0]


def test_check_approver_parts():
    _m, P = load(World(), "shared/workflow/participants.py")
    ok = lambda parts: all(o for o, _m2 in P.check_approver_parts([Obj(p) for p in parts], 2))
    assert ok([{"source_type": "Role", "role": "EC CnB"}])
    assert ok([{"source_type": "User", "user": TUAN}])
    assert not ok([])
    assert not ok([{"source_type": "User", "user": TUAN}, {"source_type": "User", "user": TUAN}])
    assert not ok([{"source_type": "Role", "role": "EC Finance"}])          # role khong ai giu
    w = World(disabled=(TUAN,))
    _m, P = load(w, "shared/workflow/participants.py")
    assert not all(o for o, _x in P.check_approver_parts([Obj(source_type="User", user=TUAN)], 1))


# ------------------------------------------------------------------ 7 setup + validate
@pytest.mark.parametrize("feat", sorted(SETUPS))
def test_setup_mac_dinh_la_role_cnb_va_validate_xanh(feat):
    fn, arg, cap, vfn = SETUPS[feat]
    w = World()
    m, _P = load(w, "features/%s/infrastructure/setup.py" % feat)
    rep = getattr(m, fn)(apply=1)
    assert not rep["errors"], rep
    lv = {l.level_no: l for l in w.levels.values()}
    duyet = [p for p in lv[cap].participants if p.participant_purpose == "Approver"]
    assert [(p.source_type, p.get("role"), p.get("user")) for p in duyet] == [("Role", "EC CnB", None)]
    for no, l in lv.items():
        for p in l.participants:
            assert p.get("user") != TUAN, (feat, no)
    v = getattr(m, vfn)()
    assert v["ok"], [c for c in v["checks"] if not c["ok"]]


@pytest.mark.parametrize("feat", sorted(SETUPS))
def test_setup_van_ep_duoc_nguoi_cu_the(feat):
    fn, arg, cap, vfn = SETUPS[feat]
    w = World()
    m, _P = load(w, "features/%s/infrastructure/setup.py" % feat)
    rep = getattr(m, fn)(apply=1, **{arg: [HUONG]})
    assert not rep["errors"], rep
    lv = {l.level_no: l for l in w.levels.values()}
    assert [(p.source_type, p.get("user")) for p in lv[cap].participants
            if p.participant_purpose == "Approver"] == [("User", HUONG)]
    assert getattr(m, vfn)()["ok"]


@pytest.mark.parametrize("feat", sorted(SETUPS))
def test_setup_chan_khi_role_cnb_khong_ai_giu(feat):
    fn, arg, cap, vfn = SETUPS[feat]
    w = World(cnb=())
    m, _P = load(w, "features/%s/infrastructure/setup.py" % feat)
    rep = getattr(m, fn)(apply=1)
    assert any("EC CnB" in e for e in rep["errors"]), rep
    assert not w.levels, "khong duoc ghi gi khi dang loi"


@pytest.mark.parametrize("feat", sorted(SETUPS))
def test_validate_do_khi_role_rong_sau_khi_da_dung(feat):
    fn, arg, cap, vfn = SETUPS[feat]
    w = World()
    m, _P = load(w, "features/%s/infrastructure/setup.py" % feat)
    getattr(m, fn)(apply=1)
    w.has_role = []
    assert not getattr(m, vfn)()["ok"]


# ------------------------------------------------------------------ p208
def _live(w, p208, drift=None, extra_cc=False):
    for proc, no, ten in p208.CAP:
        rows = [Obj(participant_purpose="Approver", source_type="User", user=TUAN, sort_order=0)]
        if drift == proc:
            rows.append(Obj(participant_purpose="Approver", source_type="User", user=HUONG, sort_order=1))
        if extra_cc:
            rows.append(Obj(participant_purpose="CC", source_type="User", user="lam.nguyen@ecentric.vn"))
        w.levels["%s-L%d" % (proc, no)] = make_level(w, proc, no, ten, rows)
    w.levels["PROMOTION_REQUEST-V1-L3"] = make_level(w, "PROMOTION_REQUEST-V1", 3, "HOF Review", [
        Obj(participant_purpose="Approver", source_type="User", user="phuong.nguyen1@ecentric.vn")])


def make_level(w, proc, no, ten, rows):
    fr = sys.modules["frappe"]
    d = fr.new_doc("EC Approval Level")
    d.update(name="%s-L%d" % (proc, no), approval_process=proc, level_no=no, level_name=ten,
             approval_mode="Any One", participants=rows)
    return d


def _approvers(w, key):
    return [(p.source_type, p.get("user") or p.get("role")) for p in w.levels[key].participants
            if p.participant_purpose == "Approver"]


def test_p208_doi_du_7_cap_va_giu_dong_khong_phai_approver():
    w = World()
    m, _P = load(w, "patches/p208_cnb_levels_to_role.py")
    _live(w, m, extra_cc=True)
    m.execute()
    assert len(m.CAP) == 7
    for proc, no, _t in m.CAP:
        k = "%s-L%d" % (proc, no)
        assert _approvers(w, k) == [("Role", "EC CnB")], k
        assert [p.user for p in w.levels[k].participants if p.participant_purpose == "CC"] == [
            "lam.nguyen@ecentric.vn"]
    assert _approvers(w, "PROMOTION_REQUEST-V1-L3") == [("User", "phuong.nguyen1@ecentric.vn")]
    log = [s for s in w.saves if isinstance(s, tuple)][-1]
    assert log[1] == "p208 cap CnB -> role" and HUONG in log[2] and log[2].count("DA DOI") == 7


def test_p208_chay_lai_khong_luu_gi_them():
    w = World()
    m, _P = load(w, "patches/p208_cnb_levels_to_role.py")
    _live(w, m)
    m.execute()
    n = len([s for s in w.saves if not isinstance(s, tuple)])
    m.execute()
    assert len([s for s in w.saves if not isinstance(s, tuple)]) == n
    assert [s for s in w.saves if isinstance(s, tuple)][-1][2].count("da la Role") == 7


def test_p208_role_rong_thi_khong_doi_cap_nao():
    w = World(cnb=())
    m, _P = load(w, "patches/p208_cnb_levels_to_role.py")
    _live(w, m)
    snap = copy.deepcopy(w.levels)
    m.execute()
    assert w.levels == snap
    assert "DUNG" in [s for s in w.saves if isinstance(s, tuple)][-1][2]


def test_p208_cau_hinh_da_bi_sua_tay_thi_bo_qua_rieng_cap_do():
    w = World()
    m, _P = load(w, "patches/p208_cnb_levels_to_role.py")
    _live(w, m, drift="HIRING_REQUEST-V1")
    m.execute()
    assert _approvers(w, "HIRING_REQUEST-V1-L2") == [("User", TUAN), ("User", HUONG)]
    assert _approvers(w, "PROMOTION_REQUEST-V1-L2") == [("Role", "EC CnB")]


def test_p208_sai_ten_cap_thi_bo_qua():
    w = World()
    m, _P = load(w, "patches/p208_cnb_levels_to_role.py")
    _live(w, m)
    w.levels["LATERAL_MOVE-V1-L3"].level_name = "CEO Review"
    m.execute()
    assert _approvers(w, "LATERAL_MOVE-V1-L3") == [("User", TUAN)]


def test_p208_mot_cap_loi_khong_chan_cap_khac_va_khong_nem():
    w = World()
    m, _P = load(w, "patches/p208_cnb_levels_to_role.py")
    _live(w, m)
    w.boom = "SPECIAL_BONUS-V1"
    m.execute()
    assert _approvers(w, "SPECIAL_BONUS-V1-L2") == [("User", TUAN)]
    assert _approvers(w, "EMPLOYEE_REFERRAL-V1-L1") == [("Role", "EC CnB")]
    assert any(isinstance(s, tuple) and "FAILED" in s[1] for s in w.saves)
