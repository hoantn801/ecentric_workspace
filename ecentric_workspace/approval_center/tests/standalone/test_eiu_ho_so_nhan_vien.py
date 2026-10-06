"""Employee Info Update 29/09/2026: truong lay tu ho so nhan vien, duyet xong tu ghi vao Employee.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_eiu_ho_so_nhan_vien.py
"""
import importlib.util
import pathlib
import sys
import types

import pytest

APP = pathlib.Path(__file__).resolve().parents[2]
FEAT = APP / "features" / "employee_info_update" / "application"
PKG = "ecentric_workspace.approval_center.features.employee_info_update.application"


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


class DF(Obj):
    pass


EMP_FIELDS = {
    "personal_email": DF(fieldtype="Data"), "cell_number": DF(fieldtype="Data"),
    "date_of_birth": DF(fieldtype="Date"), "marital_status": DF(fieldtype="Select", options="\nSingle\nMarried"),
    "passport_number": DF(fieldtype="Data"), "date_of_issue": DF(fieldtype="Date"),
    "place_of_issue": DF(fieldtype="Data"), "permanent_address": DF(fieldtype="Small Text"),
    "current_address": DF(fieldtype="Small Text"), "bank_name": DF(fieldtype="Data"),
    "bank_ac_no": DF(fieldtype="Data"), "health_insurance_no": DF(fieldtype="Data"),
    "ec_ma_kcb": DF(fieldtype="Data"), "ec_noi_kcb": DF(fieldtype="Data"),
    "ec_bien_so_xe": DF(fieldtype="Data"), "designation": DF(fieldtype="Link", options="Designation"),
    "grade": DF(fieldtype="Link", options="Employee Grade"),
}


class Throw(Exception):
    pass


class EmpDoc(Obj):
    def set(self, k, v):
        self[k] = v

    def save(self, ignore_permissions=False):
        W.saved.append(dict(self))
        W.db[("Employee", self["name"])] = dict(self)


class Req(Obj):
    pass


class World:
    pass


W = World()


def build(roles=None, boom=False, cnb_user="cnb@x"):
    W.roles = roles or {"a@x": [], cnb_user: ["EC CnB"]}
    W.db = {("Employee", "EMP-A"): {"name": "EMP-A", "user_id": "a@x", "bank_ac_no": "111",
                                     "date_of_birth": "1990-01-01", "company_email": "a@x"},
            ("Employee", "EMP-B"): {"name": "EMP-B", "user_id": "b@x", "bank_ac_no": "222"}}
    W.req = {}
    W.saved, W.logs, W.errors, W.notes, W.enq = [], [], [], [], []
    W.session = "a@x"
    W.boom = boom
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.session = types.SimpleNamespace(user="a@x")

    def throw(msg, *a, **k):
        raise Throw(msg)
    fr.throw = throw
    fr.get_roles = lambda u=None: W.roles.get(u or fr.session.user, [])
    meta = types.SimpleNamespace(get_field=lambda fn: EMP_FIELDS.get(fn))
    fr.get_meta = lambda dt: meta

    def get_value(dt, filt, fields=None, **k):
        if dt == "Employee":
            if isinstance(filt, dict):
                (f, v), = filt.items()
                for (d, n), row in W.db.items():
                    if d == "Employee" and row.get(f) == v:
                        return n if fields == "name" else row.get(fields)
                return None
            row = W.db.get(("Employee", filt))
            return row and row.get(fields)
        if dt == "EC Employee Information Update Request":
            return W.req.get(filt, {}).get(fields)
        return None

    def set_value(dt, name, vals, *a, **k):
        if isinstance(vals, str):
            vals = {vals: a[0]}
        W.req.setdefault(name, {}).update(vals)
    fr.db = types.SimpleNamespace(get_value=get_value, set_value=set_value,
                                  exists=lambda dt, n: n in ("Dev", "TTS"),
                                  commit=lambda: None, rollback=lambda: W.notes.append("rollback"))

    def get_doc(dt, name):
        if dt == "Employee":
            if W.boom:
                raise RuntimeError("boom")
            return EmpDoc(W.db[("Employee", name)], flags=types.SimpleNamespace())
        return Req(W.req[name])
    fr.get_doc = get_doc
    fr.get_all = lambda *a, **k: ["cnb@x"]
    fr.log_error = lambda title=None, message=None: W.errors.append(title)
    fr.get_traceback = lambda: "TB"
    fr.enqueue = lambda path, **k: W.enq.append((path, k))
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    utils = types.ModuleType("frappe.utils")

    def getdate(v):
        import datetime
        return datetime.date.fromisoformat(v)
    utils.getdate = getdate
    utils.now_datetime = lambda: "2026-09-29 10:00:00"
    fr.utils = utils
    eng = types.ModuleType("eng")
    eng.log_action = lambda *a, **k: W.logs.append((a, k))
    eng.notify = lambda users, msg, *a: W.notes.append((tuple(users), msg))
    eng.submit = lambda *a: "APR-1"
    wf = types.ModuleType("wf")
    wf.transitions = eng
    mods = {"frappe": fr, "frappe.utils": utils,
            "ecentric_workspace": types.ModuleType("e"),
            "ecentric_workspace.approval_center": types.ModuleType("e1"),
            "ecentric_workspace.approval_center.shared": types.ModuleType("e2"),
            "ecentric_workspace.approval_center.shared.workflow": wf,
            "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
            "ecentric_workspace.approval_center.features": types.ModuleType("e3"),
            "ecentric_workspace.approval_center.features.employee_info_update": types.ModuleType("e4"),
            PKG: types.ModuleType("e5")}
    sys.modules.update(mods)
    out = {}
    for n in ("profile_fields", "service"):
        spec = importlib.util.spec_from_file_location(PKG + "." + n, FEAT / (n + ".py"))
        m = importlib.util.module_from_spec(spec)
        sys.modules[PKG + "." + n] = m
        setattr(mods[PKG], n, m)
        spec.loader.exec_module(m)
        out[n] = m
    return fr, out["profile_fields"], out["service"]


