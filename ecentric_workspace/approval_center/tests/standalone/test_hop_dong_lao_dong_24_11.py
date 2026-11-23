# Copyright (c) 2026, eCentric and contributors
"""Cau D (PO chot 24/11/2026): hop dong lao dong di Nhan su (C&B) -> CEO; loai khac giu luong cu.
  * domain/routing.plan: bo cap theo TEN, chay dung voi process V1 (4 cap) lan V2 (5 cap);
  * service.submit truyen dung skip_level_nos; lao dong khong bao gio bo CEO;
  * gui lai: doi lao dong <-> loai khac sau khi gui theo V2 -> bat tao yeu cau moi;
  * setup_v2: chep nguoi duyet tu process dang Active, them cap Nhan su, moi cap mandatory=0.
Chay: python -m unittest ecentric_workspace.approval_center.tests.standalone.test_hop_dong_lao_dong_24_11
"""
import importlib
import os
import sys
import types
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from test_contract_kol_qc_15_11 import CR, STATE, Doc, Throw, _fresh  # noqa: E402

P = "ecentric_workspace.approval_center.features.contract_review."
LABOR = "Labor / Hợp đồng lao động (EC)"
BUY = "Purchase / Mua vào (EC)"
V1 = [(1, "Department Manager Review"), (2, "Finance Team Review"), (3, "Head of Finance Review"), (4, "CEO Review")]
V2 = V1[:3] + [(4, "HR & C&B Review"), (5, "CEO Review")]


def _routing():
    return importlib.import_module(P + "domain.routing")


class KeHoachCapDuyet(unittest.TestCase):
    def test_v2_lao_dong_chi_nhan_su_va_ceo(self):
        skips, why = _routing().plan(V2, True, False)
        self.assertEqual(skips, (1, 2, 3))
        self.assertIn("Nhân sự", why)

    def test_v2_lao_dong_khong_bao_gio_bo_ceo(self):
        self.assertEqual(_routing().plan(V2, True, True)[0], (1, 2, 3))

    def test_v2_loai_khac_bo_cap_nhan_su(self):
        self.assertEqual(_routing().plan(V2, False, False)[0], (4,))
        self.assertEqual(_routing().plan(V2, False, True)[0], (4, 5))

    def test_v1_giu_nguyen_hanh_vi_cu(self):
        r = _routing()
        self.assertEqual(r.plan(V1, True, False), ((), None))       # lao dong tren V1: du 4 cap
        self.assertEqual(r.plan(V1, False, True)[0], (4,))          # dieu chinh: bo CEO cap 4
        self.assertEqual(r.plan(V1, False, False), ((), None))

    def test_snapshot_luong_lao_dong(self):
        r = _routing()
        self.assertTrue(r.snapshot_is_labor_route(["HR & C&B Review", "CEO Review"]))
        self.assertFalse(r.snapshot_is_labor_route([n for _no, n in V1]))
        self.assertFalse(r.snapshot_is_labor_route(["Department Manager Review", "Finance Team Review",
                                                    "Head of Finance Review", "CEO Review"]))


def _service(levels, calls):
    eng = types.ModuleType("ecentric_workspace.approval_center.shared.workflow.transitions")
    eng.resolve_process = lambda t, c=None: types.SimpleNamespace(name="CONTRACT_REVIEW-V2")
    eng.resolve_levels = lambda name: [types.SimpleNamespace(level_no=n, level_name=nm, participants=[])
                                       for n, nm in levels]
    eng.submit = lambda *a, **k: calls.append(k) or "AR-1"
    eng.resubmit = lambda *a, **k: {}
    eng.resolve_participants = lambda *a, **k: []
    sys.modules[eng.__name__] = eng
    import ecentric_workspace.approval_center.shared.workflow as wf
    wf.transitions = eng
    gate = types.ModuleType(P + "application.esign_gate")
    gate.before_submit = lambda doc: None
    gate.after_submit = lambda doc: None
    sys.modules[gate.__name__] = gate
    sys.modules.pop(P + "application.service", None)
    svc = importlib.import_module(P + "application.service")
    svc._soi_guong_sharepoint = lambda n: None
    svc._requester_context = lambda u: None
    return svc


def _doc(**kw):
    d = Doc(doctype=CR, name="CR-1", request_title="HĐLĐ", request_kind="New", contract_type=LABOR,
            request_type="Template from EC / Mẫu theo khung EC", justification="Tuyển", request_details="x",
            requested_by="hr@ec", approval_request=None, previous_request=None, esign_flow="hd_lao_dong")
    d.update(kw)
    STATE["docs"][(CR, "CR-1")] = d
    return d


