# Copyright (c) 2026, eCentric and contributors
"""PR-F (23/11/2026): doi tac ky eKYC + kiem giay phep CMC; HD lao dong WF03 (doi tac ky GIUA
chuoi, buoc nguoi lap sau doi tac `-11`); kiem vai tro khoi tao cua nguoi lap tren cong.

  1. scts_client: get_licence / get_workflow_json / get_users_paged / get_roles - dung duong
     dan, CHI 401 -> scts_auth_error (dang nhap lai); 403 -> scts_read_forbidden (KHONG dang
     nhap lai); 4xx khac -> khong retry. (Nap bang exec - khong dung sys.modules cua test khac.)
  2. adapter: licence() co cache, assert_partner_sign_types_available (eKYC het luot -> chan,
     image khong kiem, khong doc duoc -> khong chan); workflow_nodes doc mo hinh GoJS (data la
     chuoi JSON); user_roles khop email chinh xac; _unwrap.
  3. next_handler.plan_portal_step: canh toi buoc EXTERNAL -> nhanh doi tac du ERP con nguoi
     (WF03 `-8`); canh noi bo -> nhu cu; khong doc duoc + khong con ai -> dung; BRIDGE_STAGE.
  4. portal_steps: chan nguoi lap / chan sau doi tac khong lan nhau; bridge_done; start_bridge_step
     chi khi buoc dau xong, tao chan co transition_id; _bridge_edge_open.
  5. tasks.retrieve_signed_bundles: ho so hop dong chi phieu Approved (DNTT nhu cu);
     flag_silent_legs goi sweep_partner_bridges.
  6. requester.assert_requester_portal_role: chi ho so hop dong; thieu vai -> chan; khong doc duoc
     -> khong chan.
"""
import ast
import io
import json
import os
import sys
import textwrap
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")
if _APP not in sys.path:
    sys.path.insert(0, _APP)


def _read(*p):
    with io.open(os.path.join(_ESIGN, *p), encoding="utf-8") as fh:
        return fh.read()


class _D(dict):
    __getattr__ = dict.get


class _PE(Exception):
    def __init__(self, code, msg="", retryable=True, **k):
        Exception.__init__(self, code)
        self.code, self.msg, self.message, self.retryable = code, msg, msg, retryable


class _Throw(Exception):
    pass


def _fns(src, names):
    out = []
    for n in ast.parse(src).body:
        nm = getattr(n, "name", None)
        if nm is None and isinstance(n, ast.Assign):
            nm = getattr(n.targets[0], "id", None)
        if nm in names:
            out.append(textwrap.dedent(ast.get_source_segment(src, n)))
    assert len(out) == len(names), (names, len(out))
    return "\n\n".join(out)


def _methods(src, cls, names):
    """Nguyen van cac phuong thuc cua mot lop (de gan vao lop gia)."""
    node = [n for n in ast.parse(src).body if isinstance(n, ast.ClassDef) and n.name == cls][0]
    out = [textwrap.dedent(ast.get_source_segment(src, m)) for m in node.body
           if isinstance(m, ast.FunctionDef) and m.name in names]
    assert len(out) == len(names), (names, len(out))
    return "\n\n".join(out)


