# Copyright (c) 2026, eCentric and contributors
"""Dong bo lai ERP -> nha cung cap (15/11/2026, chuyen SCTS -> CMC): provider_resync.

Chot o day:
  1. Ke hoach CHI DOC: dung chan thieu; cong nhieu chu ky hon ERP / danh tinh lech / tai lieu
     huy -> dung; 404 -> can tao lai tai lieu.
  2. Chi ban lai chan ky ERP DA TUNG GUI; buoc + nguoi nhan khop lenh goc.
  3. Truoc moi lan gui: doc lai tai lieu, vi tri chan == so chu ky, cau hinh theo vi tri, cong
     mo dung canh, anh xa + chu ky con khop. Mot dieu kien hong -> DUNG, khong gui.
  4. KHONG BAO GIO pool; khong dong trang thai duyet ERP; mot chan / lan; khoa theo goi;
     chan ERP dang bay / lan truoc chua xac minh -> dung.
  5. Xac minh: dung MOT chu ky moi cua dung nguoi.
  6. Tao lai tai lieu: token nguoi de nghi con dung, nguoi de nghi cung khong thay tai lieu,
     ma cu giu trong su kien; tao hong (chac chan) -> tra lai ma cu.
  7. Kiem token: chi doc, khong lo token. API: chi chay that khi dry_run="0".
"""
import ast
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_ROOT, "ecentric_workspace", "platform", "esign")
_SRC = os.path.join(_ESIGN, "provider_resync.py")


def _read(p):
    with io.open(p, encoding="utf-8") as fh:
        return fh.read()


class _Throw(Exception):
    pass


class _D(dict):
    __getattr__ = dict.get


class PE(Exception):
    def __init__(self, code, message="", retryable=False, ambiguous=False):
        super().__init__(message)
        self.code, self.retryable, self.ambiguous = code, retryable, ambiguous


class _State(object):
    def __init__(self, signed, status="processing"):
        self.signers = [{"email": e, "status": "signed"} for e in signed] + \
                       [{"email": "", "status": "pending"}]
        self.status = status


class _Adapter(object):
    def __init__(self, world):
        self.w = world
        self.token = None

    def use_user_token(self, tok):
        self.token = tok
        return self

    def poll_status(self, doc_id):
        if self.w.get("missing"):
            raise PE("scts_document_not_found")
        if self.w.get("late_land") and self.w["sent"] == [] and self.w.get("polls", 0) >= 1:
            self.w["signed"].append(self.w.pop("late_land"))
        self.w["polls"] = self.w.get("polls", 0) + 1
        st = _State(list(self.w["signed"]), self.w.get("doc_status", "processing"))
        st.identity = dict(self.w.get("identity") or {})
        return st

    def workflow_state_for_document(self, doc_id, uid):
        if self.w.get("state_none"):
            return None, "x"
        return {"current_state_id": "7", "transitions": [{"transition_id": t}
                                                         for t in self.w["open"]]}, None

    def eligible_recipients(self, inst, tid, uid):
        return self.w.get("eligible")

    def validate_signature_owner(self, uid, sig):
        return _D(ok=True) if self.w.get("owner_ok", True) else False

    def list_user_signatures(self, uid):
        if self.w.get("token_rejected") and self.token:
            raise PE("scts_user_token_rejected")
        out = []
        for u, (pid, sig, typ) in MAPS.items():
            if pid == uid:
                out.append({"id": sig, "type": self.w.get("provider_types", {}).get(u, typ)})
        return out

    def transition_with_recipients(self, inst, uid, to, cfg, sig, actor_user_id=None):
        self.w["sent"].append({"uid": uid, "to": list(to), "tid": cfg.get("transition_id"),
                               "sig": sig, "token": self.token,
                               "events_before": len(self.w["events"]),
                               "commits_before": self.w["commits"]})
        if self.w.get("send_fail"):
            raise PE("scts_transition_rejected_400")
        if self.w.get("apply", True):
            for e in (self.w["sign_as"].pop(0) if self.w.get("sign_as") else ["x@x"]):
                self.w["signed"].append(e)
        return {}

    def get_signed_document(self, doc_id, file_id):
        if self.w.get("pdf_fail"):
            raise PE("scts_signed_pdf_empty")
        n = int((self.w.get("pdf_sigs") or {}).get(file_id, 0))
        return {"content": b"%PDF-1.7 " + b"/ByteRange [0 1 2 3] " * n}

    def approve_and_sign(self, *a, **k):
        raise AssertionError("POOL bi goi - cam")


def _leg(name, actor_type, user, uid, sig, rl, done):
    return _D(name=name, actor_type=actor_type, actor_user=user if actor_type == "Requester"
              else None, approver=user, effective_scts_user_id=uid, effective_signature_id=sig,
              request_level=rl, approval_request="AR-1", completed_at=done, provider="SCTS",
              environment="UAT", package="PKG-1", action="Sign", status="Approval Completed")


LEGS = [_leg("DSR-R", "Requester", "huong@x", "U-H", "S-H", None, "1"),
        _leg("DSR-1", "Approval Level", "tuan@x", "U-T", "S-T", "RL-1", "2"),
        _leg("DSR-2", "Approval Level", "lien@x", "U-L", "S-L", "RL-2", "3"),
        _leg("DSR-3", "Approval Level", "phuong@x", "U-P", "S-P", "RL-3", "4")]
LEVEL_OF = {"RL-1": 1, "RL-2": 2, "RL-3": 3, "RL-4": 4}
MAPS = {"huong@x": ("U-H", "S-H", "ky-tham-gia"), "tuan@x": ("U-T", "S-T", "ky-tham-gia"),
        "lien@x": ("U-L", "S-L", "ky-tham-gia"), "phuong@x": ("U-P", "S-P", "ky-tham-gia"),
        "lam@x": ("U-CEO", "S-CEO", "ky-chinh")}
CFG = {0: -2, 1: -9, 2: -10, 3: -11, 4: -4}


def _orig(tid=None, to=None, signer=None, pool_after=False, accepted=True):
    meta = {}
    if tid is not None:
        meta["transition_id"] = tid
    if to is not None:
        meta["to_users"] = to
    if signer is not None:
        meta["signer_user_id"] = signer
    rows = []
    if pool_after:
        rows.append(_D(event_type="HandoverPoolFallback", request_meta=None, creation="t3"))
    if accepted:
        rows.append(_D(event_type="ProviderAccepted", request_meta=None, creation="t2"))
    rows.append(_D(event_type="HandoverTargeted", request_meta=json.dumps(meta), creation="t1"))
    return rows