class GuiPhieu(unittest.TestCase):
    def setUp(self):
        _fresh("hr@ec")
        sys.modules["frappe"].utils.now_datetime = lambda: __import__("datetime").datetime(2026, 11, 24, 9)

    def test_lao_dong_v2_bo_ba_cap_dau(self):
        calls = []
        svc = _service(V2, calls)
        _doc()
        self.assertEqual(svc.submit("CR-1"), "AR-1")
        self.assertEqual(calls[0]["skip_level_nos"], (1, 2, 3))
        self.assertIn("Nhân sự", calls[0]["skip_reason"])

    def test_mua_vao_v2_chi_bo_cap_nhan_su(self):
        calls = []
        svc = _service(V2, calls)
        _doc(contract_type=BUY, brand="FCV", contract_value=5, esign_flow="khong_ky_cong")
        svc.submit("CR-1")
        self.assertEqual(calls[0]["skip_level_nos"], (4,))

    def test_mua_vao_v1_khong_bo_gi(self):
        calls = []
        svc = _service(V1, calls)
        _doc(contract_type=BUY, brand="FCV", contract_value=5, esign_flow="khong_ky_cong")
        svc.submit("CR-1")
        self.assertIsNone(calls[0]["skip_level_nos"])
        self.assertIsNone(calls[0]["skip_reason"])

    def test_lao_dong_san_co_dieu_chinh_van_qua_ceo(self):
        calls = []
        svc = _service(V2, calls)
        self.assertFalse(svc.skip_ceo(Doc(request_kind="Existing", previous_request="CR-0", contract_type=LABOR),
                                      ["contract_value"]))


class GuiLaiDoiLoai(unittest.TestCase):
    def _svc(self, proc_levels, snap):
        _fresh("hr@ec")
        svc = _service(V2, [])
        STATE["values"][("EC Approval Request", "AR-1")] = "CONTRACT_REVIEW-V2"

        def get_all(dt, filters=None, **kw):
            if dt == "EC Approval Level":
                return [Doc(level_no=n, level_name=nm) for n, nm in proc_levels]
            if dt == "EC Approval Request Level":
                return [Doc(level_no=n, level_name=nm) for n, nm in snap]
            return []
        sys.modules["frappe"].get_all = get_all
        return svc

    def test_lao_dong_doi_sang_loai_khac_bi_chan(self):
        svc = self._svc(V2, V2[3:])
        with self.assertRaises(Throw):
            svc._guard_resubmit_route(Doc(approval_request="AR-1", contract_type=BUY))

    def test_loai_khac_doi_sang_lao_dong_bi_chan(self):
        svc = self._svc(V2, V2[:3] + V2[4:])
        with self.assertRaises(Throw):
            svc._guard_resubmit_route(Doc(approval_request="AR-1", contract_type=LABOR))

    def test_giu_loai_thi_qua(self):
        svc = self._svc(V2, V2[3:])
        svc._guard_resubmit_route(Doc(approval_request="AR-1", contract_type=LABOR))
        svc = self._svc(V2, V2[:3] + V2[4:])
        svc._guard_resubmit_route(Doc(approval_request="AR-1", contract_type=BUY))

    def test_phieu_gui_theo_v1_khong_chan(self):
        svc = self._svc(V1, V1)
        svc._guard_resubmit_route(Doc(approval_request="AR-1", contract_type=LABOR))
        svc._guard_resubmit_route(Doc(approval_request="AR-1", contract_type=BUY))

    def test_cap_ceo_tim_theo_ten_o_snapshot_v2(self):
        svc = self._svc(V2, V2[:3] + V2[4:])
        svc._require_approved_previous = lambda *a, **k: None
        STATE["values"][(CR, "CR-0")] = lambda f, d: Doc(contract_type=BUY, brand="FCV", justification="Mua")
        d = Doc(approval_request="AR-1", contract_type=BUY, request_kind="Existing", previous_request="CR-0",
                brand="KHAC", justification="Mua")
        svc._guard_resubmit_needs_ceo(d)          # snapshot co "CEO Review" (cap 5) -> khong chan
        svc = self._svc(V2, V2[:3])
        svc._require_approved_previous = lambda *a, **k: None
        STATE["values"][(CR, "CR-0")] = lambda f, d: Doc(contract_type=BUY, brand="FCV", justification="Mua")
        with self.assertRaises(Throw):             # snapshot khong co CEO ma doi noi dung -> chan
            svc._guard_resubmit_needs_ceo(d)


