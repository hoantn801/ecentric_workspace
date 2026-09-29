"""p229: dua EC-HIRE-2026-00005 (duyet truoc khi co buoc tuyen dung) vao hang doi EC Recruiter.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_p229_hire_00005.py
"""
import importlib.util
import pathlib
import sys
import types

import pytest

PATCH = pathlib.Path(__file__).resolve().parents[2] / "patches" / "p229_hire_00005_vao_buoc_tuyen_dung.py"
HIRE, APR = "EC-HIRE-2026-00005", "EC-APR-X"


class Obj(dict):
    __getattr__ = dict.get


def run(fs="Not Started", status="Approved", missing=False, boom=False):
    rows = {} if missing else {HIRE: Obj(approval_request=APR, fulfillment_status=fs)}
    calls = []
    fr = types.ModuleType("frappe")

    def get_value(dt, name, fields, as_dict=False):
        if dt == "EC Approval Request":
            return status
        r = rows.get(name)
        if r is None:
            return None
        return r if as_dict else r.get(fields)
    fr.db = types.SimpleNamespace(get_value=get_value, commit=lambda: calls.append("commit"),
                                  rollback=lambda: calls.append("rollback"))
    fr.log_error = lambda title=None, message=None: calls.append(("log", message))
    fr.get_traceback = lambda: "TB"

    svc = types.ModuleType("svc")

    def ofa(name):
        if boom:
            raise RuntimeError("x")
        calls.append(("ofa", name))
        rows[name]["fulfillment_status"] = "Assigned"
    svc.on_final_approval = ofa
    pkg = "ecentric_workspace.approval_center.features.hiring_request.application"
    mods = {"frappe": fr, "ecentric_workspace": types.ModuleType("a"),
            "ecentric_workspace.approval_center": types.ModuleType("b"),
            "ecentric_workspace.approval_center.features": types.ModuleType("c"),
            "ecentric_workspace.approval_center.features.hiring_request": types.ModuleType("d"),
            pkg: types.ModuleType("e"), pkg + ".service": svc}
    mods[pkg].service = svc
    old = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        spec = importlib.util.spec_from_file_location("p229_rieng", PATCH)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        m.execute()
    finally:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return calls, rows


def log(calls):
    return [c[1] for c in calls if isinstance(c, tuple) and c[0] == "log"][0]


def test_dua_vao_buoc_tuyen_dung():
    calls, rows = run()
    assert ("ofa", HIRE) in calls and "commit" in calls
    assert "Assigned" in log(calls)


@pytest.mark.parametrize("fs", ["Assigned", "In Progress", "Completed"])
def test_da_vao_roi_khong_lam_lai(fs):
    calls, _ = run(fs=fs)
    assert not any(isinstance(c, tuple) and c[0] == "ofa" for c in calls)


@pytest.mark.parametrize("st", ["Cancelled", "Pending", "Rejected"])
def test_khong_con_approved_thi_bo_qua(st):
    calls, _ = run(status=st)
    assert not any(isinstance(c, tuple) and c[0] == "ofa" for c in calls)


def test_fs_rong_van_dua_vao():
    calls, _ = run(fs=None)
    assert ("ofa", HIRE) in calls


def test_khong_thay_phieu():
    calls, _ = run(missing=True)
    assert "khong thay" in log(calls)


def test_loi_thi_rollback_khong_nem():
    calls, _ = run(boom=True)
    assert "rollback" in calls and "LOI" in log(calls)