def _load(world):
    for k, v in (("sent", []), ("events", []), ("writes", []), ("commits", 0),
                 ("cache", {})):
        world.setdefault(k, v)
    world.setdefault("orig", {l.name: _orig() for l in LEGS})
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.throw = lambda m, *a, **k: (_ for _ in ()).throw(_Throw(m))
    fk.session = types.SimpleNamespace(user="sm@x")
    fk._dict = _D
    fk.parse_json = lambda s: json.loads(s) if isinstance(s, str) else s
    import datetime as _dt
    fu = types.ModuleType("frappe.utils")
    NOW = _dt.datetime(2026, 11, 15, 12, 0, 0)
    fu.now_datetime = lambda: NOW
    fu.get_datetime = lambda v: v if isinstance(v, _dt.datetime) else NOW - _dt.timedelta(
        minutes=int(world.get("prior_age_min", 5)))
    fu.add_to_date = lambda d, minutes=0, **k: d + _dt.timedelta(minutes=minutes)
    fk.utils = fu

    class Cache(object):
        def set(self, key, val, nx=False, ex=None):
            if world.get("cache_down"):
                raise RuntimeError("down")
            if nx and key in world["cache"]:
                return False
            world["cache"][key] = val
            return True

        def delete(self, key):
            world["cache"].pop(key, None)
    fk.cache = lambda: Cache()

    def get_value(dt, name, fields=None, **k):
        if dt == "EC Digital Signature Provider Settings":
            return _D(provider="SCTS", environment="UAT", base_url="https://api-signx.cmc.vn",
                      allow_document_creation=0 if world.get("gated") else 1)
        if dt == "EC Digital Signature Package":
            if isinstance(name, dict) or fields == "name":
                return "PKG-1"
            if fields == "doc_code_sent":
                return world.get("doc_code_sent")
            if fields == "signed_bundle_complete":
                return "BUNDLE-WAS"
            if fields == "error_code":
                return world.get("err_code")
            if isinstance(fields, list) and "scts_workflow_instance_id" in fields \
                    and "profile" not in fields:
                return _D(scts_document_id=world.get("doc", "DOC-1"),
                          scts_workflow_instance_id="INST-OLD")
            return _D(name="PKG-1", status="Active", profile="P", provider="SCTS",
                      environment="UAT", scts_document_id=world.get("doc", "DOC-1"),
                      approval_request="AR-1", business_doctype="EC Payment Request",
                      business_name="PR-1")
        if dt == "EC Approval Request Level":
            return LEVEL_OF.get(name)
        if dt == "EC Approval Request":
            return world.get("approval_status", "Approved")
        if dt == "EC Digital Signature Request":
            return _D([l for l in LEGS if l.name == name][0])
        return None

    def get_all(dt, filters=None, fields=None, **k):
        f = filters or {}
        if dt == "EC Digital Signature Request":
            if f.get("status") == "Approval Completed":
                return [_D(l) for l in world.get("legs", LEGS)]
            return [_D(x) for x in world.get("live", [])]
        if dt == "EC Digital Signature File":
            return [_D(x) for x in world.get("dsf", [])]
        if dt == "EC Digital Signature Placement":
            return [_D(x) for x in world.get("placements", [])]
        if dt == "EC Approval Request Approver":
            return [_D(x) for x in world.get("next", []) if x["level_no"] == f["level_no"]]
        if dt == "EC SCTS User Mapping":
            return [_D(frappe_user=u, scts_user_id=MAPS[u][0]) for u in world.get("tokens", {})]
        if dt == "EC Digital Signature Event":
            if f.get("package") and not f.get("signature_request"):
                return [_D(request_meta=json.dumps({"source": "provider_resync_recreate",
                                                    "old_document_id": x}))
                        for x in world.get("prior_recreate", [])]
            leg = f.get("signature_request")
            emitted = [(i, et, k) for i, (et, k, _n) in enumerate(world["events"])
                       if k.get("signature_request") == leg]
            if f.get("event_type") == "ResendExecuted":
                mine = [_D(name="EV-%d" % i, creation="%06d" % (1000 + i))
                        for i, et, k in emitted if et == "ResendExecuted"
                        and (k.get("request_meta") or {}).get("source") == "provider_resync"]
                seeded = [_D(x) for x in world.get("prior", {}).get(leg, [])]
                return sorted(mine + seeded, key=lambda x: x.creation, reverse=True)[:1]
            if f.get("event_type") == "PollTick":
                like = f["verification_result"][1].rstrip("%")
                since = f["creation"][1]
                hits = [_D(name="EV-%d" % i) for i, et, k in emitted if et == "PollTick"
                        and str(k.get("verification_result") or "").startswith(like)
                        and "%06d" % (1000 + i) >= since]
                return hits + [_D(x) for x in world.get("prior_ok", {}).get(leg, [])]
            return world["orig"].get(leg, [])
        return []

    def set_value(*a, **k):
        world["writes"].append(a)

    def commit():
        world["commits"] += 1
    fk.db = types.SimpleNamespace(get_value=get_value, set_value=set_value, commit=commit)
    fk.get_all = get_all

    class _File(object):
        def __init__(self, name):
            self.name = name

        def get_content(self):
            if world.get("source_fail"):
                raise IOError("missing")
            return b"%PDF " + b"/ByteRange " * int((world.get("source_sigs") or {}).get(
                self.name, 0))
    fk.get_doc = lambda dt, name: _File(name)

    ev = types.ModuleType("ecentric_workspace.platform.esign.events")
    ev.emit = lambda et, **k: world["events"].append((et, k, len(world["sent"])))
    nh = types.ModuleType("ecentric_workspace.platform.esign.next_handler")
    nh.provider_step_index = lambda ad, doc: (
        (None, "khong dem duoc") if world.get("step_none") else (len(world["signed"]), None))

    def rtc(profile, action, stage=None, step_index=None):
        if world.get("cfg_none"):
            return None
        if world.get("cfg_default"):
            return {"transition_id": -9, "sign_type": "ky-tham-gia", "terminal": False}
        return {"transition_id": CFG[step_index], "step_index": step_index,
                "sign_type": "ky-chinh" if step_index == 4 else "ky-tham-gia",
                "process_action": "WfX", "terminal": step_index == 4}
    nh.resolve_transition_config = rtc
    nh.signature_type_matches = lambda want, have: (not want) or want == have
    nh.provider_ids_for = lambda users, env: (
        [MAPS[u][0] for u in users if u in MAPS], [u for u in users if u not in MAPS])
    nh.requester_actor = lambda leg, s, stage: None
    pm = types.ModuleType("ecentric_workspace.platform.esign.permissions")

    def vm(user, env):
        if user in world.get("map_changed", ()):
            return _D(scts_user_id="OTHER", signature_id="OTHER", signature_type="ky-tham-gia")
        m = MAPS.get(user)
        if not m:
            return None
        # Prod 15/11: anh xa KHONG ghi loai chu ky (signature_type rong) - mac dinh nhu prod.
        return _D(scts_user_id=m[0], signature_id=m[1],
                  signature_type=m[2] if world.get("map_has_type") else None)
    pm.verified_mapping = vm
    pv = types.ModuleType("ecentric_workspace.platform.esign.providers")
    pv.get_adapter = lambda s: _Adapter(world)
    pb = types.ModuleType("ecentric_workspace.platform.esign.providers.base")
    pb.ProviderError = PE
    sa = types.ModuleType("ecentric_workspace.platform.esign.sanitize")
    sa.safe_error = lambda e: str(e)
    svc = types.ModuleType("ecentric_workspace.platform.esign.service")
    svc._emails_cua_cung_danh_tinh = lambda leg: (
        ["huong@x", "cnb@x"] if (leg.get("actor_user") or leg.get("approver")) == "huong@x"
        else [leg.get("actor_user") or leg.get("approver")])
    pk = types.ModuleType("ecentric_workspace.platform.esign.package")
    pk.workflow_instance_id = lambda name: None
    pk.package_files = lambda n: [_D(name="F1", scts_document_file_id="OLDF")]
    pk.package_placements = lambda n: [1]
    ul = types.ModuleType("ecentric_workspace.platform.esign.user_link")
    ul.needs_own_token = lambda user, s: user != "hoan@x"
    # 16/11 (CMC): nguoi duyet cung ky bang token rieng. Mac dinh moi nguoi duyet CO token
    # ("T-<email>"); nguoi de nghi chi co khi test cho. no_approver_tokens -> khong ai co.
    ul.token_for = lambda user, env: world.get("tokens", {}).get(user, None if (
        user == "huong@x" or world.get("no_approver_tokens")) else "T-" + str(user))

    def stn(leg, s):
        if leg.get("actor_type") == "Requester":
            u = leg.get("actor_user")
        elif (leg.get("action") or "Sign") == "Sign":
            u = leg.get("approver")
        else:
            return None
        return u if (u and ul.needs_own_token(u, s)) else None
    ul.signer_token_needed = stn
    ul.default_context = lambda: (_D(provider="SCTS", environment="UAT",
                                     base_url="https://api-signx.cmc.vn"), "UAT")
    tk = types.ModuleType("ecentric_workspace.platform.esign.tasks")

    def ensure(dsr, settings, adapter):
        if world.get("create_fail"):
            raise PE("scts_create_rejected_400", ambiguous=world.get("create_ambiguous", False))
        world["created"] = {"by_token": adapter.token, "dsr": dsr.get("name"),
                            "commits": world["commits"]}
        world["doc"] = "DOC-NEW"
        world.pop("missing", None)
        world["signed"] = []
        return "DOC-NEW"
    tk._ensure_provider_document = ensure
    tm = types.ModuleType("time")
    tm.sleep = lambda s: None
    root = types.ModuleType("ecentric_workspace.platform.esign")
    for n, m in (("events", ev), ("next_handler", nh), ("permissions", pm), ("service", svc),
                 ("package", pk), ("user_link", ul), ("tasks", tk)):
        setattr(root, n, m)
    mods = {"frappe": fk, "frappe.utils": fu, "ecentric_workspace.platform.esign": root,
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.next_handler": nh,
            "ecentric_workspace.platform.esign.permissions": pm,
            "ecentric_workspace.platform.esign.providers": pv,
            "ecentric_workspace.platform.esign.providers.base": pb,
            "ecentric_workspace.platform.esign.sanitize": sa,
            "ecentric_workspace.platform.esign.service": svc,
            "ecentric_workspace.platform.esign.package": pk,
            "ecentric_workspace.platform.esign.user_link": ul,
            "ecentric_workspace.platform.esign.tasks": tk, "time": tm}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    mod = types.ModuleType("_resync")
    exec(compile(_read(_SRC), "provider_resync.py", "exec"), mod.__dict__)
    mod._restore = lambda: [sys.modules.pop(k, None) if v is None
                            else sys.modules.__setitem__(k, v) for k, v in saved.items()]
    return mod


