# Copyright (c) 2026, eCentric and contributors
"""Chang 2 ky so (11/11/2026): HOI cong buoc hien tai - o che do SHADOW.

Do tren prod 11/11: 0/546 goi co ma workflow instance. `discover_transition` (viet 28/08)
goi `GET /api/Workflow/{instanceId}` bang MA TAI LIEU -> 404 -> chua chay that lan nao. Moi
luot ky tu thang 8 deu lay buoc bang DEM CHU KY. Dung voi DNTT (5/5 buoc ky), sai voi hop dong
(ke toan duyet khong ky) va sai ca voi DNTT khi co nguoi ky tay tren cong (00295, 29/09).

Ban nay CHI them mat de nhin: hoi cong buoc hien tai va ghi lai cong co dong y voi cach dem
khong.

Chang 2b (12/11): shadow 11/11 cho thay (19 luot ky that):
  * ma instance TRUNG ma tai lieu tren moi tai lieu - ERP khong thieu ma nhu da tuong;
  * `/api/Workflow/{id}` 404 voi moi tham so -> duong hoi cu sai TU DUONG DAN;
  * `/api/Workflow/instance/history/document/{id}` 500 o 6/8 luot nguoi duyet (userId la GUID
    cua nguoi khac tai khoan dang nhap).
Do tay tren cong 12/11: `/api/Workflow/instance/{ma tai lieu}?userId=` tra 200 voi moi userId,
co `currentStateId` + canh dang mo. Shadow nay dung DUY NHAT duong do, mot lan GET.

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
    """Cong gia. Duong cu `available_transitions` (dung trong `_plan_handover_core`) luon 404
    nhu prod; duong moi `workflow_state_for_document` tra trang thai cau hinh duoc."""

    def __init__(self, edges=None, cur="-6", state_why=None, state_raises=None, signed=1,
                 instance_id=DOC):
        self.edges = edges
        self.cur = cur
        self.state_why = state_why
        self.state_raises = state_raises
        self.signed = signed
        self.instance_id = instance_id
        self.state_calls = []
        self.legacy_calls = []

    def poll_status(self, document_id):
        return _Doc(self.signed)

    def available_transitions(self, instance_id, user, quick=False):
        self.legacy_calls.append((instance_id, quick))
        raise RuntimeError("SctsHttpError: http_404")

    def workflow_state_for_document(self, document_id, user):
        self.state_calls.append((document_id, user))
        if self.state_raises:
            raise self.state_raises
        if self.state_why:
            return None, self.state_why
        return {"instance_id": self.instance_id, "current_state_id": self.cur,
                "transitions": list(self.edges or [])}, None

    def eligible_recipients(self, instance_id, transition_id, user):
        return None


def _edge(tid, ttype="approve", pa="WfFunctionRunSignedOther", st="ky-tham-gia", signed=True,
          name="Phe duyet"):
    return {"transition_id": tid, "transition_name": name, "process_action": pa,
            "sign_type": st, "requires_signature": signed, "transition_type": ttype,
            "terminal": False}


REJECT = _edge("-12", ttype="normal", pa=None, st=None, signed=False, name="Tu choi")


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
        self._so(lambda: _Adapter(edges=[_edge("-9"), REJECT]))

    def test_cong_KHONG_dong_y_van_gui_dung_lenh_cu(self):
        """Cong noi `-10`, cach dem noi `-9`: ban nay van gui `-9`."""
        self._so(lambda: _Adapter(edges=[_edge("-10")]))
        plan = _plan(_nh(), _Adapter(edges=[_edge("-10")]))
        self.assertEqual(plan["config"]["transition_id"], "-9")

    def test_doc_trang_thai_that_bai(self):
        self._so(lambda: _Adapter(state_why="state_lookup_failed:http_500"))

    def test_hoi_cong_nem_loi(self):
        self._so(lambda: _Adapter(state_raises=RuntimeError("mang dut")))

    def test_loi_trong_lop_quan_sat_khong_lot_ra(self):
        """tasks.py roi ve POOL neu plan_handover nem loi. Loi quan sat ma lot ra = doi duong."""
        nh = _nh()

        def no(*a, **k):
            raise ValueError("bug trong shadow")
        nh.shadow_probe = no
        tat = _plan(_nh({"ec_esign_transition_discovery": "off"}), _Adapter([_edge("-9")]))
        plan = _plan(nh, _Adapter(edges=[_edge("-9")]))
        for k in _LENH:
            self.assertEqual(tat.get(k), plan.get(k), k)
        self.assertIn("shadow_wrapper_failed", plan["discovery_probe"]["why"])

    def test_shadow_khong_ghi_DB(self):
        """frappe.db.set_value cua stub nem loi - chay het la bang chung khong ghi."""
        _plan(_nh(), _Adapter(edges=[_edge("-9")]))

    def test_shadow_probe_khong_cham_vao_DB_trong_ma(self):
        src = _read("next_handler.py")
        tree = ast.parse(src)
        fn = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)
              and n.name in ("shadow_probe", "plan_handover", "pick_forward_edge")]
        self.assertEqual(len(fn), 3)
        for f in fn:
            seg = ast.get_source_segment(src, f)
            body = seg.split('"""', 2)[-1]    # bo docstring - no duoc phep NHAC toi set_value
            for cam in ("set_value", "db_set", ".save(", ".insert(", "scts_workflow_instance_id ="):
                self.assertNotIn(cam, body, "%s co %s" % (f.name, cam))

    def test_shadow_khong_dung_duong_cu(self):
        """Duong cu 404 tren prod; shadow hoi no thi chi ton them mot request vo ich."""
        a = _Adapter(edges=[_edge("-9")])
        _plan(_nh(), a)
        self.assertFalse([c for c in a.legacy_calls if c[1]], "shadow khong duoc goi duong cu")
        self.assertEqual(a.state_calls, [(DOC, SIGNER)], "dung MOT lan doc trang thai")


