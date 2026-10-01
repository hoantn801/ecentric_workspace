"""Daily Target 01/10/2026: duyet xong -> team Data (Role EC Data Team) nhan + hoan tat.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_daily_target_data_xu_ly.py
"""
import importlib.util
import pathlib
import sys
import types

import pytest

APP = pathlib.Path(__file__).resolve().parents[2]


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)

    def __setattr__(self, k, v):
        self[k] = v


class Throw(Exception):
    pass


class Doc(Obj):
    def save(self, ignore_permissions=False):
        W.saved.append(dict(self))


class W:
    pass


def build(fulfiller=True, team=("linh@x", "hoan@x")):
    W.saved, W.calls, W.todos = [], [], {}
    W.row = Doc(name="DT-1", approval_request="APR", requested_by="req@x", company="EC",
                fulfillment_status=None, fulfillment_owner=None, fulfillment_summary=None)
    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.session = types.SimpleNamespace(user="linh@x")
    fr.throw = lambda m, *a: (_ for _ in ()).throw(Throw(m))
    fr.get_roles = lambda u=None: ["System Manager"] if u == "admin@x" else []
    parts = [Obj(participant_purpose="Fulfiller", source_type="Role", role="EC Data Team")] if fulfiller else []
    proc = Obj(name="P", participants=parts, fulfillment_sla_policy=None)

    def get_doc(dt, name=None):
        return proc if dt == "EC Approval Process" else W.row
    fr.get_doc = get_doc

    def get_value(dt, name, fields=None, as_dict=False, **k):
        if dt == "EC Approval Request":
            return "P"
        if dt == "Employee":
            return None
        if isinstance(fields, list):
            return Obj({f: W.row.get(f) for f in fields})
        return W.row.get(fields)

    def set_value(dt, name, vals, *a, **k):
        W.row.update(vals)

    def sql(q, args):
        if q.strip().startswith("update"):
            user, name = args
            if W.row.fulfillment_status == "Assigned":
                W.row.update(fulfillment_owner=user, fulfillment_status="In Progress")
            return None
        return [[1]] if W.row.fulfillment_owner == args[1] else []
    fr.db = types.SimpleNamespace(get_value=get_value, set_value=set_value, sql=sql,
                                  exists=lambda dt, f: bool(W.todos.get(f.get("allocated_to"))))
    fr.parse_json = lambda s: __import__("json").loads(s)
    fr.log_error = lambda **k: W.calls.append(("log", k.get("title")))
    fr.whitelist = lambda *a, **k: (a[0] if a and callable(a[0]) else (lambda f: f))
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: "NOW"
    fr.utils = utils
    eng = types.ModuleType("eng")
    eng.resolve_participants = lambda ps, req, context=None: [(u, "Role") for u in team] if ps else []
    eng.resolve_sla = lambda *a, **k: None
    eng.assign = lambda dt, n, users, desc, **k: W.calls.append(("assign", tuple(users)))
    eng.notify = lambda users, msg, *a: W.calls.append(("notify", tuple(users)))
    eng.is_active_process_fulfiller = lambda t, u: u in team
    eng.ensure_sole_todo = lambda *a, **k: W.calls.append(("todo", a[2]))
    eng.log_action = lambda *a, **k: W.calls.append(("action", a[1]))
    eng.close_fulfillment_todos = lambda *a: W.calls.append(("close",))
    eng.request_label = lambda dt, n: n
    eng.submit = lambda *a, **k: "APR"
    eng.resubmit = lambda *a, **k: None
    wf = types.ModuleType("wf"); wf.transitions = eng
    cs = types.ModuleType("cs"); cs.attach_extra_files = lambda doc, files: None
    sys.modules.update({"frappe": fr, "frappe.utils": utils,
                        "ecentric_workspace.approval_center.shared.workflow": wf,
                        "ecentric_workspace.approval_center.shared.workflow.transitions": eng,
                        "ecentric_workspace.approval_center.shared.requests.command_service": cs})
    for n in ("ecentric_workspace", "ecentric_workspace.approval_center", "ecentric_workspace.approval_center.shared",
              "ecentric_workspace.approval_center.shared.requests"):
        sys.modules.setdefault(n, types.ModuleType(n))
    spec = importlib.util.spec_from_file_location("dt_svc_rieng", APP / "features/daily_target/application/service.py")
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return fr, m


@pytest.fixture
def env():
    saved = dict(sys.modules)
    yield build
    for k in list(sys.modules):
        if k not in saved:
            del sys.modules[k]
    sys.modules.update(saved)


def test_duyet_xong_vao_hang_doi_team_data(env):
    fr, s = env()
    s.on_final_approval("DT-1")
    assert W.row.fulfillment_status == "Assigned"
    assert ("assign", ("linh@x", "hoan@x")) in W.calls


def test_process_khong_cau_hinh_thi_khong_vao_hang_doi(env):
    fr, s = env(fulfiller=False)
    s.on_final_approval("DT-1")
    assert W.row.fulfillment_status is None and not W.calls


def test_nguoi_ngoai_team_khong_nhan_duoc(env):
    fr, s = env()
    W.row.fulfillment_status = "Assigned"
    with pytest.raises(Throw):
        s.claim_fulfillment("DT-1", user="khac@x")


def test_nhan_roi_nguoi_khac_khong_cuop(env):
    fr, s = env()
    W.row.fulfillment_status = "Assigned"
    assert s.claim_fulfillment("DT-1", user="linh@x")["claimed"]
    assert W.row.fulfillment_owner == "linh@x" and ("todo", "linh@x") in W.calls
    with pytest.raises(Throw):
        s.claim_fulfillment("DT-1", user="hoan@x")


def test_hoan_tat_bat_buoc_ghi_chu_va_chi_nguoi_nhan(env):
    fr, s = env()
    W.row.update(fulfillment_status="In Progress", fulfillment_owner="linh@x")
    with pytest.raises(Throw):
        s.complete_fulfillment("DT-1", user="linh@x", payload="{}")
    with pytest.raises(Throw):
        s.complete_fulfillment("DT-1", user="hoan@x", payload='{"fulfillment_summary": "x"}')
    assert s.complete_fulfillment("DT-1", user="linh@x", payload='{"fulfillment_summary": "Da cap nhat"}')["completed"]
    assert W.row.fulfillment_status == "Completed" and W.row.completed_by == "linh@x" and ("close",) in W.calls