def _world(**kw):
    w = {"signed": ["huong@x", "tuan@x", "lien@x"], "open": [-11, -12],
         "next": [{"level_no": 4, "approver": "lam@x", "status": "Pending"}],
         "sign_as": [["phuong@x"]]}
    w.update(kw)
    return w


R = "dong bo CMC thieu chieu 13/11"


class Base(unittest.TestCase):
    def mk(self, **kw):
        w = _world(**kw)
        m = _load(w)
        self.addCleanup(m._restore)
        return m, w

    def run1(self, m, dry=False, **kw):
        return m.replay("EC Payment Request", "PR-1", R, dry_run=dry, **kw)


class TestKeHoach(Base):
    def test_thieu_mot_chan(self):
        m, w = self.mk()
        p = m.plan("EC Payment Request", "PR-1")
        self.assertEqual([x["signature_request"] for x in p["missing"]], ["DSR-3"])
        self.assertEqual(p["missing"][0]["level_no"], 3)

    def test_du_roi(self):
        m, w = self.mk(signed=["huong@x", "tuan@x", "lien@x", "phuong@x"])
        self.assertTrue(m.plan("EC Payment Request", "PR-1")["in_sync"])

    def test_du_so_luong_nhung_sai_nguoi_khong_phai_in_sync(self):
        m, w = self.mk(signed=["huong@x", "tuan@x", "lien@x", "khac@x"])
        p = m.plan("EC Payment Request", "PR-1")
        self.assertFalse(p["ok"])

    def test_cong_nhieu_hon_erp_thi_dung(self):
        m, w = self.mk(signed=["huong@x", "tuan@x", "lien@x", "phuong@x", "lam@x"])
        self.assertEqual(m.plan("EC Payment Request", "PR-1")["reason"], "provider_ahead_of_erp")

    def test_danh_tinh_lech_thi_dung(self):
        m, w = self.mk(signed=["huong@x", "lien@x", "khac@x"])
        self.assertTrue(m.plan("EC Payment Request", "PR-1")["reason"]
                        .startswith("identity_mismatch"))

    def test_mot_nguoi_ky_hai_o_dem_dung(self):
        legs = [LEGS[0], _leg("DSR-X", "Approval Level", "huong@x", "U-H", "S-H", "RL-1", "2"),
                LEGS[2]]
        m, w = self.mk(legs=legs, signed=["huong@x", "khac@x"])
        self.assertFalse(m.plan("EC Payment Request", "PR-1")["ok"],
                         "huong ky 2 o nhung cong chi co 1 cua huong + 1 nguoi la")

    def test_tai_khoan_dung_chung(self):
        m, w = self.mk(signed=["cnb@x", "tuan@x", "lien@x"])
        self.assertTrue(m.plan("EC Payment Request", "PR-1")["ok"])

    def test_tai_lieu_huy_thi_dung(self):
        m, w = self.mk(doc_status="cancelled")
        self.assertEqual(m.plan("EC Payment Request", "PR-1")["reason"],
                         "provider_document_cancelled")

    def test_mat_tai_lieu(self):
        m, w = self.mk(missing=True)
        p = m.plan("EC Payment Request", "PR-1")
        self.assertTrue(p["document_missing"])
        self.assertEqual(len(p["missing"]), 4)

    def test_ke_hoach_khong_gui_khong_ghi(self):
        m, w = self.mk()
        m.plan("EC Payment Request", "PR-1")
        self.assertEqual((w["sent"], w["writes"], w["events"], w["commits"]), ([], [], [], 0))