class TestGhiNhan(unittest.TestCase):
    def test_dong_y(self):
        p = _plan(_nh(), _Adapter(edges=[_edge("-9"), REJECT], cur="-5"))["discovery_probe"]
        self.assertTrue(p["ok"])
        self.assertTrue(p["agree"])
        self.assertEqual(p["current_state_id"], "-5")
        self.assertTrue(p["instance_is_document"])

    def test_khac_id_la_khong_dong_y(self):
        p = _plan(_nh(), _Adapter(edges=[_edge("-10")]))["discovery_probe"]
        self.assertFalse(p["agree"])
        self.assertEqual(p["transition_id"], "-10")

    def test_cung_id_khac_kieu_ky_la_KHONG_dong_y(self):
        """Ca 28/08: di het quy trinh ma o 'Ky chinh' bo trong. Cung id chua du."""
        p = _plan(_nh(), _Adapter(edges=[_edge("-9", pa="WfFunctionRunSignedA",
                                                 st="ky-chinh")]))["discovery_probe"]
        self.assertFalse(p["agree"])

    def test_ok_khac_gui_duoc(self):
        """Canh duyet KHONG ky (hop dong) - cong tra loi duoc nhung duong chinh chua gui duoc."""
        p = _plan(_nh(), _Adapter(edges=[_edge("-4", pa=None, st=None, signed=False)]))
        p = p["discovery_probe"]
        self.assertTrue(p["ok"])
        self.assertFalse(p["sendable"])
        p2 = _plan(_nh(), _Adapter(edges=[_edge("-9")]))["discovery_probe"]
        self.assertTrue(p2["sendable"])

    def test_ghi_du_truong_moi_canh(self):
        p = _plan(_nh(), _Adapter(edges=[_edge("-11", ttype="normal"), REJECT]))["discovery_probe"]
        self.assertEqual([e["id"] for e in p["edges"]], ["-11", "-12"])
        self.assertEqual(p["edges"][0]["type"], "normal")
        self.assertTrue(p["edges"][0]["signed"])
        self.assertFalse(p["edges"][1]["signed"])

    def test_ma_hoa_thuong_khac_van_la_cung_tai_lieu(self):
        p = _plan(_nh(), _Adapter(edges=[_edge("-9")], instance_id=DOC.upper()))["discovery_probe"]
        self.assertTrue(p["instance_is_document"])

    def test_cac_khoa_ghi_lai_khong_bi_che(self):
        """sanitize che khoa nao CHUA chuoi nhay cam ('sid', 'content', 'token'...)."""
        sys.path.insert(0, _APP)
        from ecentric_workspace.platform.esign import sanitize
        p = _plan(_nh(), _Adapter(edges=[_edge("-9")]))["discovery_probe"]
        clean = sanitize.sanitize(p)
        self.assertNotIn(sanitize.REDACTED, str(clean), clean)

    def test_instance_khac_tai_lieu_duoc_ghi_lai(self):
        p = _plan(_nh(), _Adapter(edges=[_edge("-9")], instance_id="khac"))["discovery_probe"]
        self.assertFalse(p["instance_is_document"])

    def test_tat_duong_chinh_thi_shadow_khong_goi_gi(self):
        nh = _nh({"ec_esign_targeted_handover": 0})
        a = _Adapter(edges=[_edge("-9")])
        plan = _plan(nh, a)
        self.assertEqual(plan["reason"], "targeted_handover_disabled")
        self.assertEqual(a.state_calls, [])

    def test_loi_duoc_ghi_ro_khong_nuot(self):
        p = _plan(_nh(), _Adapter(state_raises=RuntimeError("mang dut")))["discovery_probe"]
        self.assertFalse(p["ok"])
        self.assertIn("probe_failed", p["why"])
        self.assertIn("mang dut", p["why"])

    def test_doc_that_bai_ghi_ly_do_cua_cong(self):
        p = _plan(_nh(), _Adapter(state_why="state_lookup_empty"))["discovery_probe"]
        self.assertEqual(p, {"ok": False, "why": "state_lookup_empty"})


