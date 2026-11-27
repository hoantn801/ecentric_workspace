# Copyright (c) 2026, eCentric and contributors
"""27/11/2026 (chi Lien): form 27 - buoc Ke toan dang gui dich danh cho mot nguoi; nut "Chuyen cho ke toan khac".

  * Chi cap co trong routing.HANDOVER_ROLES (Finance Team Review -> role EC Finance), cap dang mo, phieu Pending.
  * Ai bam: nguoi dang duyet cap do, hoac System Manager. Nguoi khac / cap khac: khong co nut, goi API bi chan.
  * Nguoi nhan: dang hoat dong, giu role EC Finance, khong phai nguoi gui / nguoi dang duyet cap do.
  * Ghi DUY NHAT qua engine.reassign_pending_approver (actor that, require_target).
  * Dang cho cong ky xac nhan luot "Duyet & Ky" cua nguoi do: chan.
  * Trang: nut data-act="handover" chi khi server tra extra.handover; modal goi handover_step; p598 + ban ke.
Chay: python -m pytest ecentric_workspace/approval_center/tests/standalone/test_hop_dong_chuyen_ke_toan_27_11.py
"""
import hashlib
import importlib
import json
import os
import re
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
APP = os.path.join(ROOT, "ecentric_workspace")
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
MOD = "ecentric_workspace.approval_center.features.contract_review.application.finance_handover"


class Row(dict):
    __getattr__ = dict.get


class Throw(Exception):
    pass


def _install(state):
    fk = types.ModuleType("frappe")
    fk.PermissionError = type("PermissionError", (Throw,), {})

    def throw(msg, exc=None):
        raise (exc or Throw)(msg)

    def get_value(dt, name, fields=None, as_dict=False, **kw):
        if dt == "EC Approval Request":
            return Row(state["req"]) if state["req"] and name == state["req"]["name"] else None
        if dt == "EC Approval Request Level":
            lv = state["levels"].get(name.get("level_no")) if isinstance(name, dict) else None
            return Row(lv) if lv else None
        if dt == "EC Contract Review Request":
            return state["req"]["name"] if state["req"] else None
        if dt == "User":
            return state["names"].get(name)
        return None

    def get_all(dt, filters=None, **kw):
        if dt == "EC Approval Request Approver":
            return [Row(r) for r in state["rows"] if r["level_no"] == filters["level_no"] and r["status"] == "Pending"]
        if dt == "Has Role":
            return list(state["holders"].get(filters["role"], []))
        return []

    fk.throw = throw
    fk._ = lambda s: s
    fk.get_roles = lambda u: state["roles"].get(u, [])
    fk.get_doc = lambda dt, n: Row(state["req"])
    fk.log_error = lambda *a, **k: None
    fk.db = types.SimpleNamespace(get_value=get_value)
    fk.get_all = get_all
    sys.modules["frappe"] = fk
    for m in [k for k in sys.modules if k.startswith(MOD)]:
        sys.modules.pop(m)
    mod = importlib.import_module(MOD)
    calls = []
    eng = types.SimpleNamespace(
        _is_active_system_user=lambda u: u in state["active"],
        reassign_pending_approver=lambda row, users, **k: calls.append((row, users, k)) or {"added": users})
    mod._engine = lambda: eng
    gate = types.ModuleType("esign_gate")
    gate.in_flight = lambda req, user: state.get("in_flight")
    sys.modules["ecentric_workspace.approval_center.features.contract_review.application.esign_gate"] = gate
    pkg = importlib.import_module("ecentric_workspace.approval_center.features.contract_review.application")
    pkg.esign_gate = gate
    vi = types.ModuleType("vi_display")
    vi.level_name = lambda n: {"Finance Team Review": "Finance Team duyệt"}.get(n, n)
    sys.modules["ecentric_workspace.approval_center.shared.vi_display"] = vi
    importlib.import_module("ecentric_workspace.approval_center.shared").vi_display = vi
    return mod, calls


def _state(**kw):
    s = {"req": {"name": "AR-1", "approval_status": "Pending", "current_level": 2, "requested_by": "thien@ec"},
         "levels": {2: {"name": "L2", "level_name": "Finance Team Review", "level_status": "In Progress"},
                    3: {"name": "L3", "level_name": "Head of Finance Review", "level_status": "Not Started"}},
         "rows": [{"name": "R2", "approver": "lien@ec", "level_no": 2, "status": "Pending"},
                  {"name": "R3", "approver": "phuong@ec", "level_no": 3, "status": "Pending"}],
         "holders": {"EC Finance": ["lien@ec", "kt1@ec", "kt2@ec", "nghi@ec", "thien@ec", "Administrator"]},
         "active": {"lien@ec", "kt1@ec", "kt2@ec", "thien@ec", "phuong@ec"},
         "roles": {"sm@ec": ["System Manager"]}, "names": {"kt1@ec": "Kế toán Một"}}
    s.update(kw)
    return s


