# Copyright (c) 2026, eCentric and contributors
"""`thu_sharepoint(apply=1)` GHI len SharePoint -> chi nhan POST (03/11/2026, QA t3).

Frappe rollback cuoi request GET: tep da len SharePoint ma ban ghi lien ket mat, lan dong bo sau
tai them ban nua. GET con mo cua cho mot <img src=...?apply=1> khi SM dang dang nhap.

    python3 -m pytest -q ecentric_workspace/approval_center/tests/standalone/test_sp_probe_post.py
"""
import importlib.util
import pathlib
import sys
import types

APP = pathlib.Path(__file__).resolve().parents[2].parent


def _nap(method):
    goi = []
    fr = types.ModuleType("frappe")
    fr.local = types.SimpleNamespace(request=types.SimpleNamespace(method=method) if method else None)
    fr.session = types.SimpleNamespace(user="admin@e.c")
    fr.get_roles = lambda u: ["System Manager"]
    fr._ = lambda s: s
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr.PermissionError = PermissionError

    def throw(msg, exc=Exception):
        raise exc(msg)
    fr.throw = throw
    fr.db = types.SimpleNamespace(exists=lambda *a, **k: True)
    sp = types.SimpleNamespace(
        wr_sp=types.SimpleNamespace(get_app_token=lambda: "T"),
        _dinh_kem=lambda dt, n: [types.SimpleNamespace(file_name="a.docx")],
        duong_dan=lambda *a: "Contract Review/X/a.docx",
        dong_bo_phieu=lambda dt, n: goi.append(n) or {"xong": ["a.docx"], "hong": []},
        LINK_DT="EC SharePoint File Link")
    fr.get_all = lambda *a, **k: []
    pkg = types.ModuleType("ecentric_workspace.approval_center.shared.integrations")
    pkg.sharepoint_mirror = sp
    gia = {"frappe": fr,
           "ecentric_workspace.approval_center.shared.integrations": pkg,
           "ecentric_workspace.approval_center.shared.integrations.sharepoint_mirror": sp}
    for p in ("ecentric_workspace", "ecentric_workspace.approval_center",
              "ecentric_workspace.approval_center.shared"):
        if p not in sys.modules:
            gia[p] = types.ModuleType(p)
    cu = {k: sys.modules.get(k) for k in gia}
    sys.modules.update(gia)
    try:
        spec = importlib.util.spec_from_file_location(
            "probe_ut", APP / "approval_center/features/contract_review/infrastructure/sharepoint_probe.py")
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
    finally:
        # Tra lai sys.modules: khong de module gia lot sang test khac cung phien pytest.
        for k, v in cu.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return m, goi


def test_apply_qua_GET_khong_ghi_gi():
    m, goi = _nap("GET")
    bao = m.thu_sharepoint(name="EC-CTR-1", apply=1)
    assert goi == []
    assert bao["buoc"][-1]["ok"] is False


def test_apply_qua_POST_van_chay():
    m, goi = _nap("POST")
    m.thu_sharepoint(name="EC-CTR-1", apply=1)
    assert goi == ["EC-CTR-1"]


def test_chi_doc_qua_GET_van_duoc():
    m, goi = _nap("GET")
    bao = m.thu_sharepoint(name="EC-CTR-1", apply=0)
    assert goi == [] and bao["buoc"][-1]["ok"] is True
