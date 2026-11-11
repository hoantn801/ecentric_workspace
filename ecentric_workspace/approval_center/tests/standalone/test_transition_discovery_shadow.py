# Copyright (c) 2026, eCentric and contributors
"""Chang 2 ky so (11/11/2026): HOI cong buoc hien tai - o che do SHADOW.

Do tren prod 11/11: 0/546 goi co ma workflow instance. `discover_transition` (viet 28/08)
goi `GET /api/Workflow/{instanceId}` bang MA TAI LIEU -> 404 -> chua chay that lan nao. Moi
luot ky tu thang 8 deu lay buoc bang DEM CHU KY. Dung voi DNTT (5/5 buoc ky), sai voi hop dong
(ke toan duyet khong ky) va sai ca voi DNTT khi co nguoi ky tay tren cong (00295, 29/09).

Ban nay CHI them mat de nhin:
  * tra ma instance tu ma tai lieu (`/api/Workflow/instance/history/document/{id}`);
  * hoi cong canh chuyen hien tai;
  * ghi lai cong co dong y voi cach dem khong.

Va cam ket QUAN TRONG NHAT: lenh gui di GIU NGUYEN tung chu. Nhung phep kiem duoi day chot
dieu do truoc, roi moi toi phan ghi nhan.
"""
import ast
import io
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
if _APP not in sys.path:
    sys.path.insert(0, _APP)

DOC = "850f84a9-0687-4aa4-b78a-fd6e34020dee"     # ma TAI LIEU (00641)
INST = "11111111-2222-3333-4444-555555555555"    # ma WORKFLOW INSTANCE - khac han
SIGNER = "389f1581-fbdd-4e50-b0e2-55a16b4b4b3c"

ROW_BUOC_1 = {"transition_id": "-9", "transition_name": "Phe duyet",
              "process_action": "WfFunctionRunSignedOther", "sign_type": "ky-tham-gia",
              "stage": "approval", "step_index": 1, "terminal": False}
ROW_MAC_DINH = {"transition_id": "-9", "transition_name": "Phe duyet",
                "process_action": "WfFunctionRunSignedOther", "sign_type": "ky-tham-gia",
                "terminal": False}


def _read(rel):
    with io.open(os.path.join(_ESIGN, rel), encoding="utf-8") as fh:
        return fh.read()


class _Writes(Exception):
    """Shadow ma GHI vao DB la sai cam ket."""


def _fake_frappe(conf=None):
    fk = types.ModuleType("frappe")
    fk.conf = dict(conf or {})
    fk._ = lambda s: s

    def no_write(*a, **k):
        raise _Writes("shadow khong duoc ghi: %r" % (a,))
    fk.db = types.SimpleNamespace(get_value=lambda *a, **k: None, set_value=no_write)
    fk.get_all = lambda *a, **k: []
    fk.get_doc = lambda *a, **k: None
    fk.log_error = lambda *a, **k: None
    utils = types.ModuleType("frappe.utils")
    utils.add_to_date = lambda *a, **k: None
    utils.get_datetime = lambda v: v
    utils.now_datetime = lambda: None
    pw = types.ModuleType("frappe.utils.password")
    pw.get_decrypted_password = lambda *a, **k: None
    utils.password = pw
    fk.utils = utils
    return fk, {"frappe": fk, "frappe.utils": utils, "frappe.utils.password": pw}


def _load(rel, name, conf=None):
    """exec(compile(nguon)) - khong qua .pyc (bai hoc 01/09: __pycache__ lam hong dot bien)."""
    fk, mods = _fake_frappe(conf)
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        for k in list(sys.modules):
            if k.startswith("ecentric_workspace.platform.esign") and not k.endswith("sanitize"):
                sys.modules.pop(k)
        mod = types.ModuleType(name)
        mod.__file__ = os.path.join(_ESIGN, rel)
        exec(compile(_read(rel), rel, "exec"), mod.__dict__)
        return mod
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v


def _nh(conf=None, cfg_row=ROW_BUOC_1):
    nh = _load("next_handler.py", "_nh_shadow_under_test", conf)
    nh.next_level_approvers = lambda ar, level: ["tuan.ly@ecentric.vn"]
    nh.provider_ids_for = lambda users, env: (["P-TUAN"], [])
    nh._mapped_signature_type = lambda dsr, env: "ky-tham-gia"
    nh.resolve_transition_config = lambda *a, **k: dict(cfg_row) if cfg_row else None
    return nh