class TestCanhDiTiep(unittest.TestCase):
    """Do tren cong 12/11: canh 'Phe duyet' cua buoc Ke toan truong (`-11`) la transitionType
    "normal", cung kieu voi 'Tu choi'. Luat chi xet "approve" se dung sai o day."""

    def _pick(self, edges):
        return _nh().pick_forward_edge(edges)

    def test_buoc_ke_toan_truong_canh_normal_co_ky(self):
        e, why = self._pick([_edge("-11", ttype="normal"), REJECT])
        self.assertIsNone(why)
        self.assertEqual(e["transition_id"], "-11")

    def test_canh_approve_thuong(self):
        e, _w = self._pick([_edge("-4", pa="WfFunctionRunSignedA", st="ky-chinh"), REJECT])
        self.assertEqual(e["transition_id"], "-4")

    def test_canh_duyet_KHONG_ky_kieu_approve_van_la_di_tiep(self):
        """Hop dong: ke toan bam duyet, khong ky - cong de transitionType approve."""
        e, _w = self._pick([_edge("-4", pa=None, st=None, signed=False), REJECT])
        self.assertEqual(e["transition_id"], "-4")

    def test_chi_co_tu_choi_thi_khong_chon(self):
        e, why = self._pick([REJECT])
        self.assertIsNone(e)
        self.assertIn("no_forward_transition", why)
        self.assertIn("Tu choi", why)

    def test_hai_canh_di_tiep_khong_chon_thay(self):
        e, why = self._pick([_edge("-9"), _edge("-10", ttype="normal")])
        self.assertIsNone(e)
        self.assertIn("ambiguous_forward_transition", why)

    def test_rong(self):
        self.assertEqual(self._pick([]), (None, "no_available_transition"))

    def test_co_processAction_nhung_KHONG_ky_khong_tinh(self):
        """Nua con lai cua luat: canh 'normal' co processAction ma isSigned=false (QC 12/11)."""
        e, why = self._pick([_edge("-9", ttype="normal", signed=False)])
        self.assertIsNone(e)
        self.assertIn("no_forward_transition", why)

    def test_ly_do_tu_choi_moi_da_khai_la_TU_CHOI(self):
        """Ngay chuyen sang tin cong: 'cong noi khong duoc di' phai dung lai, khong lui ve
        cau hinh cu nhu khi 'khong hoi duoc'."""
        nh = _nh()
        for why in ("no_forward_transition:Tu choi", "ambiguous_forward_transition:-9,-10"):
            self.assertTrue(nh.why_is_refusal(why), why)

    def test_co_ky_nhung_khong_processAction_khong_tinh(self):
        e, why = self._pick([_edge("-9", ttype="normal", pa=None)])
        self.assertIsNone(e)


