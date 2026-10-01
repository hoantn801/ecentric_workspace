"""Nut "Nhac nguoi xu ly" (01/10/2026, Hoan): chi nguoi gui bam, chi nhac nguoi DANG xu ly,
15 phut / phieu, bao ERP + Teams qua engine.notify, ghi vet "Reminded".

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_remind_nguoi_xu_ly.py
"""
import datetime as dt
import importlib.util
import pathlib
import sys
import types

import pytest

APP = pathlib.Path(__file__).resolve().parents[3]
NOW = dt.datetime(2026, 10, 1, 10, 0, 0)


class Obj(dict):
    def __getattr__(self, k):
        if k.startswith("__"):
            raise AttributeError(k)
        return self.get(k)


class Throw(Exception):
    pass


class W:
    pass


def build(status="Pending", level=2, approvers=None, fulfillment=None, owner=None, todos=(),
          actions=(), requested_by="req@x", user="req@x"):
    W.notified, W.logged, W.locked = [], [], []
    W.req = Obj(name="APR-1", approval_status=status, current_level=level)
    W.doc = Obj(doctype="EC Leave", name="LV-1", approval_request="APR-1", requested_by=requested_by,
                fulfillment_status=fulfillment, fulfillment_owner=owner)
    # (level_no, approver, status)
    W.approvers = list(approvers if approvers is not None else [
        (1, "lead@x", "Approved"), (2, "hr1@x", "Pending"), (2, "hr2@x", "Pending"),
        (2, "hr3@x", "Skipped"), (3, "ceo@x", "Pending")])
    W.actions = list(actions)

    fr = types.ModuleType("frappe")
    fr._ = lambda s: s
    fr.PermissionError = type("PermissionError", (Exception,), {})
    fr.session = types.SimpleNamespace(user=user)

    def throw(m, exc=None):
        raise (exc or Throw)(m)
    fr.throw = throw

    def get_all(dt_, filters=None, pluck=None, **k):
        f = filters or {}
        if dt_ == "EC Approval Request Approver":
            return [a for (lv, a, st) in W.approvers
                    if lv == f["level_no"] and st == f["status"]]
        if dt_ == "ToDo":
            return list(todos)
        if dt_ == "EC Approval Action":
            return sorted([t for (act, t) in W.actions if act == f["action"]], reverse=True)[:1]
        raise AssertionError(dt_)
    fr.get_all = get_all
    fr.get_doc = lambda dt_, name=None: W.req if dt_ == "EC Approval Request" else W.doc

    def get_value(dt_, name, field=None, for_update=False, **k):
        if for_update:
            W.locked.append(name)
        return {"User": "Nguoi Gui"}.get(dt_, name)
    fr.db = types.SimpleNamespace(get_value=get_value)

    utils = types.ModuleType("frappe.utils")
    utils.get_datetime = lambda v: v
    utils.now_datetime = lambda: NOW
    fr.utils = utils

    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.notify = lambda users, subject, doctype, name: W.notified.append((list(users), subject))
    eng.request_label = lambda d, n: "Nghi phep LV-1"
    eng.log_action = lambda req, action, actor, level=None, comment=None: W.logged.append(
        (req, action, actor, level, comment))
    pkgs = {"ecentric_workspace": None, "ecentric_workspace.approval_center": None,
            "ecentric_workspace.approval_center.shared": None,
            "ecentric_workspace.approval_center.shared.workflow": None}
    for p in pkgs:
        sys.modules[p] = types.ModuleType(p)
    sys.modules["ecentric_workspace.approval_center.shared.workflow"].transitions = eng
    sys.modules["ecentric_workspace.approval_center.shared.workflow.transitions"] = eng
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = utils
    spec = importlib.util.spec_from_file_location(
        "remind_mod", APP / "approval_center/shared/requests/remind.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, fr


DEF = types.SimpleNamespace(business_doctype="EC Leave")


def test_chi_nhac_nguoi_dang_giu_cap_hien_tai():
    m, _ = build()
    out = m.remind(DEF, "LV-1")
    # cap 1 da duyet, cap 3 chua toi luot, hr3 da Skipped (Each Group) -> khong nhac
    assert out["reminded"] == ["hr1@x", "hr2@x"]
    assert W.notified == [(["hr1@x", "hr2@x"], "🔔 Nguoi Gui nhắc bạn xử lý: Nghi phep LV-1")]
    assert W.logged[0][:4] == ("APR-1", "Reminded", "req@x", 2)
    assert W.locked == ["APR-1"]


def test_chi_nguoi_gui_duoc_bam():
    m, fr = build(user="hr1@x")
    with pytest.raises(fr.PermissionError):
        m.remind(DEF, "LV-1")
    assert W.notified == [] and W.logged == []
    assert m.capability("hr1@x", W.doc, W.req) == (False, 0)


def test_15_phut_mot_lan():
    m, _ = build(actions=[("Reminded", NOW - dt.timedelta(minutes=5)),
                          ("Approved", NOW - dt.timedelta(minutes=1))])
    with pytest.raises(Throw, match="10 phút"):
        m.remind(DEF, "LV-1")
    assert W.notified == []
    assert m.capability("req@x", W.doc, W.req) == (True, 600)
    m, _ = build(actions=[("Reminded", NOW - dt.timedelta(minutes=15))])
    assert m.capability("req@x", W.doc, W.req) == (True, 0)
    assert m.remind(DEF, "LV-1")["reminded"] == ["hr1@x", "hr2@x"]


def test_buoc_xu_ly_nhac_nguoi_da_nhan_hoac_todo_mo():
    m, _ = build(status="Approved", level=None, fulfillment="In Progress", owner="data@x")
    assert m.remind(DEF, "LV-1")["reminded"] == ["data@x"]
    m, _ = build(status="Approved", level=None, fulfillment="Assigned", todos=["b@x", "a@x", "a@x"])
    assert m.remind(DEF, "LV-1")["reminded"] == ["a@x", "b@x"]


@pytest.mark.parametrize("kw", [
    dict(status="Information Required"),             # bong o san nguoi gui
    dict(status="Approved", level=None, fulfillment="Completed", owner="data@x"),
    dict(status="Approved", level=None, fulfillment=None),
    dict(status="Rejected"),
    dict(status="Cancelled"),
])
def test_khong_co_ai_de_nhac(kw):
    m, _ = build(**kw)
    assert m.capability("req@x", W.doc, W.req) == (False, 0)
    with pytest.raises(Throw):
        m.remind(DEF, "LV-1")
    assert W.notified == [] and W.logged == []


def test_chua_gui_phieu():
    m, _ = build()
    W.doc["approval_request"] = None
    with pytest.raises(Throw):
        m.remind(DEF, "LV-1")
    assert m.capability("req@x", W.doc, None) == (False, 0)
