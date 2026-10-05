"""Nhan xu ly -> nguoi nhan duoc cap quyen DOC phieu (de mo duoc tep dinh kem) (05/10/2026).

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_claim_cap_quyen_doc.py
"""
import importlib.util
import pathlib
import sys
import types

APP = pathlib.Path(__file__).resolve().parents[2]


def load(boom=False):
    W = types.SimpleNamespace(shared=[], logs=[], claimed=[])
    fr = types.ModuleType("frappe")
    fr.session = types.SimpleNamespace(user="linh@x")
    fr.flags = types.SimpleNamespace(mute_messages=False)
    fr.local = types.SimpleNamespace(message_log=[])
    fr._ = lambda s: s
    fr.log_error = lambda *a, **k: W.logs.append(a)
    fr.get_traceback = lambda: "tb"
    tr = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")

    def grant(dt, name, user):
        if boom:
            raise RuntimeError("share loi")
        W.shared.append((dt, name, user))
    tr._engine_grant_read = grant
    perm = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.permissions")
    perm.is_eligible_fulfiller = lambda *a, **k: True
    perm.is_system_manager = lambda *a, **k: False
    svc = types.ModuleType("ecentric_workspace.approval_center.features.daily_target.application.service")
    svc.claim_fulfillment = lambda name: W.claimed.append(name) or {"claimed": True}
    pkg = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    pkg.transitions, pkg.permissions = tr, perm
    for n in ("ecentric_workspace", "ecentric_workspace.approval_center",
              "ecentric_workspace.approval_center.shared", "ecentric_workspace.approval_center.features",
              "ecentric_workspace.approval_center.features.daily_target",
              "ecentric_workspace.approval_center.features.daily_target.application"):
        sys.modules[n] = types.ModuleType(n)
    sys.modules.update({"frappe": fr, "ecentric_workspace.approval_center.shared.workflow": pkg,
                        "ecentric_workspace.approval_center.shared.workflow.transitions": tr,
                        "ecentric_workspace.approval_center.shared.workflow.permissions": perm,
                        "ecentric_workspace.approval_center.features.daily_target.application.service": svc})
    sys.modules["ecentric_workspace.approval_center.features.daily_target.application"].service = svc
    spec = importlib.util.spec_from_file_location("fs", APP / "shared/requests/fulfillment_service.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, W


DEF = types.SimpleNamespace(feature="daily_target", business_doctype="EC Daily Target Request")


def test_nhan_xu_ly_thi_duoc_cap_quyen_doc():
    m, W = load()
    assert m.claim(DEF, "DT-1") == {"claimed": True}
    assert W.claimed == ["DT-1"]
    assert W.shared == [("EC Daily Target Request", "DT-1", "linh@x")]


def test_cap_quyen_loi_khong_lam_hong_viec_nhan():
    m, W = load(boom=True)
    assert m.claim(DEF, "DT-1") == {"claimed": True} and W.logs