@pytest.fixture
def env():
    saved = dict(sys.modules)
    yield build
    for k in list(sys.modules):
        if k not in saved:
            del sys.modules[k]
    sys.modules.update(saved)


def test_danh_sach_tu_ho_so_khong_co_tro_cap_va_cnb_moi_thay_chuc_danh(env):
    fr, pf, _s = env()
    o = pf.options("a@x")["fields_to_update"]
    assert "License plate" in o and "Bank account" in o and o[-1] == "Other"
    assert not any("allow" in x.lower() or "salary" in x.lower() for x in o)
    assert "Position (C&B use only)" not in o and "Job title (C&B use only)" not in o
    assert "Position (C&B use only)" in pf.options("cnb@x")["fields_to_update"]
    assert pf.options("a@x")["field_types"]["Date of birth"]["type"] == "Date"


def test_truong_khong_con_tren_employee_thi_an(env):
    fr, pf, _s = env()
    EMP_FIELDS.pop("ec_bien_so_xe")
    try:
        assert "License plate" not in pf.options("a@x")["fields_to_update"]
    finally:
        EMP_FIELDS["ec_bien_so_xe"] = DF(fieldtype="Data")


def test_gia_tri_hien_tai_chi_cho_chinh_minh_hoac_cnb(env):
    fr, pf, _s = env()
    assert pf.current_value("a@x", "a@x", "Bank account") == {"value": "111", "readable": True, "auto_apply": True}
    assert pf.current_value("a@x", "b@x", "Bank account")["value"] == ""       # nguoi khac
    assert pf.current_value("cnb@x", "b@x", "Bank account")["value"] == "222"  # C&B
    assert pf.current_value("a@x", "a@x", "Other")["auto_apply"] is False


def _doc(**kw):
    d = Req(name="EIU-1", employee_email="a@x", field_to_update="Bank account", new_value="999",
            requested_by="a@x", approval_request=None)
    d.update(kw)
    return d


def test_nhan_vien_chi_sua_ho_so_cua_minh(env):
    fr, pf, s = env()
    s._validate_business(_doc(), "a@x")
    with pytest.raises(Throw, match="chính mình"):
        s._validate_business(_doc(employee_email="b@x"), "a@x")
    s._validate_business(_doc(employee_email="b@x"), "cnb@x")                 # C&B duoc


def test_kieu_du_lieu_duoc_kiem(env):
    fr, pf, s = env()
    with pytest.raises(Throw, match="ngày"):
        s._validate_business(_doc(field_to_update="Date of birth", new_value="abc"), "a@x")
    with pytest.raises(Throw, match="một trong"):
        s._validate_business(_doc(field_to_update="Marital status", new_value="X"), "a@x")
    with pytest.raises(Throw, match="hợp lệ"):
        s._validate_business(_doc(field_to_update="Position (C&B use only)", new_value="TTS"), "a@x")
    with pytest.raises(Throw, match="danh mục"):
        s._validate_business(_doc(field_to_update="Position (C&B use only)", new_value="Khong co"), "cnb@x")
    d = _doc(field_to_update="Date of birth", new_value="1991-02-03")
    s._validate_business(d, "a@x")
    assert d.new_value == "1991-02-03" and d.target_employee == "EMP-A"


def test_duyet_xong_ghi_nen_sau_commit(env):
    fr, pf, s = env()
    s.on_final_approval("EIU-1")
    path, k = W.enq[0]
    assert path.endswith("employee_info_update.application.service.apply_to_employee")
    assert k["enqueue_after_commit"] is True and k["name"] == "EIU-1"


def test_ghi_vao_ho_so_va_idempotent(env):
    fr, pf, s = env()
    W.req["EIU-1"] = dict(_doc(target_employee="EMP-A", current_value="111", approval_request="APR-1"))
    assert s.apply_to_employee("EIU-1") == {"applied": True}
    assert W.db[("Employee", "EMP-A")]["bank_ac_no"] == "999"
    assert W.req["EIU-1"]["applied_at"] and "Đã ghi" in W.req["EIU-1"]["apply_result"]
    assert W.logs                                                             # nhat ky duyet
    assert s.apply_to_employee("EIU-1") == {"skipped": "applied"}
    assert len(W.saved) == 1


def test_other_khong_ghi_tu_dong(env):
    fr, pf, s = env()
    W.req["EIU-1"] = dict(_doc(field_to_update="Other", approval_request="APR-1"))
    assert s.apply_to_employee("EIU-1") == {"skipped": "manual"}
    assert not W.saved and "tay" in W.req["EIU-1"]["apply_result"]


def test_loi_ghi_thi_bao_khong_nem(env):
    fr, pf, s = env(boom=True)
    W.req["EIU-1"] = dict(_doc(target_employee="EMP-A", approval_request="APR-1"))
    assert s.apply_to_employee("EIU-1") == {"applied": False}
    assert "rollback" in W.notes and W.errors and "LỖI" in W.req["EIU-1"]["apply_result"]
    assert not W.req["EIU-1"].get("applied_at")
    assert any("a@x" in n[0] for n in W.notes if isinstance(n, tuple))
