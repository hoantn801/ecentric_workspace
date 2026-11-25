# Copyright (c) 2026, eCentric and contributors
"""25/11/2026 (PO qua chat Ky so): phieu toi DA bam "Duyet & Ky" va dang cho cong xac nhan -> KHONG hien o
tab "Cho toi xu ly" (box=fulfil) va khong tinh vao so dem. Cong bao loi han (Permanent Failure) / cap bi
tra lai -> het "dang bay" -> hien lai. Nguon that chung: shared.requests.esign_wait (in_flight_leg).

    python3 -m pytest -q ecentric_workspace/approval_center/tests/standalone/test_esign_wait_cho_toi_25_11.py
"""
import importlib
import io
import os
import sys
import types

_HERE = os.path.dirname(os.path.abspath(__file__))
_AC = os.path.abspath(os.path.join(_HERE, "..", ".."))
_DONG_SCOPE = "from ecentric_workspace.approval_center.reporting import scope as _scope"
EW = "ecentric_workspace.approval_center.shared.requests.esign_wait"
SVC = "ecentric_workspace.platform.esign.service"


class _Swap:
    def __init__(self, mods):
        self.mods = mods

    def __enter__(self):
        self.saved = {k: sys.modules.get(k) for k in self.mods}
        sys.modules.update(self.mods)
        # `from pkg import mod` doc THUOC TINH cua goi truoc sys.modules -> dat ca thuoc tinh.
        self.attrs = []
        for k, v in self.mods.items():
            parent, _, leaf = k.rpartition(".")
            pkg = sys.modules.get(parent) if parent else None
            if pkg is not None:
                self.attrs.append((pkg, leaf, getattr(pkg, leaf, None), hasattr(pkg, leaf)))
                setattr(pkg, leaf, v)
        return self

    def __exit__(self, *a):
        for pkg, leaf, old, had in reversed(self.attrs):
            if had:
                setattr(pkg, leaf, old)
            else:
                try:
                    delattr(pkg, leaf)
                except AttributeError:
                    pass
        for k, v in self.saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _fake_frappe(dsr_rows=(), pending=(), logs=None):
    fr = types.ModuleType("frappe")

    def sql(q, params=None, as_dict=False):
        return [dict(name=n, current_level=l) for n, l in pending]
    fr.db = types.SimpleNamespace(sql=sql, exists=lambda *a, **k: True)
    fr.get_all = lambda dt, filters=None, pluck=None, **k: [r for r in dsr_rows
                                                             if r in (filters or {}).get("approval_request", [None, []])[1]]
    fr.log_error = lambda *a, **k: (logs.append(a) if logs is not None else None)
    fr.get_traceback = lambda: "tb"
    return fr


def _fake_service(legs, calls):
    svc = types.ModuleType(SVC)

    def in_flight_leg(ar, level, user):
        calls.append((ar, level, user))
        return legs.get(ar)
    svc.in_flight_leg = in_flight_leg
    pkg = types.ModuleType("ecentric_workspace.platform.esign")
    pkg.service = svc
    return {"ecentric_workspace.platform": types.ModuleType("ecentric_workspace.platform"),
            "ecentric_workspace.platform.esign": pkg, SVC: svc}


def _ew(fr, mods):
    with _Swap(dict(mods, frappe=fr)):
        sys.modules.pop(EW, None)
        m = importlib.import_module(EW)
    return m


def test_waiting_requests_chi_hoi_phieu_co_ban_ghi_ky():
    calls = []
    mods = _fake_service({"APR-1": {"status": "Verifying", "accepted_at": "2026-11-25 14:05:10"}}, calls)
    fr = _fake_frappe(dsr_rows=["APR-1", "APR-3"])
    with _Swap(dict(mods, frappe=fr)):
        sys.modules.pop(EW, None)
        ew = importlib.import_module(EW)
        got = ew.waiting_requests("lam@ec", {"APR-1": 5, "APR-2": 2, "APR-3": 3})
        sys.modules.pop(EW, None)
    assert got == {"APR-1"}, got
    assert sorted(calls) == [("APR-1", 5, "lam@ec"), ("APR-3", 3, "lam@ec")], calls   # APR-2: khong co ban ghi ky


def test_in_flight_loi_nen_tang_coi_nhu_khong_cho():
    logs = []
    svc = types.ModuleType(SVC)

    def boom(*a):
        raise RuntimeError("x")
    svc.in_flight_leg = boom
    pkg = types.ModuleType("ecentric_workspace.platform.esign")
    pkg.service = svc
    mods = {"ecentric_workspace.platform": types.ModuleType("ecentric_workspace.platform"),
            "ecentric_workspace.platform.esign": pkg, SVC: svc}
    with _Swap(dict(mods, frappe=_fake_frappe(logs=logs))):
        sys.modules.pop(EW, None)
        ew = importlib.import_module(EW)
        assert ew.in_flight("APR-1", 5, "lam@ec") is None
        sys.modules.pop(EW, None)
    assert logs


def _queries(fr, waiting):
    src = io.open(os.path.join(_AC, "reporting", "queries.py"), encoding="utf-8").read()
    assert _DONG_SCOPE in src
    m = types.ModuleType("_q_ew")
    m._scope = types.SimpleNamespace(scope_predicate=lambda s: ("1=1", {}))
    ew = types.ModuleType(EW)
    ew.waiting_requests = lambda user, levels: set(waiting) & set(levels)
    with _Swap({"frappe": fr, EW: ew}):
        exec(compile(src.replace(_DONG_SCOPE, ""), "queries.py", "exec"), m.__dict__)
    m._fulfillment_refs = lambda me: []
    return m, ew


def test_tab_cho_toi_xu_ly_loai_phieu_dang_cho_cong():
    fr = _fake_frappe(pending=[("EC-APR-01321", 5), ("EC-APR-9", 2)])
    q, ew = _queries(fr, {"EC-APR-01321"})
    params = {}
    with _Swap({"frappe": fr, EW: ew}):
        clause = q._my_todo_clause("lam@ec", params)
    assert "r.name NOT IN (%(_ew0)s)" in clause, clause
    assert params["_ew0"] == "EC-APR-01321"
    assert "EC-APR-9" not in params.values()


def test_khong_dang_cho_thi_giu_nguyen():
    fr = _fake_frappe(pending=[("EC-APR-9", 2)])
    q, ew = _queries(fr, set())
    params = {}
    with _Swap({"frappe": fr, EW: ew}):
        clause = q._my_todo_clause("lam@ec", params)
    assert "NOT IN" not in clause
    assert not any(k.startswith("_ew") for k in params)


import unittest  # noqa: E402


class EsignWaitChoToi(unittest.TestCase):
    """Cho `python -m unittest` (script push chay tung module) - goi lai cac ham test o tren."""
    def test_waiting_requests(self):
        test_waiting_requests_chi_hoi_phieu_co_ban_ghi_ky()

    def test_in_flight_loi(self):
        test_in_flight_loi_nen_tang_coi_nhu_khong_cho()

    def test_tab_loai_phieu(self):
        test_tab_cho_toi_xu_ly_loai_phieu_dang_cho_cong()

    def test_giu_nguyen(self):
        test_khong_dang_cho_thi_giu_nguyen()


if __name__ == "__main__":
    unittest.main()
