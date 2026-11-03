# Copyright (c) 2026, eCentric and contributors
"""Gia tri o loc phai la chuoi / so truoc khi thanh tham so SQL (03/11/2026, QA t3).

`reporting.api._parse_filters` chep `category` / `requester` / `approver`... NGUYEN tu JSON
client. Mot dict (`{"approver": {"x": 1}}`) lot xuong driver: PyMySQL <= 1.1.0 khong escape khoa
dict (CVE-2024-36039), ban da va thi nem TypeError -> loi 500 cho ca tab "Tat ca".

    python3 -m pytest -q ecentric_workspace/approval_center/tests/standalone/test_queries_kieu_gia_tri_loc.py
"""
import io
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_DONG_SCOPE = "from ecentric_workspace.approval_center.reporting import scope as _scope"


def _nap():
    fr = types.ModuleType("frappe")
    fr.db = types.SimpleNamespace(sql=lambda *a, **k: [])
    src = io.open(os.path.join(_AC, "reporting", "queries.py"), encoding="utf-8").read()
    assert _DONG_SCOPE in src
    m = types.ModuleType("_q_kieu")
    m._scope = types.SimpleNamespace(scope_predicate=lambda s: ("1=1", {}))
    cu = sys.modules.get("frappe")
    sys.modules["frappe"] = fr
    try:
        exec(compile(src.replace(_DONG_SCOPE, ""), "queries.py", "exec"), m.__dict__)
    finally:
        if cu is None:
            sys.modules.pop("frappe", None)
        else:
            sys.modules["frappe"] = cu
    return m


def _khong_co_dict(params):
    return all(not isinstance(v, (dict, list, tuple, set, bool)) for v in params.values())


def test_dict_trong_o_loc_bi_bo_khong_xuong_driver():
    q = _nap()
    params = {}
    frag = q._non_date_filters({"category": {"x') OR 1=1 -- ": 1},
                                "approver": {"a": "b"},
                                "requester": True,
                                "department": ["Sales", {"k": 1}, ["x"]]}, params)
    assert _khong_co_dict(params), params
    assert not any("approver" in f.lower() and "exists" in f.lower() for f in frag)
    assert frag == ["r.requester_department IN (%(f_department_0)s)"], frag
    assert params == {"f_department_0": "Sales"}


def test_list_approver_khong_lam_vo_cau_lenh():
    q = _nap()
    params = {}
    q._non_date_filters({"approver": ["a@e.c", "b@e.c"]}, params)
    assert "f_approver" not in params


def test_gia_tri_hop_le_giu_nguyen():
    q = _nap()
    params = {}
    frag = q._non_date_filters({"category": "Finance", "current_level": 2,
                                "approver": "a@e.c", "status": ["Pending", "Approved"]}, params)
    assert params["f_category"] == "Finance" and params["f_current_level"] == 2
    assert params["f_approver"] == "a@e.c"
    assert "r.approval_status IN (%(f_status_0)s, %(f_status_1)s)" in frag


def test_danh_sach_rong_sau_khi_loc_thi_khong_sinh_IN_rong():
    q = _nap()
    params = {}
    frag = q._non_date_filters({"department": [{"a": 1}]}, params)
    assert frag == [] and params == {}