class TestNguonBuoc(unittest.TestCase):
    def test_dem_chu_ky_ra_dong_theo_vi_tri(self):
        plan = _plan(_nh(), _Adapter(edges=[_edge("-9")], signed=1))
        self.assertEqual(plan["transition_source"], "step_index")

    def test_khong_dem_duoc_la_dong_mac_dinh(self):
        plan = _plan(_nh(cfg_row=ROW_MAC_DINH), _Adapter(edges=[_edge("-9")], signed=1))
        self.assertEqual(plan["transition_source"], "profile_default")

    def test_vi_tri_lech_dong_la_dong_mac_dinh(self):
        plan = _plan(_nh(), _Adapter(edges=[_edge("-9")], signed=3))
        self.assertEqual(plan["transition_source"], "profile_default")


class TestCongTat(unittest.TestCase):
    def test_mac_dinh_la_shadow(self):
        self.assertEqual(_nh({}).transition_discovery_mode(), "shadow")

    def test_tat_that(self):
        for v in ("off", "OFF", "0", 0, "false", "no"):
            self.assertEqual(_nh({"ec_esign_transition_discovery": v})
                             .transition_discovery_mode(), "off", repr(v))

    def test_tat_thi_khong_hoi_gi(self):
        a = _Adapter(edges=[_edge("-9")])
        _plan(_nh({"ec_esign_transition_discovery": "off"}), a)
        self.assertEqual(a.state_calls, [])

    def test_gia_tri_la_van_la_shadow(self):
        self.assertEqual(_nh({"ec_esign_transition_discovery": "bat"})
                         .transition_discovery_mode(), "shadow")


class TestSuKienMangSoLieu(unittest.TestCase):
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
        self.assertTrue(keys)