class ChuyenKeToan(unittest.TestCase):
    def setUp(self):
        self._saved = {k: sys.modules.get(k) for k in ("frappe",)}

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v

    def test_nguoi_dang_duyet_thay_nut_va_danh_sach(self):
        mod, _ = _install(_state())
        v = mod.view({}, {"name": "AR-1"}, "lien@ec")
        self.assertEqual(v["from"], ["lien@ec"])
        self.assertEqual(v["level_label"], "Finance Team duyệt")
        # bo nguoi dang duyet, nguoi gui, nguoi nghi (khong hoat dong), Administrator
        self.assertEqual([c["user"] for c in v["candidates"]], ["kt1@ec", "kt2@ec"])
        self.assertEqual(v["candidates"][0]["full_name"], "Kế toán Một")

    def test_nguoi_khac_khong_co_nut_sm_co(self):
        mod, _ = _install(_state())
        self.assertIsNone(mod.view({}, {"name": "AR-1"}, "kt1@ec"))
        self.assertIsNone(mod.view({}, {"name": "AR-1"}, "thien@ec"))
        self.assertEqual(mod.view({}, {"name": "AR-1"}, "sm@ec")["from"], ["lien@ec"])

    def test_cap_khac_hoac_phieu_khong_pending_thi_khong(self):
        st = _state()
        st["req"]["current_level"] = 3
        mod, _ = _install(st)
        self.assertIsNone(mod.view({}, {"name": "AR-1"}, "phuong@ec"))
        st = _state()
        st["req"]["approval_status"] = "Information Required"
        mod, _ = _install(st)
        self.assertIsNone(mod.view({}, {"name": "AR-1"}, "lien@ec"))

    def test_chuyen_goi_engine_dung_dong_va_actor(self):
        mod, calls = _install(_state())
        out = mod.handover("CR-1", "kt2@ec", "  KT phụ trách brand  ", "lien@ec")
        self.assertEqual(out, {"from": "lien@ec", "to": "kt2@ec", "level": "Finance Team Review"})
        row, users, kw = calls[0]
        self.assertEqual((row, users), ("R2", ["kt2@ec"]))
        self.assertEqual(kw, {"actor": "lien@ec", "reason": "KT phụ trách brand", "require_target": True})
        mod.handover("CR-1", "kt1@ec", "", "sm@ec")
        self.assertEqual(calls[1][2]["reason"], mod.DEFAULT_REASON)

    def test_chan_sai_nguoi(self):
        mod, calls = _install(_state())
        for target in ("thien@ec", "nghi@ec", "lien@ec", "phuong@ec", "Administrator"):
            with self.assertRaises(Throw):
                mod.handover("CR-1", target, "", "lien@ec")
        with self.assertRaises(Throw):
            mod.handover("CR-1", "kt1@ec", "", "kt2@ec")         # khong phai nguoi dang duyet
        self.assertEqual(calls, [])

    def test_dang_cho_cong_ky_thi_chan(self):
        mod, calls = _install(_state(in_flight={"status": "Verifying"}))
        with self.assertRaises(Throw):
            mod.handover("CR-1", "kt1@ec", "", "lien@ec")
        self.assertEqual(calls, [])


def _read(rel):
    with open(os.path.join(APP, rel), encoding="utf-8") as f:
        return f.read()


class KhaiBao(unittest.TestCase):
    def test_cau_hinh_api_va_trang(self):
        self.assertIn('HANDOVER_ROLES = {FINANCE: "EC Finance"}',
                      _read("approval_center/features/contract_review/domain/routing.py"))
        api = _read("approval_center/features/contract_review/controllers/api.py")
        self.assertIn('@frappe.whitelist(methods=["POST"])\ndef handover_step(name, new_user, reason=None):', api)
        self.assertIn('out["handover"] = ho', _read("approval_center/features/contract_review/application/kol_service.py"))
        key = "approval_center/features/contract_review/ui/main_section.html"
        html = _read(key)
        self.assertIn('if(((det.extra||{}).handover)) btns.push(\'<button type="button" class="btn" data-act="handover">', html)
        self.assertIn('call("handover_step",{name:name,new_user:u,reason:why})', html)
        self.assertNotIn("{{", html)
        man = json.loads(_read("approval_center/patches/resync_manifest.json"))
        with open(os.path.join(APP, key), "rb") as fh:
            self.assertEqual(man[key]["sha256"], hashlib.sha256(fh.read().replace(b"\r\n", b"\n")).hexdigest())
        self.assertTrue(os.path.exists(os.path.join(APP, "approval_center", "patches", man[key]["last_resync_patch"] + ".py")))
        lines = [ln for ln in _read("patches.txt").splitlines() if ln.strip()]
        self.assertEqual(lines.count("ecentric_workspace.approval_center.patches.p598_resync_hop_dong_chuyen_ke_toan"), 1)
        marks = re.search(r"_MARKS = \(([^)]*)\)", _read("approval_center/patches/p598_resync_hop_dong_chuyen_ke_toan.py"),
                          re.S).group(1)
        for m in re.findall(r'"([^"]+)"', marks):
            self.assertIn(m, html)


if __name__ == "__main__":
    unittest.main()