class _Doc(object):
    def __init__(self, signed):
        self.signers = ([{"status": "signed"}] * signed) + [{"status": "pending"}] * 3


class _Adapter(object):
    """Cong gia: hoi bang MA TAI LIEU thi 404 (dung nhu prod), bang MA INSTANCE thi tra canh."""

    def __init__(self, discovered=None, lookup=(INST, None), lookup_raises=None, signed=1):
        self.discovered = discovered
        self.lookup = lookup
        self.lookup_raises = lookup_raises
        self.signed = signed
        self.lookups = []
        self.asked = []

    def poll_status(self, document_id):
        return _Doc(self.signed)

    def available_transitions(self, instance_id, user):
        self.asked.append(instance_id)
        if instance_id != INST:
            raise RuntimeError("SctsHttpError: http_404")
        return [self.discovered] if self.discovered else []

    def workflow_instance_for_document(self, document_id, user):
        self.lookups.append((document_id, user))
        if self.lookup_raises:
            raise self.lookup_raises
        return self.lookup

    def eligible_recipients(self, instance_id, transition_id, user):
        return None


def _approve(tid, pa="WfFunctionRunSignedOther", st="ky-tham-gia"):
    return {"transition_id": tid, "transition_name": "Phe duyet", "process_action": pa,
            "sign_type": st, "requires_signature": True, "transition_type": "approve",
            "terminal": False}


DSR = {"effective_scts_user_id": SIGNER, "action": "Sign", "approval_request": "AR",
       "request_level_no": 1, "actor_type": "Approval Level"}


def _plan(nh, adapter, instance_id=DOC, document_id=DOC):
    return nh.plan_handover(dict(DSR), "PROF", "UAT", stage="approval", adapter=adapter,
                            instance_id=instance_id, document_id=document_id)


_LENH = ("mode", "to_users", "config", "reason")


class TestLenhGuiDiGiuNguyen(unittest.TestCase):
    """Cam ket so mot: shadow KHONG doi lenh nao. Bat ky khac biet nao o day = chan merge."""

    def _so(self, adapter_factory):
        tat = _plan(_nh({"ec_esign_transition_discovery": "off"}), adapter_factory())
        mo = _plan(_nh(), adapter_factory())
        for k in _LENH:
            self.assertEqual(tat.get(k), mo.get(k), "shadow doi truong lenh %r" % k)
        self.assertNotIn("discovery_probe", tat, "che do off van di hoi cong")
        self.assertIn("discovery_probe", mo)

    def test_cong_dong_y(self):
        self._so(lambda: _Adapter(discovered=_approve("-9")))

    def test_cong_KHONG_dong_y_van_gui_dung_lenh_cu(self):
        """Cong noi `-10`, cach dem noi `-9`: ban nay van gui `-9`. Chuyen sang tin cong la
        buoc sau, sau khi co so lieu - khong phai o day."""
        self._so(lambda: _Adapter(discovered=_approve("-10")))
        plan = _plan(_nh(), _Adapter(discovered=_approve("-10")))
        self.assertEqual(plan["config"]["transition_id"], "-9")

    def test_tra_ma_instance_that_bai(self):
        self._so(lambda: _Adapter(lookup=(None, "instance_lookup_failed:http_502")))

    def test_hoi_cong_nem_loi(self):
        self._so(lambda: _Adapter(lookup_raises=RuntimeError("mang dut")))

    def test_loi_trong_lop_quan_sat_khong_lot_ra(self):
        """tasks.py roi ve POOL neu plan_handover nem loi. Loi quan sat ma lot ra = doi duong."""
        nh = _nh()
        def no(*a, **k):
            raise ValueError("bug trong shadow")
        nh.shadow_probe = no
        tat = _plan(_nh({"ec_esign_transition_discovery": "off"}), _Adapter(_approve("-9")))
        plan = _plan(nh, _Adapter(discovered=_approve("-9")))
        for k in _LENH:
            self.assertEqual(tat.get(k), plan.get(k), k)
        self.assertIn("shadow_wrapper_failed", plan["discovery_probe"]["why"])

    def test_shadow_khong_ghi_DB(self):
        """frappe.db.set_value cua stub nem loi - chay het la bang chung khong ghi."""
        _plan(_nh(), _Adapter(discovered=_approve("-9")))

    def test_shadow_probe_khong_cham_vao_DB_trong_ma(self):
        """Luu ma instance vao goi = `workflow_instance_id()` tra ma do cho CA lenh ghi
        (transition, bulk-process) -> doi duong gui cua moi phieu ngay lap tuc."""
        src = _read("next_handler.py")
        tree = ast.parse(src)
        fn = [n for n in ast.walk(tree)
              if isinstance(n, ast.FunctionDef) and n.name in ("shadow_probe", "plan_handover")]
        self.assertEqual(len(fn), 2)
        for f in fn:
            seg = ast.get_source_segment(src, f)
            body = seg.split('"""', 2)[-1]    # bo docstring - no duoc phep NHAC toi set_value
            for cam in ("set_value", "db_set", ".save(", ".insert(", "scts_workflow_instance_id ="):
                self.assertNotIn(cam, body, "%s co %s" % (f.name, cam))