class TestAdapterDocTrangThai(unittest.TestCase):
    def _adapter(self, resp=None, raises=None):
        scts = _load("providers/scts.py", "_scts_shadow_under_test")
        a = scts.SctsAdapter.__new__(scts.SctsAdapter)
        calls = []

        class C(object):
            def get_workflow_instance_by_document(self, doc, user, token):
                calls.append((doc, user, token))
                if raises:
                    raise raises
                return resp
        a._client = C()
        a._with_auth = lambda fn: fn("tok")
        return a, calls

    _RAW_EDGES = [{"transitionId": "-11", "transitionName": "Phe duyet", "isSigned": True,
                   "signType": "ky-tham-gia", "transitionType": "normal",
                   "processAction": "WfFunctionRunSignedOther", "toState": "-4"},
                  {"transitionId": "-12", "transitionName": "Tu choi", "transitionType": "normal",
                   "toState": "-3"}]

    def test_dang_khong_boc(self):
        """Hinh dang do tren cong 12/11: instance + availableTransitions o goc."""
        a, calls = self._adapter({"instance": {"instanceId": DOC, "currentStateId": "-7"},
                                  "availableTransitions": self._RAW_EDGES})
        st, why = a.workflow_state_for_document(DOC, SIGNER)
        self.assertIsNone(why)
        self.assertEqual(st["current_state_id"], "-7")
        self.assertEqual(st["instance_id"], DOC)
        self.assertEqual([t["transition_id"] for t in st["transitions"]], ["-11", "-12"])
        self.assertTrue(st["transitions"][0]["requires_signature"])
        self.assertEqual(calls, [(DOC, SIGNER, "tok")])

    def test_dang_boc_data(self):
        a, _c = self._adapter({"success": True, "data": {
            "instance": {"currentStateId": -5}, "availableTransitions": []}})
        st, why = a.workflow_state_for_document(DOC, SIGNER)
        self.assertEqual(st["current_state_id"], "-5")

    def test_khong_co_trang_thai_hien_tai(self):
        a, _c = self._adapter({"instance": {}, "availableTransitions": self._RAW_EDGES})
        self.assertEqual(a.workflow_state_for_document(DOC, SIGNER),
                         (None, "state_lookup_no_current_state"))

    def test_hinh_dang_la_khong_nem(self):
        a, _c = self._adapter({"instance": {"currentStateId": "-5"}, "availableTransitions": 7})
        st, why = a.workflow_state_for_document(DOC, SIGNER)
        self.assertEqual(st["transitions"], [])
        a2, _c2 = self._adapter({"instance": "x", "availableTransitions": []})
        self.assertEqual(a2.workflow_state_for_document(DOC, SIGNER),
                         (None, "state_lookup_no_current_state"))

    def test_rong(self):
        a, _c = self._adapter("khong phai dict")
        self.assertEqual(a.workflow_state_for_document(DOC, SIGNER), (None, "state_lookup_empty"))

    def test_loi_khong_lot_ra_ngoai(self):
        a, _c = self._adapter(raises=RuntimeError("http_500"))
        st, why = a.workflow_state_for_document(DOC, SIGNER)
        self.assertIsNone(st)
        self.assertIn("state_lookup_failed", why)
        self.assertIn("http_500", why)

    def test_duong_cu_va_duong_moi_chuan_hoa_giong_nhau(self):
        a, _c = self._adapter({"instance": {"currentStateId": "-7"},
                               "availableTransitions": self._RAW_EDGES})
        st, _w = a.workflow_state_for_document(DOC, SIGNER)

        class C2(object):
            def get_workflow_instance(self, iid, user, token, quick=False):
                return {"availableTransitions": TestAdapterDocTrangThai._RAW_EDGES}
        a._client = C2()
        self.assertEqual(a.available_transitions(DOC, SIGNER), st["transitions"])


class TestClient(unittest.TestCase):
    """Duong doc moi: dung route, 1 lan thu, 5 giay. Lenh khac giu mac dinh."""

    def _client(self, statuses):
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_scts_client_quick", os.path.join(_ESIGN, "providers", "scts_client.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        calls = []

        class R(object):
            def __init__(self, st):
                self.status_code = st

            def json(self):
                return {"instance": {"currentStateId": "-5"}}

        def transport(method, url, headers=None, json_body=None, timeout=None, verify_tls=True):
            calls.append((url, timeout))
            return R(statuses[min(len(calls) - 1, len(statuses) - 1)])
        c = m.SctsClient("https://x.example", transport=transport, sleeper=lambda s: None)
        return c, calls

    def test_route_dung(self):
        c, calls = self._client([200])
        c.get_workflow_instance_by_document(DOC, SIGNER, "tok")
        self.assertEqual(calls[0][0],
                         "https://x.example/api/Workflow/instance/%s?userId=%s" % (DOC, SIGNER))

    def test_mot_lan_thu_5_giay(self):
        c, calls = self._client([500, 500, 500])
        with self.assertRaises(Exception):
            c.get_workflow_instance_by_document(DOC, SIGNER, "tok")
        self.assertEqual(len(calls), 1, "5xx khong duoc thu lai o lenh shadow")
        self.assertEqual(calls[0][1], 5)

    def test_duong_chinh_giu_mac_dinh(self):
        c, calls = self._client([502, 502, 502])
        with self.assertRaises(Exception):
            c.get_workflow_instance(DOC, SIGNER, "tok")
        self.assertEqual(len(calls), 3, "duong chinh giu 1 + 2 lan thu lai nhu cu")
        self.assertEqual(calls[0][1], 30)

    def test_duong_500_da_bo(self):
        src = _read("providers/scts_client.py")
        self.assertNotIn("instance/history/document", src.split('"""')[0] + "".join(
            src.split('"""')[2::2]), "duong 500 khong duoc goi nua")


if __name__ == "__main__":
    unittest.main()