class _Cache(object):
    def __init__(self):
        self.d, self.ttl = {}, {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v
        self.ttl[k] = expires_in_sec


def _fk(**kw):
    cache = _Cache()
    fk = types.SimpleNamespace(log_error=lambda *a, **k: None, get_traceback=lambda: "tb",
                               _dict=_D, cache=lambda: cache, _cache=cache)
    for k, v in kw.items():
        setattr(fk, k, v)
    return fk


# =============================================================================== 1. client
class _Resp(object):
    def __init__(self, status, body):
        self.status_code, self._b = status, body
        self.text = json.dumps(body)

    def json(self):
        return self._b


def _load_client():
    """scts_client + base nap bang exec (QC 23/11: import that hong khi test khac da thay
    `ecentric_workspace` trong sys.modules)."""
    base = types.ModuleType("_prov_base")
    exec(compile(_read("providers", "base.py"), "base.py", "exec"), base.__dict__)
    key = "ecentric_workspace.platform.esign.providers.base"
    old = sys.modules.get(key)
    sys.modules[key] = base
    try:
        m = types.ModuleType("_scts_client")
        exec(compile(_read("providers", "scts_client.py"), "scts_client.py", "exec"), m.__dict__)
    finally:
        if old is None:
            sys.modules.pop(key, None)
        else:
            sys.modules[key] = old
    return m, base


class TestClient(unittest.TestCase):
    def _client(self, status=200, body=None):
        m, base = _load_client()
        seen = []

        def transport(method, url, headers=None, json_body=None, timeout=30, verify_tls=True):
            seen.append((method, url, timeout))
            return _Resp(status, body if body is not None else {"data": {}})
        return m.SctsClient("https://signx.cmc.vn", transport=transport,
                            sleeper=lambda s: None), seen, base

    def test_duong_dan(self):
        c, seen, _b = self._client()
        c.get_licence("T")
        c.get_workflow_json("05E6F032", "T")
        c.get_users_paged("a.b@ecentric.vn", "T")
        c.get_roles("T")
        urls = [u for _m, u, _t in seen]
        self.assertEqual(urls[0], "https://signx.cmc.vn/api/Settings/GetLicence")
        self.assertEqual(urls[1], "https://signx.cmc.vn/api/WorkflowDefinition/GetJson/05E6F032")
        self.assertIn("/api/User/GetPaged?pageIndex=1&pageSize=50&keyword=a.b%40ecentric.vn",
                      urls[2])
        self.assertEqual(urls[3], "https://signx.cmc.vn/api/Role/GetAll")
        self.assertTrue(all(m == "GET" and t == 5 for m, _u, t in seen), "doc nhanh, chi GET")

    def test_401_403_va_4xx(self):
        c, _s, base = self._client(status=401)
        with self.assertRaises(base.ProviderError) as cm:
            c.get_licence("T")
        self.assertTrue(cm.exception.code.startswith("scts_auth_error"))
        c, _s, base = self._client(status=403)
        with self.assertRaises(base.ProviderError) as cm:
            c.get_workflow_json("W", "T")
        self.assertEqual(cm.exception.code, "scts_read_forbidden",
                         "403 = thieu quyen, KHONG dang nhap lai")
        c, _s, base = self._client(status=404)
        with self.assertRaises(base.ProviderError) as cm:
            c.get_roles("T")
        self.assertEqual(cm.exception.code, "scts_read_rejected_404")
        self.assertFalse(cm.exception.retryable)


# =============================================================================== 2. adapter
_ADAPTER_FNS = ["_service_auth", "licence", "assert_partner_sign_types_available",
                "workflow_nodes", "user_roles", "role_names"]


def _adapter(client):
    src = _read("providers", "scts.py")
    fk = _fk()
    g = {"frappe": fk, "ProviderError": _PE}
    exec(compile(_fns(src, ["PARTNER_SIGN_TYPES", "PARTNER_DEFAULT_SIGN_TYPE", "_LICENCE_FIELDS",
                            "_SIGN_TYPE_LABEL", "LICENCE_CACHE_SECONDS",
                            "LICENCE_EMPTY_CACHE_SECONDS", "WORKFLOW_CACHE_SECONDS",
                            "ROLES_CACHE_SECONDS", "FAIL_CACHE_SECONDS", "_FAIL", "_is_fail",
                            "partner_sign_type_message", "_unwrap", "_rows_of",
                            "_cache_get", "_cache_set", "_external_handlers_payload"]),
                 "s", "exec"), g)
    body = "class A(object):\n" + textwrap.indent(_methods(src, "SctsAdapter", _ADAPTER_FNS), "    ")
    sa = types.ModuleType("ecentric_workspace.platform.esign.sanitize")
    sa.safe_error = lambda e: str(e)
    sys.modules.setdefault("ecentric_workspace.platform.esign.sanitize", sa)
    exec(compile(body, "a", "exec"), g)
    a = g["A"]()
    a._name, a._client, a._user_token = "CMC", client, None
    a._with_auth = lambda fn: fn(a._user_token or "SVC")
    return a, g, fk


class _FakeClient(object):
    def __init__(self, **resp):
        self.resp, self.calls = resp, []

    def _r(self, k):
        self.calls.append(k)
        v = self.resp.get(k)
        if isinstance(v, Exception):
            raise v
        return v

    def get_licence(self, t):
        return self._r("licence")

    def get_workflow_json(self, d, t):
        self.tokens = getattr(self, "tokens", []) + [t]
        return self._r("wf")

    def get_users_paged(self, kw, t):
        return self._r("users")

    def n(self, k):
        return self.calls.count(k)

    def get_roles(self, t):
        return self._r("roles")


LIC = {"data": {"docTotal": 2100, "ekycTotal": 0, "esginTotal": 500, "vnetTotal": 100,
                "nfcTotal": 0, "emailTotal": 10000}}
WF03 = {"class": "GraphLinksModel", "nodeDataArray": [
    {"key": "START", "type": "Start"}, {"key": "STOP", "type": "End"},
    {"key": 3, "text": "Khoi tao", "type": "Step", "processingType": "INTERNAL",
     "roles": ["R-CNB", "R-KT"]},
    {"key": 4, "text": "Doi tac", "type": "Step", "processingType": "EXTERNAL"},
    {"key": 6, "text": "CEO", "type": "Step", "processingType": "INTERNAL", "roles": ["R-CEO"]}],
    "linkDataArray": [{"id": -1, "from": "START", "to": 3}, {"id": -8, "from": 3, "to": 4},
                      {"id": -7, "from": 4, "to": 3}, {"id": -11, "from": 3, "to": 6},
                      {"id": -5, "from": 6, "to": "STOP"}]}


class TestAdapter(unittest.TestCase):
    def test_ekyc_het_luot_thi_chan(self):
        a, _g, _f = _adapter(_FakeClient(licence=LIC))
        with self.assertRaises(_PE) as cm:
            a.assert_partner_sign_types_available([{"SignType": "ekyc"}])
        self.assertEqual(cm.exception.code, "partner_sign_type_unavailable")
        self.assertFalse(cm.exception.retryable)
        self.assertIn("eKYC", cm.exception.msg)

    def test_con_luot_va_image_khong_kiem(self):
        c = _FakeClient(licence=LIC)
        a, _g, _f = _adapter(c)
        a.assert_partner_sign_types_available([{"SignType": "vnetid"}, {"SignType": "esign"}])
        a.assert_partner_sign_types_available([{"SignType": "image"}, {"SignType": "token"}])
        a.assert_partner_sign_types_available([])
        self.assertEqual(c.calls, ["licence"], "image/token/rong khong hoi; cache lan 2")

    def test_khong_doc_duoc_thi_khong_chan(self):
        a, _g, _f = _adapter(_FakeClient(licence=RuntimeError("500")))
        a.assert_partner_sign_types_available([{"SignType": "ekyc"}])
        self.assertIsNone(a.licence())

    def test_workflow_nodes_chuoi_json(self):
        c = _FakeClient(wf={"data": json.dumps(WF03)})
        a, _g, _f = _adapter(c)
        wf = a.workflow_nodes("WF03")
        self.assertEqual(wf["start_node"], "3")
        self.assertTrue(wf["nodes"]["4"]["external"])
        self.assertFalse(wf["nodes"]["6"]["external"])
        self.assertEqual(wf["nodes"]["3"]["roles"], ["R-CNB", "R-KT"])
        a.workflow_nodes("WF03")
        self.assertEqual(c.calls, ["wf"], "cache")
        self.assertIsNone(a.workflow_nodes(None))

    def test_doc_cau_hinh_bang_tai_khoan_tich_hop(self):
        c = _FakeClient(wf=WF03)
        a, _g, _f = _adapter(c)
        a._user_token = "USER"
        self.assertTrue(a.workflow_nodes("W"))
        self.assertEqual(c.tokens, ["SVC"], "khong dung token nguoi dung")
        self.assertEqual(a._user_token, "USER", "tra lai token nguoi dung")

    def test_workflow_nodes_loi_hoac_la(self):
        a, _g, _f = _adapter(_FakeClient(wf=RuntimeError("x")))
        self.assertIsNone(a.workflow_nodes("W"))
        a, _g, _f = _adapter(_FakeClient(wf={"data": {"foo": 1}}))
        self.assertIsNone(a.workflow_nodes("W"))

    def test_user_roles_khop_chinh_xac(self):
        users = {"data": {"totalRecords": 2, "data": [
            {"email": "Hoan.Tran@ecentric.vn", "roleIds": ["R-KT"]},
            {"email": "hoan.tran2@ecentric.vn", "roleIds": ["R-CNB"]}]}}
        a, _g, _f = _adapter(_FakeClient(users=users))
        self.assertEqual(a.user_roles("hoan.tran@ecentric.vn"), ["R-KT"])
        a, _g, _f = _adapter(_FakeClient(users={"data": {"data": []}}))
        self.assertIsNone(a.user_roles("x@ecentric.vn"), "khong thay -> None (khong chan)")
        a, _g, _f = _adapter(_FakeClient(users=RuntimeError("x")))
        self.assertIsNone(a.user_roles("x@ecentric.vn"))

    def test_role_names(self):
        a, _g, _f = _adapter(_FakeClient(roles={"data": [{"id": "R-CNB", "name": "Chuyen vien CnB"}]}))
        self.assertEqual(a.role_names(), {"R-CNB": "Chuyen vien CnB"})

    def test_mac_dinh_ekyc_va_goi_kiem_truoc_add_document(self):
        _a, g, _f = _adapter(_FakeClient())
        out = g["_external_handlers_payload"]([{"full_name": "A", "email": "a@x.vn"}])
        self.assertEqual(out[0]["SignType"], "ekyc")
        self.assertIn("Gói CMC chưa có lượt eKYC", g["partner_sign_type_message"]("ekyc"))
        src = _read("providers", "scts.py")
        i = src.index("def create_document(")
        body = src[i:src.index("\n    @staticmethod", i)]
        self.assertLess(body.index("self.assert_partner_sign_types_available(handlers)"),
                        body.index("self._client.add_document(payload, t)"))

    def test_luot_0_cache_ngan_thieu_truong_khong_chan(self):
        a, _g, fk = _adapter(_FakeClient(licence=LIC))
        a.licence()
        self.assertEqual(fk._cache.ttl["esign:scts:licence:CMC"], 60, "con luot = 0 -> 60s")
        a, _g, fk = _adapter(_FakeClient(licence={"data": {"esginTotal": 5}}))
        a.assert_partner_sign_types_available([{"SignType": "ekyc"}])   # khong co truong ekyc
        self.assertEqual(fk._cache.ttl["esign:scts:licence:CMC"], 600)

    def test_loi_doc_cache_5_phut(self):
        c = _FakeClient(licence=RuntimeError("x"), wf=RuntimeError("x"), roles=RuntimeError("x"),
                        users=RuntimeError("x"))
        a, _g, fk = _adapter(c)
        for _i in range(3):
            self.assertIsNone(a.licence())
            self.assertIsNone(a.workflow_nodes("W"))
            self.assertEqual(a.role_names(), {})
            self.assertIsNone(a.user_roles("x@ecentric.vn"))
        self.assertEqual([c.n(k) for k in ("licence", "wf", "roles", "users")], [1, 1, 1, 1])
        self.assertEqual(fk._cache.ttl["esign:scts:licence:CMC"], 300)

    def test_user_roles_theo_ma_anh_xa_fresh_va_items(self):
        users = {"data": {"items": [
            {"id": "U-1", "email": "lap.cong@ecentric.vn", "roleIds": ["R-KT"]},
            {"id": "U-2", "email": "khac@ecentric.vn", "roleIds": ["R-CNB"]}]}}
        c = _FakeClient(users=users)
        a, _g, _f = _adapter(c)
        self.assertEqual(a.user_roles("lap@ecentric.vn", provider_user_id="u-1"), ["R-KT"],
                         "email cong khac email ERP -> khop theo ma anh xa")
        a.user_roles("lap@ecentric.vn", provider_user_id="u-1")
        self.assertEqual(c.n("users"), 1, "cache")
        a.user_roles("lap@ecentric.vn", provider_user_id="u-1", fresh=True)
        self.assertEqual(c.n("users"), 2, "fresh bo qua cache")


# =============================================================================== 3. next_handler
def _nh(allow, wf, approvers, eligible, current_level=2, internal=(), final=None):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.conf = {}
    rows = [_D(action="Forward", stage="requester", transition_id=-8,
               transition_name="Chuyen doi tac ky", process_action=None, sign_type=None,
               terminal=0),
            _D(action="Forward", stage="requester:after_partner", transition_id=-11,
               transition_name="Trinh CEO", process_action=None, sign_type=None, terminal=0)]

    def gv(dt, n, f=None, **k):
        if f == "allow_external_signers":
            return allow
        if f == "workflow_definition_id":
            return "WF03"
        if f == "current_level":
            return current_level
        return None
    fk.db = types.SimpleNamespace(
        get_value=gv, exists=lambda dt, f=None, **k: (
            dt == "EC SCTS User Mapping" and str((f or {}).get("scts_user_id")) in internal))
    fk.get_all = lambda dt, *a, **k: ([_D(level_no=final)] if (
        dt == "EC Approval Request Approver" and final is not None) else [])
    fk.get_doc = lambda dt, n: _D(transitions=rows)
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: "tb"
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = utils.add_to_date = utils.get_datetime = lambda *a, **k: None
    mods = {"frappe": fk, "frappe.utils": utils}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    try:
        nh = types.ModuleType("_nh_prf")
        exec(compile(_read("next_handler.py"), "next_handler.py", "exec"), nh.__dict__)
    finally:
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    seen = {}

    def nla(ar, lv):
        seen["level"] = lv
        return list(approvers)
    nh.next_level_approvers = nla
    nh.provider_ids_for = lambda users, env: (["P-" + u for u in users], [])
    nh._seen = seen
    ad = types.SimpleNamespace(eligible_recipients=lambda *a: eligible,
                               workflow_nodes=lambda d: wf)
    return nh, ad


REQ = _D(name="DSR-R", approval_request="AR-1", action="Approve", actor_type="Requester",
         effective_scts_user_id="U-LAP")
BRIDGE = _D(REQ, name="DSR-B", transition_id=-11)
WF = {"nodes": {"3": {"external": False}, "4": {"external": True}, "6": {"external": False}},
      "start_node": "3"}


def _st(tid, to):
    return {"current_state_id": "3", "transitions": [
        {"transition_id": tid, "transition_name": "x", "requires_signature": False,
         "process_action": None, "sign_type": None, "to_state": to, "terminal": False}]}


class TestKeHoach(unittest.TestCase):
    def test_wf03_nguoi_lap_chuyen_doi_tac_du_erp_con_ceo(self):
        nh, ad = _nh(1, WF, ["ceo@x"], {"DT-1"})
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual((p["mode"], p["to_users"]), ("transition", ["DT-1"]))
        self.assertTrue(p["partner_handover"])

    def test_buoc_doi_tac_van_chan_nguoi_noi_bo(self):
        nh, ad = _nh(1, WF, ["ceo@x"], {"KT-7"}, internal=("KT-7",))
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["reason"], "partner_recipient_internal:KT-7")

    def test_ho_so_khong_doi_tac_khong_hoi_quy_trinh(self):
        nh, ad = _nh(0, None, ["ceo@x"], None)
        ad.workflow_nodes = lambda d: (_ for _ in ()).throw(AssertionError("khong duoc hoi"))
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["to_users"], ["P-ceo@x"])

    def test_buoc_sau_doi_tac_trinh_ceo(self):
        self.assertEqual(_nh(1, WF, [], None)[0].portal_stage_for(BRIDGE), "requester:after_partner")
        self.assertEqual(_nh(1, WF, [], None)[0].portal_stage_for(REQ), "requester")
        nh, ad = _nh(1, WF, ["ceo@x"], {"P-ceo@x"}, current_level=3)
        p = nh.plan_portal_step(BRIDGE, _st(-11, "6"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual((p["mode"], p["to_users"]), ("transition", ["P-ceo@x"]))
        self.assertEqual(p["config"]["transition_id"], -11)
        self.assertEqual(nh._seen["level"], 2, "trinh cho cap ERP dang mo")
        self.assertFalse(p.get("partner_handover"))

    def test_khong_doc_duoc_quy_trinh_khong_con_ai_luat_pr_d(self):
        """WF09 CEO `-5`: chua cap quyen GetJson -> KHONG dung han, ve luat cap ERP cuoi."""
        nh, ad = _nh(1, None, [], {"DT-1"}, final=1)
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual((p["mode"], p["to_users"]), ("transition", ["DT-1"]))
        self.assertTrue(p["partner_handover"])
        nh, ad = _nh(1, None, [], {"DT-1"}, final=5)
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["reason"], "no_next_level_approver:not_final_level")
        nh, ad = _nh(1, None, [], {"KT-7"}, final=1, internal=("KT-7",))
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["reason"], "partner_recipient_internal:KT-7")

    def test_khong_doc_duoc_va_khong_hoi_duoc_nguoi_nhan_thi_dung(self):
        """WF03 `-8`: khong biet buoc dich + khong hoi duoc nguoi nhan -> KHONG gui cho CEO."""
        nh, ad = _nh(1, None, ["ceo@x"], None)
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual((p["mode"], p["reason"]), ("wait", "partner_recipient_unverified"),
                         "khong gui; CHO thu lai (loi doc tam thoi khong lam chan dung han)")
        nh, ad = _nh(1, None, ["ceo@x"], {"P-ceo@x"}, current_level=3)
        p = nh.plan_portal_step(BRIDGE, _st(-11, "6"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["to_users"], ["P-ceo@x"], "cong xac nhan nguoi nhan -> gui")
        nh, ad = _nh(1, None, ["ceo@x"], {"DT-1"})
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["reason"], "recipient_not_eligible:P-ceo@x")

    def test_buoc_noi_bo_khong_con_ai_ve_luat_pr_d(self):
        """Nut dich khong danh dau EXTERNAL, ERP khong con ai: ve luat PR-D (cap cuoi + mot
        nguoi cong chap nhan, khong noi bo) thay vi dung (QC vong 2 M-4)."""
        nh, ad = _nh(1, WF, [], None)
        p = nh.plan_portal_step(BRIDGE, _st(-11, "6"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual(p["reason"], "no_next_level_approver:not_final_level")

    def test_nut_noi_bo_o_cap_cuoi_van_giao_doi_tac_theo_pr_d(self):
        """QC vong 2 M-4: GetJson doc duoc nhung nut doi tac khong danh dau EXTERNAL -> o cap ERP
        CUOI van ve luat PR-D (_partner_plan: dung mot nguoi, khong noi bo)."""
        nh, ad = _nh(1, WF, [], {"DT-1"}, current_level=3, final=2)
        p = nh.plan_portal_step(BRIDGE, _st(-11, "6"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual((p["mode"], p["to_users"]), ("transition", ["DT-1"]))
        self.assertTrue(p["partner_handover"])
        self.assertEqual(p["workflow_node_kind"], "internal")

    def test_buoc_doi_tac_khong_hoi_duoc_nguoi_nhan_thi_cho(self):
        """QC vong 2 M-3: buoc doi tac, users-for-transition loi (None) -> CHO, khong dung han."""
        nh, ad = _nh(1, WF, ["ceo@x"], None)
        p = nh.plan_portal_step(REQ, _st(-8, "4"), "P", "UAT", adapter=ad, instance_id="I")
        self.assertEqual((p["mode"], p["reason"]), ("wait", "partner_recipient_unverified"))

    def test_bridge_step(self):
        nh, _ad = _nh(1, WF, [], None)
        self.assertEqual(nh.bridge_step("P")["transition_id"], -11)


# =============================================================================== 4. portal_steps
def _ps(rows=(), req=None, profile="P", bridge=True, mapping=True, inserted=None, token="TOK",
        existing=None, retire_ok=True, sql_rows=(), profiles=(), linked_at=None):
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.throw = lambda m, *a: (_ for _ in ()).throw(_Throw(m))
    fk.log_error = lambda *a, **k: None
    fk.get_traceback = lambda: "tb"
    fk._dict = _D
    cache = _Cache()
    fk.cache = lambda: cache
    ins = inserted if inserted is not None else []
    w = {"retired": [], "emits": [], "sql": [], "commits": 0, "bao": []}

    class Doc(_D):
        def insert(self, ignore_permissions=False):
            self["name"] = "DSR-NEW"
            ins.append(dict(self))
            return self
    fk.get_doc = lambda d: Doc(d)

    def get_all(dt, filters=None, fields=None, **k):
        if dt == "EC Digital Signature Profile":
            return [_D(x) for x in profiles]
        return [_D(r) for r in rows]
    fk.get_all = get_all

    def gv(dt, n, f=None, **k):
        if dt == "EC Approval Request":
            return req
        if dt == "EC Digital Signature Package":
            return _D(name="PKG-1", package_version=1, package_hash="H", provider="SCTS",
                      environment="UAT", scts_document_id="DOC", profile="P",
                      business_doctype="X", business_name="Y")
        if dt == "EC Digital Signature Provider Settings":
            return _D(username="api@x")
        if dt == "EC Digital Signature Request":
            return existing
        if dt == "EC Digital Signature Profile":
            return 1
        return None

    def sql(q, params=None, as_dict=False):
        w["sql"].append((q, params))
        return [_D(x) for x in sql_rows]
    fk.db = types.SimpleNamespace(get_value=gv, exists=lambda *a, **k: False, sql=sql,
                                  commit=lambda: w.__setitem__("commits", w["commits"] + 1),
                                  rollback=lambda: None)
    utils = types.ModuleType("frappe.utils")
    utils.now_datetime = lambda: None
    utils.get_datetime = lambda v: v
    ev = types.ModuleType("ev")
    ev.emit = lambda *a, **k: w["emits"].append((a, k))
    ev.set_dsr_status = lambda *a, **k: None
    gd = types.ModuleType("gd")
    gd.get_active_profile = lambda *a: profile
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.events, root.guard = ev, gd
    nh = types.ModuleType("nh")
    nh.bridge_step = lambda p: ({"transition_id": -11} if bridge else None)
    hs = types.ModuleType("hs")
    hs.idempotency_key = lambda *a: "K-" + a[3]
    pk = types.ModuleType("pk")
    pk.signable_package_for_request = lambda ar: "PKG-1"
    pm = types.ModuleType("pm")
    pm.verified_mapping = lambda u, e: (_D(name="M", modified="t", scts_user_id="U-LAP")
                                        if mapping else None)
    ul = types.ModuleType("ul")
    ul.needs_own_token = lambda u, s: True
    ul.token_for = lambda u, e: token
    ul._token_row = lambda u, e: {"api_token_linked_at": linked_at}
    sv = types.ModuleType("sv")

    def retire(ex, actor, who_vi=None):
        if not retire_ok:
            raise _Throw("may have sent")
        w["retired"].append(ex.name)
        return True
    sv.retire_dead_leg = retire
    root.next_handler, root.hashing, root.package, root.permissions = nh, hs, pk, pm
    root.user_link, root.service = ul, sv
    mods = {"frappe": fk, "frappe.utils": utils, "ecentric_workspace.platform.esign": root,
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.guard": gd,
            "ecentric_workspace.platform.esign.next_handler": nh,
            "ecentric_workspace.platform.esign.hashing": hs,
            "ecentric_workspace.platform.esign.package": pk,
            "ecentric_workspace.platform.esign.permissions": pm,
            "ecentric_workspace.platform.esign.user_link": ul,
            "ecentric_workspace.platform.esign.service": sv}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    m = types.ModuleType("_ps")
    exec(compile(_read("portal_steps.py"), "portal_steps.py", "exec"), m.__dict__)
    m._enqueue = lambda n: ins.append(("enqueue", n))
    m._bao = lambda req, msg, also_level=False: w["bao"].append(msg)
    m._w, m._cache = w, cache
    m._restore = lambda: [sys.modules.pop(k, None) if v is None else sys.modules.__setitem__(k, v)
                          for k, v in saved.items()]
    return m, ins


REQ_ROW = _D(name="AR-1", reference_doctype="EC Contract Review Request", reference_name="CTR-1",
             approval_type="CR", approval_status="Pending", requested_by="lap@x", current_level=3)
DONE = {"name": "A", "status": "Approval Completed", "transition_id": 0}


def _tasks_stub(**kw):
    tk = types.ModuleType("tk")
    tk._disabled = lambda: False
    tk._integration_open = lambda p, e: True
    tk.handled = []
    tk._handle_partner_round = lambda pkg, why: tk.handled.append((pkg, why))
    tk._outcome_closed = lambda pkg: False
    for k, v in kw.items():
        setattr(tk, k, v)
    return tk


class TestBridge(unittest.TestCase):
    def tearDown(self):
        sys.modules.pop("ecentric_workspace.platform.esign.tasks", None)
        sys.modules.pop("ecentric_workspace.platform.esign.signed_files", None)
        if getattr(self, "_m", None):
            self._m._restore()

    def _with(self, name, mod):
        sys.modules["ecentric_workspace.platform.esign." + name] = mod
        setattr(sys.modules["ecentric_workspace.platform.esign"], name, mod)

    def test_hai_loai_chan_khong_lan(self):
        rows = [DONE, {"name": "B", "status": "Queued", "transition_id": -11}]
        self._m, _i = _ps(rows=rows)
        self.assertEqual([r.name for r in self._m._requester_step_rows("AR-1")], ["A"])
        self.assertEqual([r.name for r in self._m._requester_step_rows("AR-1", bridge=True)], ["B"])
        self.assertIs(self._m.bridge_done(REQ_ROW, "PKG-1"), False)

    def test_bridge_done_none_khi_khong_khai(self):
        self._m, _i = _ps(bridge=False)
        self.assertIsNone(self._m.bridge_done(REQ_ROW, "PKG-1"))

    def test_chi_tao_khi_buoc_dau_xong(self):
        self._m, ins = _ps(rows=[{"name": "A", "status": "Queued", "transition_id": 0}],
                           req=REQ_ROW)
        self.assertEqual(self._m.start_bridge_step("AR-1")["reason"], "requester_step_not_done")
        self.assertEqual(ins, [])

    def test_tao_chan_co_transition_id(self):
        self._m, ins = _ps(rows=[DONE], req=REQ_ROW)
        r = self._m.start_bridge_step("AR-1")
        self.assertTrue(r["started"])
        doc = ins[0]
        self.assertEqual((doc["actor_type"], doc["action"], doc["transition_id"]),
                         ("Requester", "Approve", -11))
        self.assertEqual(doc["idempotency_key"], "K-requester-bridge")
        self.assertIn(("enqueue", "DSR-NEW"), ins)

    def test_token_het_han_bao_mot_lan_khong_tao(self):
        self._m, ins = _ps(rows=[DONE], req=REQ_ROW, token=None)
        for _i in range(3):
            self.assertEqual(self._m.start_bridge_step("AR-1")["reason"], "requester_not_linked")
        self.assertEqual(ins, [])
        self.assertEqual(len(self._m._w["bao"]), 1, "bao MOT lan, khong spam moi 5 phut")
        self.assertIn("Kết nối CMC", self._m._w["bao"][0])

    def test_chan_cu_dung_han_chi_tao_lai_khi_loi_ket_noi_va_da_ket_noi_lai(self):
        """QC vong 2 B-1: chi tao lai chan hong vi KET NOI CMC va nguoi lap DA ket noi lai sau
        lan hong. Con lai de van hanh (khong vong tao lai vo tan)."""
        def run(err, linked, retire_ok=True):
            dead = _D(name="B", status="Permanent Failure", error_code=err,
                      modified="2026-11-23 10:00:00")
            rows = [DONE, {"name": "B", "status": "Permanent Failure", "transition_id": -11,
                           "error_code": err}]
            if getattr(self, "_m", None):
                self._m._restore()
            self._m, ins = _ps(rows=rows, req=REQ_ROW, existing=dead, retire_ok=retire_ok,
                               linked_at=linked)
            return self._m.start_bridge_step("AR-1"), ins
        r, ins = run("scts_user_token_rejected", "2026-11-23 11:00:00")
        self.assertTrue(r["started"])
        self.assertEqual(self._m._w["retired"], ["B"])
        for err, linked in (("scts_user_token_rejected", "2026-11-23 09:00:00"),
                            ("scts_user_token_rejected", None),
                            ("recipient_not_eligible:P-ceo", "2026-11-23 11:00:00"),
                            ("next_handler_unmapped:ceo@x", "2026-11-23 11:00:00")):
            r, ins = run(err, linked)
            self.assertEqual(r["reason"], "previous_bridge_needs_review", (err, linked))
            self.assertEqual((ins, self._m._w["retired"]), ([], []))
        r, ins = run("requester_not_linked", "2026-11-23 11:00:00", retire_ok=False)
        self.assertEqual(r["reason"], "previous_bridge_needs_review")
        self.assertEqual(ins, [])

    def test_hai_vong_quet_lien_tiep_khong_tao_lai_chan_dung(self):
        """Sweep 5 phut x2 voi chan dung vi ly do khong phai ket noi: khong tao chan moi, khong
        thong bao lap lai; SQL loai phieu do khoi vong quet."""
        dead = _D(name="B", status="Permanent Failure", error_code="recipient_not_eligible:X",
                  modified="t0")
        rows = [DONE, {"name": "B", "status": "Permanent Failure", "transition_id": -11,
                       "error_code": "recipient_not_eligible:X"}]
        reqs = [{"name": "AR-1", "reference_doctype": "X", "approval_type": "CR",
                 "reference_name": "Y", "requested_by": "lap@x"}]
        self._m, ins = _ps(rows=rows, req=REQ_ROW, existing=dead, sql_rows=reqs,
                           profiles=[{"name": "P", "business_doctype": "X",
                                      "approval_type": "CR"}], linked_at="t9")
        self._with("tasks", _tasks_stub())
        self._m._partner_gate = lambda pkg: "signed"
        self._m._bridge_edge_open = lambda r, pkg, tid: True
        for _i in range(2):
            self.assertEqual(self._m.sweep_partner_bridges(limit=50), [])
        self.assertEqual((ins, self._m._w["retired"], self._m._w["bao"]), ([], [], []))
        q, params = self._m._w["sql"][0]
        self.assertIn("NOT IN %(token_errs)s", q)
        self.assertIn("scts_user_token_rejected", params["token_errs"])

    def test_da_co_chan_song(self):
        rows = [DONE, {"name": "B", "status": "Verifying", "transition_id": -11}]
        self._m, ins = _ps(rows=rows, req=REQ_ROW)
        self.assertEqual(self._m.start_bridge_step("AR-1")["reason"], "exists")
        self.assertEqual(ins, [])

    def test_cau_chan_theo_trang_thai(self):
        def msg(rows, bridge=True, fpl=3):
            self._m, _i = _ps(rows=rows, bridge=bridge)
            self._m.first_portal_level = lambda req: fpl
            out = self._m.bridge_gate_message(REQ_ROW, "PKG-1")
            self._m._restore()
            self._m = None
            return out
        self.assertIn("Đối tác chưa ký xong", msg([DONE]))
        self.assertIn("ERP đang trình", msg([DONE, {"name": "B", "status": "Queued",
                                                     "transition_id": -11}]))
        self.assertIn("đang lỗi (chờ đối soát)", msg([DONE, {"name": "B",
                                                               "status": "Manual Review",
                                                               "transition_id": -11}]))
        self.assertIsNone(msg([DONE, {"name": "B", "status": "Approval Completed",
                                      "transition_id": -11}]))
        self.assertIsNone(msg([DONE], fpl=2), "chi chan o cap cong DAU TIEN")
        self.assertIsNone(msg([DONE], bridge=False), "ho so khong co buoc sau doi tac")

    def _gate(self, doc, ext):
        if getattr(self, "_m", None):
            self._m._restore()
        self._m, _i = _ps()
        ad = types.SimpleNamespace(poll_status=lambda d: doc)
        self._with("tasks", _tasks_stub(_settings_and_adapter=lambda d: ({}, ad)))
        sf = types.ModuleType("sf")
        exec(compile(_fns(_read("signed_files.py"), ["_RETURNED", "_partner_state",
                                                     "_is_partner"]), "sf", "exec"), sf.__dict__)
        sf._external_expectation = lambda pkg: ext
        self._with("signed_files", sf)
        return self._m._partner_gate("PKG-1")

    def test_cong_doi_tac(self):
        A = {"email": "ceo@ec", "status": "pending", "is_external": False}

        def P(st, raw=None):
            return {"email": "kol@x.vn", "status": st, "is_external": True,
                    "provider_status": raw}

        def doc(signers, status="processing", destroyed=False):
            return _D(status=status, signers=signers, identity={"destroyed": destroyed})
        ext = frozenset(["kol@x.vn"])
        self.assertEqual(self._gate(doc([A, P("signed")]), ext), "signed")
        self.assertEqual(self._gate(doc([A, P("pending")]), ext), "waiting_partner")
        self.assertEqual(self._gate(doc([A]), ext), "waiting_partner", "chua thay doi tac")
        self.assertEqual(self._gate(doc([A, P("rejected", "từ chối")]), ext), "partner_rejected")
        self.assertEqual(self._gate(doc([A, P("rejected", "trả lại")]), ext), "partner_returned")
        self.assertEqual(self._gate(doc([P("signed")], status="cancelled"), ext),
                         "document_dead:cancelled")
        self.assertEqual(self._gate(doc([P("signed")]), None), "partner_info_missing")

    def test_quet_chi_tao_khi_doi_tac_ky_xong_va_bao_tu_choi(self):
        reqs = [{"name": n, "reference_doctype": "X", "approval_type": "CR",
                 "reference_name": "Y", "requested_by": "lap@x"} for n in
                ("AR-1", "AR-2", "AR-3", "AR-4")]
        self._m, _i = _ps(sql_rows=reqs, profiles=[{"name": "P", "business_doctype": "X",
                                                    "approval_type": "CR"}])
        tk = _tasks_stub(_outcome_closed=lambda pkg: False)
        self._with("tasks", tk)
        gates = {"AR-1": "signed", "AR-2": "partner_rejected", "AR-3": "waiting_partner",
                 "AR-4": "signed"}
        cur = {}
        self._m.signable = None
        pk = sys.modules["ecentric_workspace.platform.esign.package"]
        pk.signable_package_for_request = lambda ar: cur.setdefault("ar", ar) and ar
        pk.signable_package_for_request = lambda ar: ar
        self._m._partner_gate = lambda pkg: gates[pkg]
        self._m._bridge_edge_open = lambda r, pkg, tid: pkg == "AR-1"
        started = []
        self._m.start_bridge_step = lambda n, quiet=True: started.append(n) or {"started": True}
        out = self._m.sweep_partner_bridges(limit=50)
        self.assertEqual(out, ["AR-1"], "AR-4 doi tac ky nhung canh chua mo -> cho")
        self.assertEqual(started, ["AR-1"])
        self.assertEqual(tk.handled, [("AR-2", "partner_rejected")])
        self.assertTrue(any(a[0] == "SignedRetrievalNotReady" for a, _k in self._m._w["emits"]))
        q, params = self._m._w["sql"][0]
        self.assertIn("ar.name > %(after)s", q)
        self.assertIn("b.status IN %(live)s", q, "chan cu dung han khong chan quet")
        self.assertEqual(self._m._cache.d.get("esign:bridge_sweep:P"), "",
                         "it hon gioi han -> con tro ve dau")

    def test_quet_bo_goi_da_dong_va_quay_vong(self):
        reqs = [{"name": "AR-%d" % i, "reference_doctype": "X", "approval_type": "CR",
                 "reference_name": "Y", "requested_by": "lap@x"} for i in (1, 2)]
        self._m, _i = _ps(sql_rows=reqs, profiles=[{"name": "P", "business_doctype": "X",
                                                    "approval_type": "CR"}])
        self._with("tasks", _tasks_stub(_outcome_closed=lambda pkg: True))
        self._m._partner_gate = lambda pkg: (_ for _ in ()).throw(AssertionError("khong hoi"))
        self.assertEqual(self._m.sweep_partner_bridges(limit=2), [])
        self.assertEqual(self._m._cache.d.get("esign:bridge_sweep:P"), "AR-2",
                         "du gioi han -> nho con tro")

    def test_het_gio_giua_lo_nho_dung_phieu_da_xu_ly(self):
        """QC vong 2 M-1: het gio o phieu thu 2 cua lo 3 (it hon gioi han) -> con tro = phieu 1,
        KHONG ve dau (truoc day ve dau -> phieu cuoi lo khong bao gio duoc xet)."""
        reqs = [{"name": "AR-%d" % i, "reference_doctype": "X", "approval_type": "CR",
                 "reference_name": "Y", "requested_by": "lap@x"} for i in (1, 2, 3)]
        self._m, _i = _ps(sql_rows=reqs, profiles=[{"name": "P", "business_doctype": "X",
                                                    "approval_type": "CR"}])
        self._with("tasks", _tasks_stub(_outcome_closed=lambda pkg: False))
        seen = []
        clock = {"t": 0.0}
        import time as _time
        real = _time.monotonic

        def gate(pkg):
            seen.append(pkg)
            clock["t"] += 100.0                  # moi phieu "ton" 100 giay > gioi han 60
            return "waiting_partner"
        self._m._partner_gate = gate
        _time.monotonic = lambda: clock["t"]
        try:
            self._m.sweep_partner_bridges(limit=50)
        finally:
            _time.monotonic = real
        self.assertEqual(len(seen), 1, "het gio sau phieu dau")
        self.assertEqual(self._m._cache.d.get("esign:bridge_sweep:P"), "AR-1")

    def test_canh_mo(self):
        self._m, _i = _ps()
        state = {"transitions": [{"transition_id": -11}, {"transition_id": -9}]}
        tk = _tasks_stub(_settings_and_adapter=lambda d: ({}, types.SimpleNamespace(
            workflow_state_for_document=lambda doc, uid: (state, None))))
        self._with("tasks", tk)
        self.assertTrue(self._m._bridge_edge_open(REQ_ROW, "PKG-1", -11))
        state["transitions"] = [{"transition_id": -7}]
        self.assertFalse(self._m._bridge_edge_open(REQ_ROW, "PKG-1", -11))
        tk._integration_open = lambda p, e: False
        state["transitions"] = [{"transition_id": -11}]
        self.assertFalse(self._m._bridge_edge_open(REQ_ROW, "PKG-1", -11), "cong tac TAT")

    def test_noi_day(self):
        self.assertIn("portal_steps.bridge_gate_message(", _read("service.py"))
        ps = _read("portal_steps.py")
        i = ps.index("def _requester_step_rows(")
        self.assertIn('"error_code"', ps[i:ps.index("\ndef ", i + 10)],
                      "B-1 can error_code cua chan cu de quyet tao lai hay khong")
        src = _read("tasks.py")
        i = src.index("def flag_silent_legs(")
        self.assertIn("portal_steps.sweep_partner_bridges()", src[i:src.index("\ndef ", i + 10)])


# =============================================================================== 5. retrieval
class TestTaiPdf(unittest.TestCase):
    def test_hop_dong_chi_phieu_approved_dntt_giu_nguyen(self):
        calls = []
        pkgs = [_D(name="P1", provider="SCTS", environment="UAT", approval_request="AR-OK",
                   profile="HD"),
                _D(name="P2", provider="SCTS", environment="UAT", approval_request="AR-PEND",
                   profile="HD"),
                _D(name="P3", provider="SCTS", environment="UAT", approval_request="AR-REJ",
                   profile="HD"),
                _D(name="P4", provider="SCTS", environment="UAT", approval_request="AR-PEND",
                   profile="DNTT")]
        st = {"AR-OK": "Approved", "AR-PEND": "Pending", "AR-REJ": "Rejected"}
        prof = {"HD": _D(trust_portal_transitions=1, allow_external_signers=0),
                "DNTT": _D(trust_portal_transitions=0, allow_external_signers=0)}

        def gv(dt, n, f=None, **k):
            if dt == "EC Digital Signature Profile":
                return prof.get(n)
            return st.get(n)
        fk = _fk(get_all=lambda *a, **k: pkgs,
                 db=types.SimpleNamespace(exists=lambda dt, f: dt != "EVT", get_value=gv,
                                          count=lambda *a: 0))
        sf = types.ModuleType("sf")
        sf.retrieve_and_store_for_package = lambda n: calls.append(n) or {"ok": True}
        oc = types.ModuleType("oc")
        oc.sweep_unreported = lambda commit=None: 0
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.signed_files, root.outcomes = sf, oc
        mods = {"ecentric_workspace.platform.esign": root,
                "ecentric_workspace.platform.esign.signed_files": sf,
                "ecentric_workspace.platform.esign.outcomes": oc}
        g = {"frappe": fk, "DSR": "DSR", "EVT": "EVT", "_disabled": lambda: False,
             "_integration_open": lambda *a: True, "_commit_step": lambda: None,
             "_outcome_closed": lambda n: False, "_flag_stalled_retrieval": lambda *a, **k: None,
             "_handle_partner_round": lambda *a: None, "_PARTNER_REASONS": ()}
        exec(compile(_fns(_read("tasks.py"), ["_AR_CLOSED", "_contract_profile",
                                              "retrieve_signed_bundles"]), "t", "exec"), g)
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            g["retrieve_signed_bundles"]()
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        self.assertEqual(calls, ["P1", "P4"], "HD Pending bo qua; DNTT Pending nhu cu")


# =============================================================================== 6. role check
def _req_mod(prof, extra=None):
    fk = _fk()
    fk._ = lambda s: s
    fk.throw = lambda m, *a: (_ for _ in ()).throw(_Throw(m))
    ex = extra or {}

    def gv(dt, n, f=None, **k):
        if dt == "EC Digital Signature Profile":
            return prof
        if dt == "EC Digital Signature Provider Settings":
            return _D(integration_enabled=ex.get("integration", 1))
        if dt == "EC Digital Signature Package":
            return _D(name="PKG-1", profile="P", business_doctype="X", business_name="Y")
        return None
    fk.db = types.SimpleNamespace(get_value=gv)
    pm = types.SimpleNamespace(verified_mapping=lambda u, e: _D(scts_user_id="U-LAP"))
    g = {"frappe": fk, "_": fk._, "perms": pm, "PKG": "EC Digital Signature Package"}
    exec(compile(_fns(_read("requester.py"), ["PROFILE", "_portal_adapter",
                                              "_contract_profile_row",
                                              "assert_requester_portal_role",
                                              "_PARTNER_ERROR_VI", "_partner_error_vi",
                                              "assert_partner_sign_type_ready"]), "r", "exec"), g)
    return g


def _swap(mods):
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)

    def restore():
        for k, v in saved.items():
            if v is None:
                sys.modules.pop(k, None)
            else:
                sys.modules[k] = v
    return restore


def _role(prof, wf, have, names=None, integration=1, fresh_have="same"):
    calls = []

    def user_roles(u, provider_user_id=None, fresh=False):
        calls.append((u, provider_user_id, fresh))
        return have if (not fresh or fresh_have == "same") else fresh_have
    ad = types.SimpleNamespace(workflow_nodes=lambda d: wf, user_roles=user_roles,
                               role_names=lambda: dict(names or {}))
    prov = types.ModuleType("prov")
    prov.get_adapter = lambda s: ad
    g = _req_mod(prof, {"integration": integration})

    def run():
        restore = _swap({"ecentric_workspace.platform.esign.providers": prov})
        try:
            return g["assert_requester_portal_role"]("P", "lap@ecentric.vn")
        finally:
            restore()
    run.calls = calls
    return run


PROF_HD = _D(trust_portal_transitions=1, allow_external_signers=1, workflow_definition_id="WF03",
             provider="SCTS", environment="UAT")
WFR = {"nodes": {"3": {"roles": ["R-CNB", "R-KT"]}}, "start_node": "3"}
NAMES = {"R-CNB": "Chuyên viên CnB", "R-KT": "Khởi tạo hợp đồng"}


class TestVaiTro(unittest.TestCase):
    def test_co_vai_thi_qua_khong_phan_biet_hoa_thuong(self):
        self.assertIsNone(_role(PROF_HD, WFR, ["r-kt", "X"], names=NAMES)())

    def test_thieu_vai_thi_chan_va_ghi_ten_theo_ma_anh_xa(self):
        run = _role(PROF_HD, WFR, ["X"], names=NAMES)
        with self.assertRaises(_Throw) as cm:
            run()
        self.assertIn("Chuyên viên CnB", str(cm.exception))
        self.assertIn("Khởi tạo hợp đồng", str(cm.exception))
        self.assertEqual(run.calls, [("lap@ecentric.vn", "U-LAP", False),
                                     ("lap@ecentric.vn", "U-LAP", True)],
                         "tim theo ma anh xa; doc lai KHONG cache truoc khi chan")

    def test_vua_duoc_cap_vai_thi_qua(self):
        self.assertIsNone(_role(PROF_HD, WFR, ["X"], names=NAMES, fresh_have=["R-CNB"])())

    def test_ma_vai_la_hoac_khong_doc_duoc_ten_thi_khong_chan(self):
        self.assertIsNone(_role(PROF_HD, WFR, ["X"], names={"R-CNB": "CnB"})())
        self.assertIsNone(_role(PROF_HD, WFR, ["X"], names={})())

    def test_khong_doc_duoc_hoac_dntt_thi_khong_chan(self):
        self.assertIsNone(_role(PROF_HD, WFR, None, names=NAMES)())
        self.assertIsNone(_role(PROF_HD, None, ["X"], names=NAMES)())
        self.assertIsNone(_role(PROF_HD, WFR, ["X"], names=NAMES, integration=0)())
        dntt = _D(PROF_HD, trust_portal_transitions=0, allow_external_signers=0)
        self.assertIsNone(_role(dntt, WFR, ["X"], names=NAMES)())

    def test_goi_o_ca_hai_cho_gui(self):
        src = _read("requester.py")
        self.assertEqual(src.count("assert_requester_portal_role("), 3, "dinh nghia + 2 cho goi")
        self.assertEqual(src.count("assert_partner_sign_type_ready("), 3)


class TestLuotLucGui(unittest.TestCase):
    def _run(self, prof, rows=None, rows_err=None, licence_err=None):
        calls = []
        tk = types.ModuleType("tk")

        def ext(pkg):
            if rows_err:
                raise rows_err
            return rows
        tk._external_handlers_for = ext
        sg = {"ProviderError": _PE}
        exec(compile(_fns(_read("providers", "scts.py"),
                          ["PARTNER_SIGN_TYPES", "PARTNER_DEFAULT_SIGN_TYPE",
                           "_external_handlers_payload"]), "s", "exec"), sg)
        sc = types.ModuleType("sc")
        sc._external_handlers_payload = sg["_external_handlers_payload"]
        base = types.ModuleType("base")
        base.ProviderError = _PE

        def assert_av(payload):
            calls.append([h["SignType"] for h in payload])
            if licence_err:
                raise licence_err
        ad = types.SimpleNamespace(assert_partner_sign_types_available=assert_av)
        prov = types.ModuleType("prov")
        prov.get_adapter = lambda s: ad
        root = types.ModuleType("ecentric_workspace.platform.esign")
        root.tasks = tk
        g = _req_mod(prof)
        restore = _swap({"ecentric_workspace.platform.esign": root,
                         "ecentric_workspace.platform.esign.tasks": tk,
                         "ecentric_workspace.platform.esign.providers": prov,
                         "ecentric_workspace.platform.esign.providers.base": base,
                         "ecentric_workspace.platform.esign.providers.scts": sc})
        try:
            return g["assert_partner_sign_type_ready"]("PKG-1"), calls
        finally:
            restore()

    def test_dntt_khong_hoi_gi(self):
        dntt = _D(PROF_HD, trust_portal_transitions=0, allow_external_signers=0)
        self.assertEqual(self._run(dntt, rows_err=AssertionError("khong duoc goi")), (None, []))

    def test_het_luot_chan_luc_gui(self):
        err = _PE("partner_sign_type_unavailable", "Gói CMC chưa có lượt eKYC cho đối tác ký")
        with self.assertRaises(_Throw) as cm:
            self._run(PROF_HD, rows=[{"full_name": "A", "email": "a@x"}], licence_err=err)
        self.assertIn("Gói CMC chưa có lượt eKYC", str(cm.exception))

    def test_thieu_thong_tin_doi_tac_chan_luc_gui(self):
        with self.assertRaises(_Throw) as cm:
            self._run(PROF_HD, rows_err=_PE("partner_info_missing", "phieu chua co doi tac"))
        msg = str(cm.exception)
        self.assertIn("chưa có đủ thông tin người ký phía đối tác", msg)
        self.assertNotIn("phieu chua co", msg, "khong lo cau ky thuat khong dau")
        err = _PE("partner_info_missing", "x")
        err.user_message = "Hợp đồng chưa có email đối tác"
        with self.assertRaises(_Throw) as cm:
            self._run(PROF_HD, rows_err=err)
        self.assertEqual(str(cm.exception), "Hợp đồng chưa có email đối tác",
                         "cau cua nghiep vu giu nguyen")

    def test_con_luot_hoac_loi_khac_khong_chan(self):
        out, calls = self._run(PROF_HD, rows=[{"full_name": "A", "email": "a@x"}])
        self.assertEqual(calls, [["ekyc"]])
        self.assertIsNone(self._run(PROF_HD, rows=[{"full_name": "A", "email": "a@x"}],
                                    licence_err=_PE("scts_read_forbidden", "403"))[0])


if __name__ == "__main__":
    unittest.main()