class TestGhiNhan(unittest.TestCase):
    def test_dong_y(self):
        p = _plan(_nh(), _Adapter(discovered=_approve("-9")))["discovery_probe"]
        self.assertTrue(p["ok"])
        self.assertTrue(p["agree"])
        self.assertEqual(p["instance_id"], INST)
        self.assertEqual(p["instance_source"], "provider_lookup")

    def test_khac_id_la_khong_dong_y(self):
        p = _plan(_nh(), _Adapter(discovered=_approve("-10")))["discovery_probe"]
        self.assertFalse(p["agree"])
        self.assertEqual(p["transition_id"], "-10")

    def test_cung_id_khac_kieu_ky_la_KHONG_dong_y(self):
        """Ca 28/08: di het quy trinh ma o 'Ky chinh' bo trong. Cung id chua du."""
        p = _plan(_nh(), _Adapter(discovered=_approve("-9", pa="WfFunctionRunSignedA",
                                                       st="ky-chinh")))["discovery_probe"]
        self.assertFalse(p["agree"])

    def test_hoi_bang_MA_INSTANCE_khong_bang_ma_tai_lieu(self):
        a = _Adapter(discovered=_approve("-9"))
        _plan(_nh(), a)
        self.assertEqual(a.lookups, [(DOC, SIGNER)], "tra cuu bang ma tai lieu + nguoi ky")
        self.assertIn(INST, a.asked, "phai hoi canh chuyen bang ma instance vua tra duoc")

    def test_goi_da_co_ma_instance_thi_khong_tra_cuu(self):
        a = _Adapter(discovered=_approve("-9"))
        p = _plan(_nh(), a, instance_id=INST, document_id=DOC)["discovery_probe"]
        self.assertEqual(a.lookups, [])
        self.assertEqual(p["instance_source"], "package")

    def test_loi_duoc_ghi_ro_khong_nuot(self):
        p = _plan(_nh(), _Adapter(lookup_raises=RuntimeError("mang dut")))["discovery_probe"]
        self.assertFalse(p["ok"])
        self.assertIn("probe_failed", p["why"])
        self.assertIn("mang dut", p["why"])

    def test_tra_cuu_that_bai_ghi_ly_do_cua_cong(self):
        p = _plan(_nh(), _Adapter(lookup=(None, "instance_lookup_empty")))["discovery_probe"]
        self.assertEqual(p, {"ok": False, "why": "instance_lookup_empty"})


class TestNguonBuoc(unittest.TestCase):
    def test_dem_chu_ky_ra_dong_theo_vi_tri(self):
        plan = _plan(_nh(), _Adapter(discovered=_approve("-9"), signed=1))
        self.assertEqual(plan["transition_source"], "step_index")

    def test_khong_dem_duoc_la_dong_mac_dinh(self):
        nh = _nh(cfg_row=ROW_MAC_DINH)
        plan = _plan(nh, _Adapter(discovered=_approve("-9"), signed=1))
        self.assertEqual(plan["transition_source"], "profile_default")

    def test_vi_tri_lech_dong_la_dong_mac_dinh(self):
        """Dem ra 3 chu ky ma dong cau hinh la cua buoc 1 -> do la dong mac dinh, khong phai
        dong theo vi tri. Ghi sai nguon thi so lieu shadow vo nghia."""
        plan = _plan(_nh(), _Adapter(discovered=_approve("-9"), signed=3))
        self.assertEqual(plan["transition_source"], "profile_default")