class TestChotGui(Base):
    def _stop(self, **kw):
        m, w = self.mk(**kw)
        r = self.run1(m, dry=True)
        self.assertEqual(w["sent"], [])
        return r["results"][0] if r.get("results") else r

    def test_chay_thu_dung_lenh(self):
        r = self._stop()
        self.assertEqual(r["result"], "would_send")
        self.assertEqual((r["transition_id"], r["step_index"], r["to_users"]),
                         (-11, 3, ["U-CEO"]))

    def test_chan_nhan_ve_tu_cong_khong_ban(self):
        self.assertEqual(self._stop(orig={"DSR-3": []})["reason"], "leg_not_sent_by_erp")

    def test_khac_lenh_goc(self):
        r = self._stop(orig={"DSR-3": _orig(tid=-10)})
        self.assertTrue(r["reason"].startswith("differs_from_original"))

    def test_nguoi_nhan_khac_lenh_goc(self):
        r = self._stop(orig={"DSR-3": _orig(tid=-11, to=["U-KHAC"])})
        self.assertEqual(r["reason"], "recipients_differ_from_original")

    def test_lenh_goc_roi_ve_pool(self):
        self.assertEqual(self._stop(orig={"DSR-3": _orig(pool_after=True)})["reason"],
                         "original_was_pool")

    def test_lenh_goc_khong_duoc_nhan(self):
        self.assertEqual(self._stop(orig={"DSR-3": _orig(accepted=False)})["reason"],
                         "leg_not_sent_by_erp")

    def test_nguoi_ky_khac_lenh_goc(self):
        self.assertEqual(self._stop(orig={"DSR-3": _orig(signer="U-KHAC")})["reason"],
                         "signer_differs_from_original")

    def test_lenh_goc_khop(self):
        self.assertEqual(self._stop(orig={"DSR-3": _orig(tid=-11, to=["U-CEO"])})["result"],
                         "would_send")

    def test_lan_truoc_chua_xac_minh(self):
        r = self._stop(prior={"DSR-3": [{"name": "EV-9", "creation": "t9"}]})
        self.assertEqual(r["reason"], "prior_resync_unverified:EV-9")

    def test_lan_truoc_da_xac_minh_thi_cho(self):
        r = self._stop(prior={"DSR-3": [{"name": "EV-9", "creation": "t9"}]},
                       prior_ok={"DSR-3": [{"name": "EV-10"}]})
        self.assertEqual(r["result"], "would_send")

    def test_loai_chu_ky_doc_tu_cong_khi_anh_xa_trong(self):
        self.assertEqual(self._stop()["result"], "would_send")
        r = self._stop(provider_types={"phuong@x": "ky-chinh"})
        self.assertEqual(r["reason"], "signature_type_mismatch:ky-tham-gia/ky-chinh")

    def test_khong_biet_loai_chu_ky_thi_dung(self):
        self.assertEqual(self._stop(provider_types={"phuong@x": None})["reason"],
                         "signature_type_unknown")

    def test_anh_xa_co_loai_thi_dung_loai_anh_xa(self):
        self.assertEqual(self._stop(map_has_type=True,
                                    provider_types={"phuong@x": "ky-chinh"})["result"],
                         "would_send")

    def test_anh_xa_doi(self):
        self.assertEqual(self._stop(map_changed={"phuong@x"})["reason"],
                         "mapping_changed_since_signing")

    def test_khong_dem_duoc_buoc(self):
        self.assertTrue(self._stop(step_none=True)["reason"].startswith("step_unknown"))

    def test_khong_co_cau_hinh_buoc(self):
        self.assertTrue(self._stop(cfg_none=True)["reason"].startswith("no_step_config"))

    def test_dong_mac_dinh_khong_co_vi_tri_thi_dung(self):
        self.assertTrue(self._stop(cfg_default=True)["reason"].startswith("no_step_config"))

    def test_cong_khong_mo_canh_do(self):
        self.assertTrue(self._stop(open=[-10])["reason"].startswith("portal_disagrees"))

    def test_khong_doc_duoc_cong(self):
        self.assertTrue(self._stop(state_none=True)["reason"].startswith("portal_state"))

    def test_nguoi_nhan_chua_anh_xa(self):
        r = self._stop(next=[{"level_no": 4, "approver": "ai@x", "status": "Pending"}])
        self.assertTrue(r["reason"].startswith("next_handler_unmapped"))

    def test_nguoi_nhan_khong_hop_le(self):
        self.assertEqual(self._stop(eligible={"U-KHAC"})["reason"], "no_eligible_recipient")

    def test_chu_ky_khong_con_hieu_luc(self):
        self.assertTrue(self._stop(owner_ok=False)["reason"].startswith("signature_owner"))

    def test_chan_ceo_manual_review_khong_chan_ban_lai_cap_3(self):
        """16/11: CEO bam Duyet & Ky khi CMC con thieu chu ky KTT -> chan CEO Manual Review.
        Chan KTT (cap 3) van ban lai duoc; chan CEO gui lai sau qua "Gui lai co kiem"."""
        r = self._stop(live=[{"name": "DSR-CEO", "status": "Manual Review",
                              "actor_type": "Approval Level", "request_level": "RL-4"}])
        self.assertEqual(r["result"], "would_send")

    def test_manual_review_cung_cap_thi_dung(self):
        r = self._stop(live=[{"name": "DSR-X", "status": "Manual Review",
                              "actor_type": "Approval Level", "request_level": "RL-3"}])
        self.assertTrue(r["reason"].startswith("live_legs"))

    def test_chan_cap_sau_dang_bay_van_dung(self):
        r = self._stop(live=[{"name": "DSR-CEO", "status": "Queued",
                              "actor_type": "Approval Level", "request_level": "RL-4"}])
        self.assertTrue(r["reason"].startswith("live_legs"))

    def test_chan_dang_bay_thi_dung(self):
        r = self._stop(live=[{"name": "DSR-CEO", "status": "Queued"}])
        self.assertTrue(r["reason"].startswith("live_legs"))

    def test_dang_co_nguoi_khac_dong_bo(self):
        m, w = self.mk(cache={"esign:provider_resync:PKG-1": "1"})
        with self.assertRaises(_Throw):
            self.run1(m, dry=True)

    def test_khong_khoa_duoc_thi_khong_chay(self):
        m, w = self.mk(cache_down=True)
        with self.assertRaises(_Throw):
            self.run1(m, dry=True)

    def test_uu_tien_nguoi_da_duyet_cap_sau(self):
        m, w = self.mk(signed=["huong@x", "tuan@x"], open=[-10],
                       next=[{"level_no": 3, "approver": "phuong@x", "status": "Approved"},
                             {"level_no": 3, "approver": "lien@x", "status": "Skipped"}])
        self.assertEqual(self.run1(m, dry=True)["results"][0]["to_users"], ["U-P"])

    def test_bat_buoc_ly_do(self):
        m, w = self.mk()
        with self.assertRaises(_Throw):
            m.replay("EC Payment Request", "PR-1", "ngan", dry_run=True)

    def test_khoa_duoc_tra_sau_khi_chay(self):
        m, w = self.mk()
        self.run1(m, dry=True)
        self.assertEqual(w["cache"], {})


