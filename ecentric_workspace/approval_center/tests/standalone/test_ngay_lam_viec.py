"""Ai dang nghi hom nay (03/10/2026, Hoan) - job nhac viec khong ban vao cuoi tuan / le / nghi phep.

    python -m pytest ecentric_workspace/approval_center/tests/standalone/test_ngay_lam_viec.py
"""
import datetime as dt
import importlib.util
import pathlib
import sys
import types

APP = pathlib.Path(__file__).resolve().parents[3]


class Obj(dict):
    def __getattr__(self, k):
        return self.get(k)


def load(emps=None, holidays=None, leaves=None, boom=False):
    W = types.SimpleNamespace(logs=[])
    fr = types.ModuleType("frappe")

    def get_all(dt_, filters=None, fields=None, limit_page_length=None, **k):
        if boom:
            raise RuntimeError("db loi")
        if dt_ == "Employee":
            e = (emps or {}).get(filters["user_id"])
            return [Obj(e)] if e else []
        if dt_ == "Leave Application":
            d = filters["from_date"][1]
            return [1 for (emp, a, b) in (leaves or []) if emp == filters["employee"] and a <= d <= b]
        raise AssertionError(dt_)
    fr.get_all = get_all
    fr.log_error = lambda title=None, message=None: W.logs.append(title)
    fr.get_traceback = lambda: "tb"
    fu = types.ModuleType("frappe.utils")
    fu.getdate = lambda v: v if isinstance(v, dt.date) else dt.date.fromisoformat(str(v))
    fu.nowdate = lambda: "2026-10-05"
    hol = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.holidays")
    hol.resolve_holiday_list = lambda employee=None, company=None: "HL-" + (company or "")
    hol.holiday_dates = lambda hl: set((holidays or {}).get(hl, ()))
    for name in ("ecentric_workspace", "ecentric_workspace.approval_center",
                 "ecentric_workspace.approval_center.shared"):
        sys.modules[name] = types.ModuleType(name)
    pkg = types.ModuleType("ecentric_workspace.approval_center.shared.workflow")
    pkg.holidays = hol
    sys.modules.update({"frappe": fr, "frappe.utils": fu,
                        "ecentric_workspace.approval_center.shared.workflow": pkg,
                        "ecentric_workspace.approval_center.shared.workflow.holidays": hol})
    spec = importlib.util.spec_from_file_location(
        "nlv", APP / "approval_center/shared/workflow/ngay_lam_viec.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m, W


EMPS = {"a@x": {"name": "E-A", "company": "EC"}, "b@x": {"name": "E-B", "company": "EC"}}
MON, SAT, SUN = dt.date(2026, 10, 5), dt.date(2026, 10, 3), dt.date(2026, 10, 4)


def test_cuoi_tuan_luon_nghi_ke_ca_nguoi_khong_co_ho_so():
    m, _ = load(EMPS)
    assert m.la_ngay_nghi("a@x", SAT) and m.la_ngay_nghi("a@x", SUN)
    assert m.la_ngay_nghi("khong-co@x", SAT) and not m.la_ngay_nghi("khong-co@x", MON)


def test_ngay_le_theo_holiday_list():
    m, _ = load(EMPS, holidays={"HL-EC": [MON]})
    assert m.la_ngay_nghi("a@x", MON)
    assert not m.la_ngay_nghi("a@x", dt.date(2026, 10, 6))


def test_nghi_phep_da_duyet_chi_nguoi_do():
    m, _ = load(EMPS, leaves=[("E-A", dt.date(2026, 10, 5), dt.date(2026, 10, 6))])
    assert m.la_ngay_nghi("a@x", MON) and not m.la_ngay_nghi("b@x", MON)
    assert m.nguoi_di_lam(["a@x", "b@x", "b@x", None], MON) == ["b@x"]


def test_loi_tra_cuu_thi_coi_la_di_lam_va_ghi_log():
    m, W = load(EMPS, boom=True)
    assert m.la_ngay_nghi("a@x", MON) is False and W.logs
    assert m.la_ngay_nghi("a@x", SAT) is True          # cuoi tuan khong can tra cuu
