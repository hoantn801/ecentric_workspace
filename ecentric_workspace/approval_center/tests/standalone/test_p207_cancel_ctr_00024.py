"""p207: huy EC-CTR-2026-00024 (Approved nhung cap Finance bi duyet nham vai tro).

Chay doc lap: frappe va transitions la gia, patch nap vao module RIENG nen khong phu thuoc
thu tu chay voi test khac.
    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_p207_cancel_ctr_00024.py
"""
import copy
import importlib.util
import pathlib
import sys
import types

import pytest

PATCH = pathlib.Path(__file__).resolve().parents[2] / "patches" / "p207_cancel_ctr_00024.py"
APR, CTR = "EC-APR-2026-00376", "EC-CTR-2026-00024"


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return dict.get(self, k)


def build(status="Approved", ref=CTR, atype="CONTRACT_REVIEW", ky_so=False, fulfil=False,
          phu_luc=False, boom=False, missing=False):
    t = {"EC Approval Request": {} if missing else {APR: Obj(
            name=APR, approval_status=status, approval_type=atype, current_level=0,
            reference_doctype="EC Contract Review Request", reference_name=ref,
            requested_by="trong.vo@ecentric.vn", completed_at="2026-09-24 16:55")},
         "EC Approval Request Approver": {"r%d" % i: Obj(name="r%d" % i, approval_request=APR,
                                                         status=s) for i, s in
                                          enumerate(["Approved", "Approved", "Skipped", "Approved", "Skipped"])},
         "EC Contract Review Request": {CTR: Obj(name=CTR)}}
    if phu_luc:
        t["EC Contract Review Request"]["EC-CTR-2026-00030"] = Obj(name="EC-CTR-2026-00030", previous_request=CTR)
    st = {"db": copy.deepcopy(t), "saved": copy.deepcopy(t)}
    calls = []

    def get_value(dt, name, field, for_update=False):
        if for_update:
            calls.append(("lock", name))
        r = st["db"][dt].get(name)
        return r and r.get(field)

    def set_value(dt, name, vals, v=None):
        st["db"][dt][name].update(vals if isinstance(vals, dict) else {vals: v})

    def commit():
        st["saved"] = copy.deepcopy(st["db"])

    def rollback():
        st["db"] = copy.deepcopy(st["saved"])

    fr = types.ModuleType("frappe")
    fr.db = types.SimpleNamespace(get_value=get_value, set_value=set_value, commit=commit, rollback=rollback)
    fr.get_doc = lambda dt, name: Obj(copy.deepcopy(st["db"][dt][name]))
    fr.get_all = lambda dt, filters=None, pluck=None: [
        r[pluck] for r in st["db"][dt].values() if all(r.get(k) == v for k, v in filters.items())]
    fr.log_error = lambda msg, title=None: calls.append(("log_error", title, msg))
    fr.get_traceback = lambda: "tb"
    fr.utils = types.ModuleType("frappe.utils")
    fr.utils.now_datetime = lambda: "NOW"

    tr = types.ModuleType("transitions")
    tr._FULFILLMENT_HANDLERS = {"EC Contract Review Request": "x"} if fulfil else {}
    tr._luong_co_ky_so = lambda req, ctx: ky_so

    def log_action(n, action, actor, level_no=None, **k):
        if boom:
            raise RuntimeError("boom")
        calls.append(("log", n, action, actor, k.get("comment"), k.get("previous_status"), k.get("new_status")))
    tr.log_action = log_action
    tr.close_todos = lambda dt, name, keep_user=None: calls.append(("close_todos", dt, name))
    tr.notify = lambda users, subj, dt, name: calls.append(("notify", tuple(users), name))
    tr._sla = lambda: types.SimpleNamespace(
        on_request_cancelled=lambda **k: calls.append(("sla_cancel", k["request_doctype"], k["request_name"])))

    mods = {"frappe": fr, "frappe.utils": fr.utils,
            "ecentric_workspace": types.ModuleType("a"),
            "ecentric_workspace.approval_center": types.ModuleType("b"),
            "ecentric_workspace.approval_center.shared": types.ModuleType("c"),
            "ecentric_workspace.approval_center.shared.workflow": types.ModuleType("d"),
            "ecentric_workspace.approval_center.shared.workflow.transitions": tr}
    mods["ecentric_workspace.approval_center.shared.workflow"].transitions = tr
    old = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        spec = importlib.util.spec_from_file_location("_p207_huy_rieng", PATCH)
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        for k, v in old.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return m, st, calls


def test_huy_dung_cac_buoc_cua_cancel():
    m, st, calls = build()
    rows_before = copy.deepcopy(st["db"]["EC Approval Request Approver"])
    m.execute()
    req = st["db"]["EC Approval Request"][APR]
    assert (req.approval_status, req.completed_at) == ("Cancelled", "NOW")
    assert st["db"]["EC Approval Request Approver"] == rows_before, "khong duoc dung vao dong nguoi duyet"
    kinds = [c[0] for c in calls]
    assert kinds[0] == "lock"
    for k in ("log", "close_todos", "notify", "sla_cancel"):
        assert k in kinds, k
    log = next(c for c in calls if c[0] == "log")
    assert log[1:4] == (APR, "Cancelled", "hoan.tran@ecentric.vn")
    assert "EC Finance" in log[4] and log[5:] == ("Approved", "Cancelled")
    assert ("close_todos", "EC Contract Review Request", CTR) in calls
    assert ("notify", ("trong.vo@ecentric.vn",), CTR) in calls
    assert ("sla_cancel", "EC Contract Review Request", CTR) in calls
    assert st["saved"]["EC Approval Request"][APR].approval_status == "Cancelled", "phai commit"
    assert any(c[0] == "log_error" and "DA HUY" in c[2] for c in calls)


def test_chay_lai_khong_lam_gi_them():
    m, st, calls = build()
    m.execute()
    snap, n = copy.deepcopy(st["db"]), len(calls)
    m.execute()
    assert st["db"] == snap
    assert not [c for c in calls[n:] if c[0] in ("log", "close_todos", "notify", "sla_cancel")]


@pytest.mark.parametrize("kw", [dict(status="Pending"), dict(status="Rejected"), dict(ref="EC-CTR-2026-00099"),
                                dict(atype="PAYMENT"), dict(ky_so=True), dict(fulfil=True),
                                dict(phu_luc=True), dict(missing=True)])
def test_dieu_kien_sai_thi_khong_dung_vao(kw):
    m, st, calls = build(**kw)
    before = copy.deepcopy(st["db"])
    m.execute()
    assert st["db"] == before
    assert not [c for c in calls if c[0] in ("log", "close_todos", "notify", "sla_cancel")]


def test_loi_giua_chung_thi_rollback_va_khong_nem():
    m, st, calls = build(boom=True)
    m.execute()                                                   # khong duoc nem
    assert st["db"]["EC Approval Request"][APR].approval_status == "Approved"
    assert st["db"]["EC Approval Request"][APR].completed_at == "2026-09-24 16:55"
    assert any(c[0] == "log_error" and "FAILED" in (c[1] or "") for c in calls)
