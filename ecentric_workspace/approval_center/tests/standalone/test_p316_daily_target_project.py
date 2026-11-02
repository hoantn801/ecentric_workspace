# Copyright (c) 2026, eCentric and contributors
"""p316 (02/11/2026): Daily Target cap Project khong qua buoc Data. Site-free, frappe gia."""
import importlib.util
import os
import sys
import types
import unittest

_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
_PATCH = os.path.join(_ROOT, "approval_center", "patches", "p316_daily_target_project_khong_qua_data.py")
_SETUP = os.path.join(_ROOT, "approval_center", "features", "daily_target", "infrastructure", "setup.py")


class _R(dict):
    __getattr__ = dict.get


def _env(parts, docs):
    fr = types.ModuleType("frappe")
    fr.parts, fr.docs, fr.logs, fr.closed, fr.acts, fr.deleted = parts, docs, [], [], [], []

    def match(r, f):
        for k, v in f.items():
            if isinstance(v, list):
                if v[0] == "in" and r.get(k) not in v[1]:
                    return False
            elif r.get(k) != v:
                return False
        return True

    def get_all(dt, filters=None, fields=None, **kw):
        src = fr.parts if dt == "EC Approval Participant" else fr.docs
        return [_R(r) for r in src if match(r, filters or {})]

    def delete(dt, filters):
        names = filters["name"][1]
        fr.deleted += names
        fr.parts[:] = [p for p in fr.parts if p["name"] not in names]

    def set_value(dt, name, vals, update_modified=True):
        for d in fr.docs:
            if d["name"] == name:
                d.update(vals)
    fr.get_all = get_all
    fr.db = types.SimpleNamespace(delete=delete, set_value=set_value)
    fr.log_error = lambda *a, **k: fr.logs.append(a)
    fr.get_traceback = lambda: "tb"
    eng = types.ModuleType("transitions")
    eng.close_fulfillment_todos = lambda dt, n: fr.closed.append(n)
    eng.log_action = lambda req, action, actor, **kw: fr.acts.append((req, action, actor, kw.get("comment")))
    pkg = "ecentric_workspace.approval_center.shared.workflow"
    mods = {"frappe": fr, pkg: types.ModuleType(pkg), pkg + ".transitions": eng}
    mods[pkg].transitions = eng
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    spec = importlib.util.spec_from_file_location("p316", _PATCH)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return fr, m, saved


def _restore(saved):
    for k, v in saved.items():
        if v is None:
            sys.modules.pop(k, None)
        else:
            sys.modules[k] = v


PARTS = [{"name": "PA1", "parenttype": "EC Approval Process", "parent": "DAILY_TARGET_PROJECT-V1",
          "participant_purpose": "Fulfiller", "role": "EC Data Team"},
         {"name": "PA2", "parenttype": "EC Approval Process", "parent": "DAILY_TARGET_CONSOLIDATED-V1",
          "participant_purpose": "Fulfiller", "role": "EC Data Team"},
         {"name": "PA3", "parenttype": "EC Approval Process", "parent": "DAILY_TARGET_PROJECT-V1",
          "participant_purpose": "Notify", "role": "EC Data Team"}]


def _docs():
    return [
        {"name": "D41", "request_scope": "Project level", "fulfillment_status": "Assigned",
         "fulfillment_owner": None, "approval_request": "A41"},
        {"name": "D40", "request_scope": "Project level", "fulfillment_status": "In Progress",
         "fulfillment_owner": "linh.vuong@ecentric.vn", "approval_request": "A40"},
        {"name": "D49", "request_scope": "Consolidated / Total", "fulfillment_status": "In Progress",
         "fulfillment_owner": "linh.vuong@ecentric.vn", "approval_request": "A49"},
        {"name": "D35", "request_scope": "Project level", "fulfillment_status": "Completed",
         "fulfillment_owner": "linh.vuong@ecentric.vn", "approval_request": "A35"},
    ]


class P313(unittest.TestCase):
    def setUp(self):
        self.fr, self.m, self.saved = _env([dict(p) for p in PARTS], _docs())

    def tearDown(self):
        _restore(self.saved)

    def test_chi_go_fulfiller_cua_process_project(self):
        self.m.execute()
        self.assertEqual(self.fr.deleted, ["PA1"])
        self.assertEqual([p["name"] for p in self.fr.parts], ["PA2", "PA3"])

    def test_dong_buoc_data_chi_phieu_project_dang_mo(self):
        self.m.execute()
        self.assertEqual(sorted(self.fr.closed), ["D40", "D41"])
        st = {d["name"]: (d["fulfillment_status"], d["fulfillment_owner"]) for d in self.fr.docs}
        self.assertEqual(st["D41"], ("Not Started", None))
        self.assertEqual(st["D40"], ("Not Started", None))
        self.assertEqual(st["D49"], ("In Progress", "linh.vuong@ecentric.vn"))   # Consolidated giu
        self.assertEqual(st["D35"], ("Completed", "linh.vuong@ecentric.vn"))     # da xong giu

    def test_ghi_lich_su_ke_ca_nguoi_da_nhan(self):
        self.m.execute()
        a40 = [a for a in self.fr.acts if a[0] == "A40"][0]
        self.assertEqual(a40[1:3], ("System Transition", "Administrator"))
        self.assertIn("linh.vuong@ecentric.vn", a40[3])
        self.assertEqual(len(self.fr.acts), 2)

    def test_chay_lai_khong_lam_gi(self):
        self.m.execute()
        self.fr.closed.clear(); self.fr.acts.clear(); self.fr.deleted.clear()
        self.m.execute()
        self.assertEqual((self.fr.closed, self.fr.acts, self.fr.deleted), ([], [], []))

    def test_loi_khong_nem(self):
        self.fr.db.delete = lambda *a, **k: 1 / 0
        self.m.execute()
        self.assertTrue(self.fr.logs)


class SetupMoi(unittest.TestCase):
    def test_setup_khong_gan_fulfiller_cho_project(self):
        src = open(_SETUP, encoding="utf-8").read()
        i = src.index('_upsert_single_level(PROCESS_PROJECT')
        self.assertIn("fulfiller=False", src[i:i + 200])
        j = src.index('_upsert_single_level(PROCESS_CONSOLIDATED')
        self.assertNotIn("fulfiller=False", src[j:j + 160])


if __name__ == "__main__":
    unittest.main()