class TestCongTat(unittest.TestCase):
    def test_mac_dinh_la_shadow(self):
        self.assertEqual(_nh({}).transition_discovery_mode(), "shadow")

    def test_tat_that(self):
        for v in ("off", "OFF", "0", 0, "false", "no"):
            self.assertEqual(_nh({"ec_esign_transition_discovery": v})
                             .transition_discovery_mode(), "off", repr(v))

    def test_tat_thi_khong_hoi_gi(self):
        a = _Adapter(discovered=_approve("-9"))
        _plan(_nh({"ec_esign_transition_discovery": "off"}), a)
        self.assertEqual(a.lookups, [])
        self.assertNotIn(INST, a.asked)

    def test_gia_tri_la_van_la_shadow(self):
        """Shadow khong doi lenh gui, nen gia tri la khong co ly do gi de am tham tat mat."""
        self.assertEqual(_nh({"ec_esign_transition_discovery": "bat"})
                         .transition_discovery_mode(), "shadow")


class TestSuKienMangSoLieu(unittest.TestCase):
    """Do duoc ma khong ghi ra thi cung nhu khong do."""

    def _meta_keys(self, event):
        src = _read("tasks.py")
        for n in ast.walk(ast.parse(src)):
            if (isinstance(n, ast.Call) and getattr(n.func, "attr", None) == "emit"
                    and n.args and isinstance(n.args[0], ast.Constant)
                    and n.args[0].value == event):
                for kw in n.keywords:
                    if kw.arg == "request_meta" and isinstance(kw.value, ast.Dict):
                        yield {k.value for k in kw.value.keys if isinstance(k, ast.Constant)}

    def test_handover_targeted(self):
        keys = list(self._meta_keys("HandoverTargeted"))
        self.assertTrue(keys)
        for k in ("discovery_probe", "transition_source", "transition_id"):
            self.assertTrue(all(k in s for s in keys), k)

    def test_pool_fallback_khong_ly_do_san(self):
        keys = [s for s in self._meta_keys("HandoverPoolFallback") if "reason" in s
                and "discovery_probe" in s]
        self.assertTrue(keys, "nhanh pool vi khong goi duoc ten nguoi phai mang discovery_probe")


class TestAdapterTraMaInstance(unittest.TestCase):
    def _adapter(self, resp=None, raises=None):
        scts = _load("providers/scts.py", "_scts_shadow_under_test")
        a = scts.SctsAdapter.__new__(scts.SctsAdapter)
        calls = []

        class C(object):
            def get_instance_history_by_document(self, doc, user, token):
                calls.append((doc, user, token))
                if raises:
                    raise raises
                return resp
        a._client = C()
        a._with_auth = lambda fn: fn("tok")
        return a, calls

    def test_dang_khong_boc(self):
        """Do tren trang cong 09/11: khong co `data`, khoa nam ngay goc."""
        a, calls = self._adapter({"instanceId": INST, "currentStateId": "-3"})
        self.assertEqual(a.workflow_instance_for_document(DOC, SIGNER), (INST, None))
        self.assertEqual(calls, [(DOC, SIGNER, "tok")])

    def test_dang_boc_data(self):
        a, _c = self._adapter({"success": True, "data": {"instanceId": INST}})
        self.assertEqual(a.workflow_instance_for_document(DOC, SIGNER), (INST, None))

    def test_rong(self):
        a, _c = self._adapter({"data": {}})
        self.assertEqual(a.workflow_instance_for_document(DOC, SIGNER),
                         (None, "instance_lookup_empty"))

    def test_loi_khong_lot_ra_ngoai(self):
        a, _c = self._adapter(raises=RuntimeError("http_404"))
        iid, why = a.workflow_instance_for_document(DOC, SIGNER)
        self.assertIsNone(iid)
        self.assertIn("instance_lookup_failed", why)
        self.assertIn("http_404", why)

    def test_client_goi_dung_duong(self):
        src = _read("providers/scts_client.py")
        self.assertIn("/api/Workflow/instance/history/document/%s?userId=%s", src)


if __name__ == "__main__":
    unittest.main()
