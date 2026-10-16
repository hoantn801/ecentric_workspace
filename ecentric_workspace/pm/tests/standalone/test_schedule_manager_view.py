"""PO 16/10/2026: department head sees task titles + meeting subjects in a staff member's
Lịch làm việc; teammates still see 'Bận'; Outlook Private meetings stay 'Họp riêng'."""
import sys, types, unittest, importlib.util, os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.abspath(os.path.join(HERE, "..", "..", "api", "schedule.py"))


def load(fake_get_all, depts_of):
    fr = types.ModuleType("frappe")
    fr.whitelist = lambda *a, **k: (lambda f: f)
    fr._ = lambda s: s
    fr.get_all = fake_get_all
    fr.PermissionError = PermissionError
    fr.throw = lambda msg, exc=Exception: (_ for _ in ()).throw(exc(msg))
    fr.session = types.SimpleNamespace(user="boss@x")
    fr.get_conf = lambda: {}
    ut = types.ModuleType("frappe.utils")
    for n in ("get_datetime", "getdate", "add_days", "nowdate", "now_datetime", "cint", "flt",
              "cstr", "add_to_date", "time_diff_in_hours", "get_time", "format_date"):
        setattr(ut, n, lambda *a, **k: None)
    ut.__getattr__ = lambda name: (lambda *a, **k: None)
    fr.utils = ut
    sys.modules["frappe"] = fr
    sys.modules["frappe.utils"] = ut
    pm = types.ModuleType("ecentric_workspace.pm.permissions")
    pm.get_user_departments = lambda u: depts_of.get(u, [])
    pm.require_pm_access = lambda *a, **k: None
    pm.can_see_all_pm_data = lambda u=None: False
    pm.visible_task_subset = lambda names, u: []
    pm.can_view_task = lambda *a, **k: False
    pkg = types.ModuleType("ecentric_workspace.pm"); pkg.permissions = pm
    sys.modules.setdefault("ecentric_workspace", types.ModuleType("ecentric_workspace"))
    sys.modules["ecentric_workspace.pm"] = pkg
    sys.modules["ecentric_workspace.pm.permissions"] = pm
    src = open(SRC, encoding="utf-8").read()
    mod = types.ModuleType("schedule_under_test")
    exec(compile(src, SRC, "exec"), mod.__dict__)
    return mod


class T(unittest.TestCase):
    def ga(self, heads):
        def get_all(dt, filters=None, fields=None, **k):
            if dt == "Department":
                if "manager_email" in (filters or {}):
                    return [{"name": d} for d, m in heads.items() if m == filters["manager_email"]]
                names = filters["name"][1]
                return [{"name": d, "manager_email": heads.get(d, "")} for d in names]
            return []
        return get_all

    def test_head_detected(self):
        m = load(self.ga({"Ecom": "boss@x"}), {"staff@x": ["Ecom"]})
        self.assertTrue(m._is_department_head_of("boss@x", "staff@x"))

    def test_teammate_not_head(self):
        m = load(self.ga({"Ecom": "boss@x"}), {"staff@x": ["Ecom"]})
        self.assertFalse(m._is_department_head_of("peer@x", "staff@x"))

    def test_case_insensitive_and_self(self):
        m = load(self.ga({"Ecom": "Boss@X"}), {"staff@x": ["Ecom"], "boss@x": ["Ecom"]})
        self.assertTrue(m._is_department_head_of("boss@x", "staff@x"))
        self.assertFalse(m._is_department_head_of("boss@x", "boss@x"))

    def test_no_department_fail_safe(self):
        m = load(self.ga({}), {})
        self.assertFalse(m._is_department_head_of("boss@x", "ghost@x"))


if __name__ == "__main__":
    unittest.main()