class TestGuiThat(Base):
    def test_gui_dung_chu_ky_cua_chan_va_xac_minh(self):
        m, w = self.mk()
        r = self.run1(m)
        self.assertEqual(r["results"][0]["result"], "verified")
        s = w["sent"][0]
        self.assertEqual((s["uid"], s["sig"], s["tid"], s["to"]), ("U-P", "S-P", -11, ["U-CEO"]))
        self.assertEqual(s["token"], "T-phuong@x",
                         "chan duyet: token cua CHINH nguoi duyet (16/11 CMC khong nhung chu ky "
                         "khi tai khoan tich hop ky thay)")
        first = [e for e in w["events"] if e[0] == "ResendExecuted"][0]
        self.assertEqual(first[2], 0, "vet ghi TRUOC khi gui")
        self.assertGreaterEqual(s["commits_before"], 1, "vet da COMMIT truoc khi gui")
        self.assertEqual(first[1]["request_meta"]["source"], "provider_resync")
        self.assertEqual(w["writes"], [], "khong dong vao trang thai ERP")
        self.assertEqual(r["remaining"], 0)

    def test_nguoi_duyet_khong_co_token_thi_dung_khong_ky_thay(self):
        m, w = self.mk(no_approver_tokens=True)
        r = self.run1(m)
        self.assertEqual(r["results"][0]["result"], "stop")
        self.assertEqual(r["results"][0]["reason"], "signer_token_missing:phuong@x")
        self.assertEqual(w["sent"], [])

    def test_tai_khoan_tich_hop_tu_ky_dung_token_tich_hop(self):
        m, w = self.mk(no_approver_tokens=True)
        leg = _leg("DSR-3", "Approval Level", "hoan@x", "U-X", "S-X", "RL-3", "4")
        ad, why = m._user_token_adapter(leg, {"environment": "UAT"})
        self.assertIsNone(why)
        self.assertIsNone(ad.token, "tai khoan tich hop tu ky: khong doi token")
        ad2, why2 = m._user_token_adapter(dict(LEGS[2], action="Approve"), {"environment": "UAT"})
        self.assertIsNone(ad2.token, "buoc duyet KHONG ky giu tai khoan tich hop")

    def test_mot_chan_moi_lan_goi(self):
        m, w = self.mk(signed=["huong@x", "tuan@x"], open=[-10, -11],
                       sign_as=[["lien@x"], ["phuong@x"]],
                       next=[{"level_no": 3, "approver": "phuong@x", "status": "Approved"},
                             {"level_no": 4, "approver": "lam@x", "status": "Pending"}])
        r1 = self.run1(m)
        self.assertEqual((len(w["sent"]), r1["remaining"]), (1, 1))
        r2 = self.run1(m)
        self.assertEqual([s["tid"] for s in w["sent"]], [-10, -11])
        self.assertEqual([s["to"] for s in w["sent"]], [["U-P"], ["U-CEO"]])
        self.assertEqual(r2["results"][0]["result"], "verified")

    def test_chu_ky_den_tre_giua_ke_hoach_va_gui_thi_dung(self):
        """QC 15/11: ke hoach thay [huong,tuan]; chu ky cua lien (lan truoc) len NGAY truoc khi
        gui -> khong duoc gui chan lien vao o -11."""
        m, w = self.mk(signed=["huong@x", "tuan@x"], open=[-10, -11], late_land="lien@x",
                       next=[{"level_no": 3, "approver": "phuong@x", "status": "Approved"}])
        r = self.run1(m)
        self.assertEqual(w["sent"], [])
        self.assertTrue(r["results"][0]["reason"].startswith("position_mismatch"))

    def test_khong_thay_chu_ky_thi_unverified(self):
        m, w = self.mk(apply=False)
        self.assertEqual(self.run1(m)["results"][0]["result"], "unverified")

    def test_chu_ky_moi_sai_nguoi(self):
        m, w = self.mk(sign_as=[["khac@x"]])
        r = self.run1(m)
        self.assertEqual(r["results"][0]["reason"], "resync_unverified:wrong_signer")

    def test_them_hai_chu_ky_la_bat_thuong(self):
        m, w = self.mk(sign_as=[["phuong@x", "lam@x"]])
        r = self.run1(m)
        self.assertTrue(r["results"][0]["reason"].startswith("resync_unverified:extra"))

    def test_gui_loi_thi_dung(self):
        m, w = self.mk(send_fail=True)
        self.assertEqual(self.run1(m)["results"][0]["result"], "send_failed")

    def test_lan_sau_bi_chan_neu_lan_truoc_chua_xac_minh(self):
        m, w = self.mk(apply=False)
        self.run1(m)
        w["prior"] = {"DSR-3": [{"name": "EV-1", "creation": "t"}]}
        r = self.run1(m)
        self.assertTrue(r["results"][0]["reason"].startswith("prior_resync_unverified"))
        self.assertEqual(len(w["sent"]), 1)
        r = self.run1(m, ack_prior_attempt=True)
        self.assertTrue(r["results"][0]["reason"].startswith("prior_too_recent"),
                        "xac nhan qua som (lenh truoc co the van dang chay)")
        w["prior_age_min"] = 45
        r = self.run1(m, ack_prior_attempt=True)
        self.assertEqual(len(w["sent"]), 2, "du lau + co xac nhan da xem cong thi cho gui lai")

    def test_tu_choi_chac_chan_khong_can_xac_nhan(self):
        m, w = self.mk(send_fail=True)
        self.run1(m)
        w.pop("send_fail")
        self.run1(m)
        self.assertEqual(len(w["sent"]), 2, "4xx = khong gui gi -> lan sau khong can xac nhan")

    def test_chan_dang_bay_xuat_hien_ngay_truoc_khi_gui(self):
        m, w = self.mk()
        orig_live = w.get("live")
        class Flip(list):
            n = 0
            def __iter__(self_):
                Flip.n += 1
                return iter([{"name": "DSR-CEO", "status": "Queued"}] if Flip.n > 1 else [])
            def __bool__(self_):
                return Flip.n >= 1
        w["live"] = Flip()
        r = self.run1(m)
        self.assertEqual(w["sent"], [])

    def test_mat_tai_lieu_khong_ban_lai(self):
        m, w = self.mk(missing=True)
        r = self.run1(m)
        self.assertFalse(r["ok"])
        self.assertEqual(w["sent"], [])

    def test_khong_bao_gio_pool(self):
        for n in ast.walk(ast.parse(_read(_SRC))):
            if isinstance(n, ast.Attribute):
                self.assertNotIn(n.attr, ("approve_and_sign", "plan_handover", "bulk_process"))