class SetupV2(unittest.TestCase):
    def _run(self, src_levels, v2_status=None, hr_ok=True):
        _fresh("Administrator")
        fk = sys.modules["frappe"]
        fk.whitelist = lambda *a, **k: (lambda f: f)
        STATE["values"][("EC Approval Process", "CONTRACT_REVIEW-V2")] = v2_status
        levels = {nm: Doc(name="L%d" % n, level_name=nm, sla_policy="SLA-%d" % n, approval_mode="Any One",
                          participants=[Doc(participant_purpose="Approver", source_type="User", user="u%d@ec" % n)])
                  for n, nm in src_levels}

        def get_all(dt, filters=None, **kw):
            if dt == "EC Approval Process":
                return ["CONTRACT_REVIEW-V1"] if src_levels else []
            if dt == "EC Approval Level":
                return [Doc(name="L%d" % n, level_name=nm, sla_policy="SLA-%d" % n, approval_mode="Any One")
                        for n, nm in src_levels]
            return []
        fk.get_all = get_all
        fk.get_doc = lambda dt, name=None: next(v for v in levels.values() if v.name == name)
        ps = types.ModuleType("ecentric_workspace.approval_center.shared.process_seed")
        ps.require_sm = lambda: None
        ps.new_report = lambda dry: {"errors": [], "warnings": [], "notes": [], "planned": [], "result": None}

        def check_entries(label, entries, rep, optional=()):
            if not hr_ok:
                rep["errors"].append("%s: role chua co nguoi" % label)
                return []
            return list(entries)
        ps.check_entries = check_entries
        ps.rows = lambda entries: [{"participant_purpose": "Approver", "source_type": "Role",
                                    "role": e.split(":", 1)[1]} for e in entries]
        self.spec = None

        def finish(rep, dry, spec_fn, atype):
            if rep["errors"]:
                rep["result"] = "BLOCKED"
                return rep
            self.spec = spec_fn()
            rep["result"] = "APPLIED"
            return rep
        ps.finish_setup = finish
        ps.validate_process = lambda *a, **k: {}
        ps.run_swap = lambda *a, **k: {}
        sys.modules[ps.__name__] = ps
        import ecentric_workspace.approval_center.shared as sh
        sh.process_seed = ps
        sys.modules.pop(P + "infrastructure.setup_v2", None)
        return importlib.import_module(P + "infrastructure.setup_v2").setup_contract_review_v2(dry_run=0, apply=1)

    def tearDown(self):
        sys.modules.pop("ecentric_workspace.approval_center.shared.process_seed", None)
        import ecentric_workspace.approval_center.shared as sh
        if hasattr(sh, "process_seed") and isinstance(sh.process_seed, types.ModuleType) \
                and not getattr(sh.process_seed, "__file__", None):
            del sh.process_seed

    def test_chep_tu_v1_them_cap_nhan_su(self):
        rep = self._run(V1)
        self.assertEqual(rep["result"], "APPLIED")
        lv = self.spec["levels"]
        self.assertEqual([(l["level_no"], l["level_name"]) for l in lv], V2)
        self.assertTrue(all(l["mandatory"] == 0 for l in lv))
        self.assertEqual(lv[4]["participants"][0]["user"], "u4@ec")          # CEO chep tu V1 cap 4
        self.assertEqual(lv[4]["sla_policy"], "SLA-4")
        self.assertEqual(lv[2]["participants"][0]["user"], "u3@ec")
        self.assertEqual([p["role"] for p in lv[3]["participants"]], ["EC CnB", "HR"])
        self.assertEqual(lv[3]["sla_policy"], "SLA-3")
        self.assertEqual(self.spec["code"], "CONTRACT_REVIEW-V2")

    def test_thieu_cap_nguon_thi_chan(self):
        self.assertEqual(self._run(V1[:3])["result"], "BLOCKED")
        self.assertEqual(self._run([])["result"], "BLOCKED")

    def test_role_nhan_su_chua_co_nguoi_thi_chan(self):
        self.assertEqual(self._run(V1, hr_ok=False)["result"], "BLOCKED")

    def test_v2_da_active_bo_qua(self):
        self.assertIn("ACTIVE", self._run(V1, v2_status="Active")["result"])
        self.assertIsNone(self.spec)


class TrangVaPatch(unittest.TestCase):
    def _read(self, rel):
        with open(os.path.join(HERE, "..", "..", rel), encoding="utf-8") as f:
            return f.read()

    def test_trang_xem_truoc_luong_lao_dong(self):
        page = self._read("features/contract_review/ui/main_section.html")
        self.assertIn('LEVELS_LABOR=["Nhân sự (C&B) duyệt","CEO duyệt"]', page)
        self.assertIn("2 cấp (Nhân sự → CEO)", page)
        self.assertIn("||isLabor(d)) return false;", page)

    def test_patch_khai_va_khong_nem(self):
        with open(os.path.join(HERE, "..", "..", "..", "patches.txt"), encoding="utf-8") as f:
            patches = f.read()
        self.assertIn("ecentric_workspace.approval_center.patches.p514_hop_dong_quy_trinh_v2", patches)
        src = self._read("patches/p514_hop_dong_quy_trinh_v2.py")
        self.assertIn("except Exception", src)
        self.assertIn("frappe.db.rollback()", src)
        self.assertLess(src.index("mod.setup_contract_review_v2("), src.index("mod.activate_contract_review_v2("))


if __name__ == "__main__":
    unittest.main()