class TestTaoLai(Base):
    def kw(self, **extra):
        k = dict(missing=True, tokens={"huong@x": "T-H"}, signed=[], open=[-2],
                 legs=[LEGS[0], LEGS[1]], sign_as=[["huong@x"]],
                 next=[{"level_no": 1, "approver": "tuan@x", "status": "Pending"}])
        k.update(extra)
        return k

    def pkg_writes(self, w):
        return [a[2] for a in w["writes"] if a[0] == "EC Digital Signature Package"]

    def test_chay_thu(self):
        m, w = self.mk(**self.kw())
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=True)
        self.assertEqual(r["would_create"]["as_requester"], "huong@x")
        self.assertNotIn("created", w)
        self.assertEqual((w["sent"], w["writes"], w["commits"]), ([], [], 0))

    def test_chay_thu_bao_khi_cam_tao(self):
        m, w = self.mk(**self.kw(gated=True))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=True)
        self.assertEqual(r["reason"], "document_creation_gated")

    def test_dang_cho_doi_soat_tao(self):
        m, w = self.mk(**self.kw(err_code="create_outcome_unknown"))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=True)
        self.assertTrue(r["reason"].startswith("create_outcome_unknown"))

    def test_thieu_token(self):
        m, w = self.mk(**self.kw(tokens={}))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertTrue(r["reason"].startswith("requester_token_missing"))
        self.assertEqual(w["writes"], [])

    def test_token_bi_tu_choi(self):
        m, w = self.mk(**self.kw(token_rejected=True))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertEqual(r["reason"], "requester_token:scts_user_token_rejected")
        self.assertEqual(w["writes"], [])

    def test_chan_nguoi_de_nghi_khong_do_erp_gui(self):
        m, w = self.mk(**self.kw(orig={"DSR-R": []}))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertEqual(r["reason"], "leg_not_sent_by_erp")

    def test_tai_lieu_con_thi_khong_tao(self):
        m, w = self.mk(**self.kw(missing=False))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertFalse(r["ok"])
        self.assertNotIn("created", w)

    def test_hai_pha_moc_cho_doi_soat_truoc(self):
        m, w = self.mk(**self.kw())
        m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        pw = self.pkg_writes(w)
        self.assertEqual(pw[0]["error_code"], "create_outcome_unknown")
        self.assertIsNone(pw[0]["scts_document_id"])
        self.assertEqual(pw[1], {"error_code": None, "error_message": None})
        self.assertGreaterEqual(w["created"]["commits"], 1, "pha 1 da commit truoc khi tao")

    def test_tao_hong_chac_chan_thi_tra_nhu_cu(self):
        m, w = self.mk(**self.kw(create_fail=True))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertFalse(r["ok"])
        self.assertEqual(self.pkg_writes(w)[-1], {"scts_document_id": "DOC-1",
                                                  "scts_workflow_instance_id": "INST-OLD",
                                                  "error_code": None, "error_message": None})

    def test_tao_mo_ho_thi_giu_moc(self):
        m, w = self.mk(**self.kw(create_fail=True, create_ambiguous=True))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertTrue(r["ambiguous"])
        self.assertEqual(len(self.pkg_writes(w)), 2, "khong tra ma cu; doi soat")

    def test_tao_lai_lan_hai_sau_khi_doi_soat_mo_ho(self):
        """16/11 00675: CMC tra 500 cho AddDocument -> mo ho; SM doi soat xong (go moc) -> goi
        khong con ma tai lieu. Tao lai lan hai phai duoc, lay ma cu tu su kien truoc."""
        m, w = self.mk(**self.kw(doc=None, prior_recreate=["DOC-1"]))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertTrue(r["ok"], r)
        self.assertEqual(r["new_document_id"], "DOC-NEW")
        ev = [e for e in w["events"] if (e[1].get("request_meta") or {}).get("old_document_id")]
        self.assertEqual(ev[0][1]["request_meta"]["old_document_id"], "DOC-1")

    def test_tao_lai_lan_hai_khi_con_moc_mo_ho_thi_khong(self):
        m, w = self.mk(**self.kw(doc=None, prior_recreate=["DOC-1"],
                                 err_code="create_outcome_unknown"))
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertFalse(r["ok"])
        self.assertNotIn("created", w)

    def test_tao_lai_khong_ky_trong_cung_request_roi_ban_lai_tung_chan(self):
        m, w = self.mk(**self.kw())
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertEqual(w["created"], {"by_token": "T-H", "dsr": "DSR-R",
                                        "commits": w["created"]["commits"]})
        self.assertEqual((r["old_document_id"], r["new_document_id"]), ("DOC-1", "DOC-NEW"))
        self.assertEqual(w["sent"], [], "lenh ky o lan goi sau")
        ev = [e for e in w["events"] if (e[1].get("request_meta") or {}).get("old_document_id")]
        self.assertIsNone(ev[0][1].get("signature_request"), "su kien cap goi")
        self.assertEqual(ev[0][1]["request_meta"]["old_file_ids"], {"F1": "OLDF"})
        r1 = self.run1(m)
        self.assertEqual(r1["results"][0]["result"], "verified",
                         "su kien tao lai KHONG chan lan ban lai dau (QC 15/11)")
        s0 = w["sent"][0]
        self.assertEqual((s0["tid"], s0["token"], s0["to"]), (-2, "T-H", ["U-T"]))
        w["open"] = [-9]
        w["sign_as"] = [["tuan@x"]]
        w["next"] = [{"level_no": 2, "approver": "lien@x", "status": "Pending"}]
        self.run1(m)
        self.assertEqual(w["sent"][1]["token"], "T-tuan@x",
                         "chan duyet: token cua CHINH nguoi duyet (16/11 CMC)")


class TestThayTaiLieuNham(Base):
    """16/11 00675: goi trong ma tai lieu, cap 1 bam duyet -> worker tao tai lieu bang TAI KHOAN
    TICH HOP. eContract giao buoc nguoi de nghi cho tai khoan tao -> chu ky nguoi de nghi khong
    vao duoc (400). replace_foreign: tao ban moi bang token nguoi de nghi khi ban cu 0 chu ky
    va do nguoi khac tao."""
    MR_L1 = {"name": "DSR-1B", "status": "Manual Review", "actor_type": "Approval Level",
             "request_level": "RL-1"}

    def kw(self, **extra):
        k = dict(missing=False, tokens={"huong@x": "T-H"}, signed=[], open=[-2],
                 legs=[LEGS[0]], sign_as=[["huong@x"]], live=[dict(self.MR_L1)],
                 identity={"creator_email": "Hoan@X", "doc_code": "PR-1"},
                 next=[{"level_no": 1, "approver": "tuan@x", "status": "Pending"}])
        k.update(extra)
        return k

    def go(self, m, dry=False):
        return m.recreate_document("EC Payment Request", "PR-1", R, dry_run=dry,
                                   replace_foreign=True)

    def test_khong_bat_co_thi_nhu_cu(self):
        m, w = self.mk(**self.kw())
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertEqual(r["reason"], "document_not_missing")
        self.assertNotIn("created", w)

    def test_chay_thu_khong_ghi(self):
        m, w = self.mk(**self.kw())
        r = self.go(m, dry=True)
        self.assertTrue(r.get("dry_run"), r)
        self.assertEqual(r["foreign_creator"], "hoan@x")
        self.assertEqual((w["writes"], w["commits"]), ([], 0))

    def test_thay_bang_token_nguoi_de_nghi_mr_cap_sau_khong_chan(self):
        m, w = self.mk(**self.kw())
        r = self.go(m)
        self.assertTrue(r["ok"], r)
        self.assertEqual(w["created"]["by_token"], "T-H")
        self.assertEqual((r["old_document_id"], r["new_document_id"]), ("DOC-1", "DOC-NEW"))
        ev = [e for e in w["events"] if (e[1].get("request_meta") or {}).get("old_document_id")]
        self.assertEqual(ev[0][1]["request_meta"]["replaced_foreign_creator"], "hoan@x")
        self.assertEqual(w["sent"], [])

    def test_co_chu_ky_thi_khong(self):
        m, w = self.mk(**self.kw(signed=["huong@x"]))
        self.assertEqual(self.go(m)["reason"], "foreign_doc_has_signatures")
        self.assertNotIn("created", w)

    def test_nguoi_de_nghi_tao_thi_khong(self):
        for who in ("huong@x", "CNB@x"):
            m, w = self.mk(**self.kw(identity={"creator_email": who, "doc_code": "PR-1"}))
            self.assertEqual(self.go(m)["reason"], "foreign_doc_created_by_requester", who)
            self.assertNotIn("created", w)

    def test_khong_biet_nguoi_tao_thi_khong(self):
        m, w = self.mk(**self.kw(identity={"doc_code": "PR-1"}))
        self.assertEqual(self.go(m)["reason"], "foreign_doc_creator_unknown")

    def test_ma_chung_tu_lech_thi_khong(self):
        m, w = self.mk(**self.kw(identity={"creator_email": "hoan@x", "doc_code": "PR-9"}))
        self.assertEqual(self.go(m)["reason"], "foreign_doc_code_mismatch")
        m, w = self.mk(**self.kw(doc_code_sent="EC-X-1",
                                 identity={"creator_email": "hoan@x", "doc_code": "EC-X-1"}))
        self.assertTrue(self.go(m)["ok"], "doc_code_sent uu tien hon ten phieu")

    def test_tai_lieu_huy_hoac_xong_thi_khong(self):
        for st in ("cancelled", "completed"):
            m, w = self.mk(**self.kw(doc_status=st))
            self.assertFalse(self.go(m)["ok"], st)
            self.assertNotIn("created", w)

    def test_chan_dang_bay_van_chan(self):
        live = dict(self.MR_L1, status="Queued")
        m, w = self.mk(**self.kw(live=[live]))
        self.assertTrue(self.go(m)["reason"].startswith("live_legs"))

    def test_404_thi_phai_dung_duong_thuong(self):
        m, w = self.mk(**self.kw(missing=True))
        self.assertEqual(self.go(m)["reason"], "replace_foreign_needs_existing_doc")


class TestDungLaiPdfThieuChuKy(Base):
    """16/11 CMC: tai khoan tich hop ky thay -> cong ghi 'Da ky' nhung PDF thieu chu ky so.
    rebuild_unembedded: tao ban moi bang token nguoi de nghi, moi chan ky lai bang token rieng."""
    def kw(self, **extra):
        k = dict(missing=False, tokens={"huong@x": "T-H"}, signed=["huong@x", "tuan@x"],
                 open=[-2], legs=[LEGS[0], LEGS[1]], sign_as=[["huong@x"]], live=[],
                 pdf_sigs={"OLDF": 1},
                 placements=[{"signature_file": "F1", "status": "Placed", "level_no": 0},
                             {"signature_file": "F1", "status": "Placed", "level_no": 1},
                             {"signature_file": "F1", "status": "Placed", "level_no": 2}],
                 dsf=[{"name": "F1", "file": "SRC-1", "file_name": "a.pdf",
                       "scts_document_file_id": "OLDF",
                       "signed_file": "FILE-OLD", "signed_file_sha256": "abc",
                       "provider_status": "Signed"}],
                 next=[{"level_no": 1, "approver": "tuan@x", "status": "Approved"},
                       {"level_no": 2, "approver": "lien@x", "status": "Approved"}])
        k.update(extra)
        return k

    def go(self, m, dry=False, **kw):
        return m.recreate_document("EC Payment Request", "PR-1", R, dry_run=dry,
                                   rebuild_unembedded=True, **kw)

    def writes(self, w, dt):
        return [a for a in w["writes"] if a[0] == dt]

    def test_chay_thu(self):
        m, w = self.mk(**self.kw())
        r = self.go(m, dry=True)
        self.assertTrue(r.get("dry_run"), r)
        self.assertEqual(r["unembedded"], [{"file": "F1", "pdf_signatures": 1, "placements": 2,
                                            "source_signatures": 0}],
                         "cap 2 chua ky tren ERP -> khong tinh")
        self.assertEqual((w["writes"], w["commits"]), ([], 0))

    def test_pdf_du_chu_ky_thi_khong(self):
        m, w = self.mk(**self.kw(pdf_sigs={"OLDF": 2}))
        self.assertEqual(self.go(m)["reason"], "pdf_signatures_complete")
        self.assertNotIn("created", w)

    def test_chua_dong_bo_thi_ban_lai_truoc(self):
        m, w = self.mk(**self.kw(signed=["huong@x"]))
        self.assertEqual(self.go(m)["reason"], "rebuild_needs_in_sync")

    def test_thieu_token_bat_ky_chan_nao_thi_dung_tu_dau(self):
        m, w = self.mk(**self.kw(no_approver_tokens=True))
        r = self.go(m)
        self.assertEqual(r["reason"], "tokens_missing:signer_token_missing:tuan@x")
        self.assertEqual(w["writes"], [])

    def test_khong_doc_duoc_pdf_thi_dung(self):
        m, w = self.mk(**self.kw(pdf_fail=True))
        self.assertEqual(self.go(m)["reason"], "pdf_read:scts_signed_pdf_empty")

    def test_hai_che_do_cung_luc_thi_khong(self):
        m, w = self.mk(**self.kw())
        self.assertEqual(self.go(m, replace_foreign=True)["reason"], "one_mode_only")

    def test_chay_that_go_con_tro_pdf_cu_va_ma_tep_cu(self):
        m, w = self.mk(**self.kw())
        r = self.go(m)
        self.assertTrue(r["ok"], r)
        self.assertEqual(w["created"]["by_token"], "T-H")
        dsf = self.writes(w, "EC Digital Signature File")
        self.assertEqual(dsf[0][1], "F1")
        self.assertIsNone(dsf[0][2]["scts_document_file_id"])
        for k in ("signed_file", "signed_file_sha256", "provider_status", "signed_retrieved_at",
                  "signed_review_candidate", "signed_review_sha256"):
            self.assertIn(k, dsf[0][2])
            self.assertIsNone(dsf[0][2][k])
        pk = [a[2] for a in self.writes(w, "EC Digital Signature Package")]
        self.assertIn("signed_bundle_complete", pk)
        ev = [e for e in w["events"] if (e[1].get("request_meta") or {}).get("old_document_id")]
        meta = ev[0][1]["request_meta"]
        self.assertEqual(meta["old_signed_files"]["F1"]["signed_file"], "FILE-OLD")
        self.assertEqual(meta["rebuild_unembedded"][0]["pdf_signatures"], 1)

    def test_tao_hong_chac_chan_thi_tra_lai_ca_con_tro_pdf(self):
        m, w = self.mk(**self.kw(create_fail=True))
        r = self.go(m)
        self.assertFalse(r["ok"])
        dsf = self.writes(w, "EC Digital Signature File")
        last = dsf[-1][2]
        self.assertEqual((last["scts_document_file_id"], last["signed_file"],
                          last["signed_file_sha256"], last["provider_status"]),
                         ("OLDF", "FILE-OLD", "abc", "Signed"))
        pk = self.writes(w, "EC Digital Signature Package")
        self.assertIn(("EC Digital Signature Package", "PKG-1", "signed_bundle_complete",
                       "BUNDLE-WAS"), pk, "tra lai DUNG gia tri cu, khong ep 1")

    def test_phieu_chua_duyet_xong_thi_khong(self):
        m, w = self.mk(**self.kw(approval_status="Pending"))
        self.assertEqual(self.go(m)["reason"], "rebuild_needs_approved_request")

    def test_tep_goc_co_san_chu_ky_thi_tru(self):
        # PDF 2 /ByteRange nhung 1 cai co san tu tep goc -> that ra chi 1 chu ky / can 2
        m, w = self.mk(**self.kw(pdf_sigs={"OLDF": 2}, source_sigs={"SRC-1": 1}))
        r = self.go(m, dry=True)
        self.assertEqual(r["unembedded"][0]["pdf_signatures"], 1)
        self.assertEqual(r["unembedded"][0]["source_signatures"], 1)
        m, w = self.mk(**self.kw(pdf_sigs={"OLDF": 2}, source_sigs={"SRC-1": 0}))
        self.assertEqual(self.go(m, dry=True)["reason"], "pdf_signatures_complete")

    def test_khong_doc_duoc_tep_goc_thi_dung(self):
        m, w = self.mk(**self.kw(source_fail=True))
        self.assertEqual(self.go(m)["reason"], "source_unreadable:F1")

    def test_chan_sau_khong_ban_lai_duoc_thi_dung_truoc_khi_tao(self):
        # chan cap 1 khong do ERP gui (vd nhan ve tu cong) -> dung NGAY, khong tao
        m, w = self.mk(**self.kw(orig={"DSR-R": _orig(), "DSR-1": []}))
        r = self.go(m)
        self.assertEqual(r["reason"], "leg_not_replayable:DSR-1:leg_not_sent_by_erp")
        self.assertEqual(w["writes"], [])
        m, w = self.mk(**self.kw(map_changed={"tuan@x"}))
        self.assertTrue(self.go(m, dry=True)["reason"].startswith(
            "leg_not_replayable:DSR-1:mapping_changed"))


class TestKhongDeTrongMaTaiLieu(Base):
    def test_tao_hong_khi_goi_da_trong_ma_thi_tra_ma_cu_tu_su_kien(self):
        """03:57 16/11 00675: lan tao lai thu hai bi CMC chan (het han muc) - goi bi de TRONG ma
        -> 09:22 cap 1 bam duyet, worker tao tai lieu bang tai khoan tich hop. Phai tra ma cu."""
        m, w = self.mk(missing=True, tokens={"huong@x": "T-H"}, signed=[], open=[-2],
                       legs=[LEGS[0]], doc=None, prior_recreate=["DOC-1"], create_fail=True,
                       next=[{"level_no": 1, "approver": "tuan@x", "status": "Pending"}])
        r = m.recreate_document("EC Payment Request", "PR-1", R, dry_run=False)
        self.assertFalse(r["ok"])
        last = [a[2] for a in w["writes"] if a[0] == "EC Digital Signature Package"][-1]
        self.assertEqual(last["scts_document_id"], "DOC-1")
        self.assertIsNone(last["error_code"])


class TestKiemTokenVaApi(Base):
    def test_ok_tu_choi_het_han(self):
        m, w = self.mk(tokens={"huong@x": "T-H", "tuan@x": None})
        r = m.probe_user_tokens()
        self.assertEqual({x["user"]: x["result"] for x in r["rows"]},
                         {"huong@x": "ok", "tuan@x": "expired_or_missing"})
        self.assertNotIn("T-H", repr(r), "khong lo token")
        m2, w2 = self.mk(tokens={"huong@x": "T-H"}, token_rejected=True)
        self.assertEqual(m2.probe_user_tokens()["rejected"], 1)

    def test_api(self):
        src = _read(os.path.join(_ESIGN, "api.py"))
        tree = ast.parse(src)
        fns = {n.name: n for n in tree.body if isinstance(n, ast.FunctionDef)
               and (n.name.startswith("resync_") or n.name == "_live_flag")}
        self.assertEqual(set(fns), {"resync_probe_user_tokens", "resync_plan", "resync_replay",
                                    "resync_recreate_document", "_live_flag"})
        for name, n in fns.items():
            if name != "_live_flag":
                self.assertIn("perms.assert_system_manager()", ast.get_source_segment(src, n))
        for name in ("resync_replay", "resync_recreate_document"):
            decos = [ast.get_source_segment(src, d) for d in fns[name].decorator_list]
            self.assertTrue(any('methods=["POST"]' in d for d in decos), name)
        g = {}
        exec(compile(ast.get_source_segment(src, fns["_live_flag"]), "f", "exec"), g)
        for v, dry in (("0", False), (0, False), (" 0 ", False), ("", True), (None, True),
                       ("1", True), ("2", True), ("abc", True)):
            self.assertEqual(g["_live_flag"](v), dry, repr(v))


if __name__ == "__main__":
    unittest.main()
