# Copyright (c) 2026, eCentric and contributors
"""Phieu ERP bi TU CHOI / HUY -> huy tai lieu tren cong CMC (18/11/2026).

  1. scts_client.cancel_document: dung payload cua cong; MOT lan goi; 2xx success=false / 4xx =
     tu choi chac chan; mang / 5xx = mo ho; 401/403 = loi xac thuc.
  2. scts adapter: destroy -> identity.destroyed (KHONG doi status chung).
  3. provider_cancel.cancel_one: chi Payment Request Rejected / Cancelled; chan dang bay -> cho;
     khoa chung + bo snapshot; doc lai truoc (danh sach CHO PHEP: chi "dang xu ly"); vet + commit
     TRUOC khi gui; MOT lenh (tai khoan tich hop); doc lai co cho; da nhan ma chua huy -> khong
     gui lai, danh dau cho xac minh + ToDo; 404 khong coi la da huy.
  4. sweep: tu len co sau mot lan huy SM xac minh (Production); kill switch; toi da
     MAX_AUTO_TRIES lenh, MAX_POLL_FAILS loi doc tam thoi; ly do ben vung ghi mot lan.
  5. candidates: chi phieu ket thuc (completed_at) tu AUTO_SINCE (tru lenh SM).
  6. hooks + api.
"""
import datetime
import importlib.util
import io
import json
import os
import sys
import types
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
_ESIGN = os.path.join(_APP, "ecentric_workspace", "platform", "esign")


def _read(*p):
    with io.open(os.path.join(_ESIGN, *p), encoding="utf-8") as fh:
        return fh.read()


class PE(Exception):
    def __init__(self, code, message="", retryable=False, ambiguous=False):
        super().__init__(message)
        self.code, self.message, self.retryable, self.ambiguous = code, message, retryable, ambiguous


class _D(dict):
    __getattr__ = dict.get


# --------------------------------------------------------------------------- 1. client
class _Resp(object):
    def __init__(self, status, body):
        self.status_code = status
        self._b = body
        self.text = body if isinstance(body, str) else json.dumps(body)

    def json(self):
        if isinstance(self._b, str):
            raise ValueError("x")
        return self._b


class TestClient(unittest.TestCase):
    def _call(self, status=200, body=None, boom=False):
        spec = importlib.util.spec_from_file_location(
            "_scts_client_cancel", os.path.join(_ESIGN, "providers", "scts_client.py"))
        m = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(m)
        calls = []

        def transport(method, url, headers=None, json_body=None, timeout=None, verify_tls=True):
            calls.append((method, url, json_body, headers))
            if boom:
                raise IOError("net")
            return _Resp(status, body if body is not None else {"success": True})
        c = m.SctsClient("https://x.example", transport=transport, sleeper=lambda s: None)
        try:
            return c.cancel_document("DOC-1", "ly do", "tok"), calls
        except Exception as e:
            return e, calls

    def test_payload_dung_cua_cong(self):
        r, calls = self._call()
        self.assertEqual(r, {"success": True})
        meth, url, body, hdr = calls[0]
        self.assertEqual((meth, url), ("POST", "https://x.example/api/Document/cancel-file-pdf"))
        self.assertEqual(body, {"documentId": "DOC-1", "emails": [], "emailTemplateId": None,
                                "reason": "ly do"})
        self.assertEqual(hdr["Authorization"], "Bearer tok")

    def test_success_false_la_tu_choi(self):
        e, calls = self._call(200, {"success": False, "message": "Khong co quyen"})
        self.assertEqual(e.code, "scts_cancel_rejected")
        self.assertFalse(e.ambiguous)
        self.assertEqual(len(calls), 1)

    def test_4xx_tu_choi_5xx_mang_mo_ho_401_xac_thuc(self):
        e, _c = self._call(400, {"title": "bad"})
        self.assertEqual((e.code, e.ambiguous), ("scts_cancel_rejected_400", False))
        for st in (500, 502):
            e, calls = self._call(st, "x")
            self.assertEqual((e.code, e.ambiguous), ("scts_cancel_outcome_unknown", True))
            self.assertEqual(len(calls), 1, "KHONG thu lai lenh huy")
        e, calls = self._call(boom=True)
        self.assertEqual((e.code, e.ambiguous), ("scts_cancel_outcome_unknown", True))
        self.assertEqual(len(calls), 1)
        e, _c = self._call(401, "x")
        self.assertEqual(e.code, "scts_auth_error_401")


class TestAdapterSource(unittest.TestCase):
    def test_destroy_va_co_cancel_document(self):
        src = _read("providers", "scts.py")
        self.assertIn('raw.get("destroy")', src)
        self.assertIn("def cancel_document(self, document_id, reason):", src)


# --------------------------------------------------------------------------- 3-5. provider_cancel
NOW = datetime.datetime(2026, 11, 18, 12, 0, 0)


class _State(object):
    def __init__(self, status="Đang xử lý", signed=1, total=5, creator="anh@x"):
        self.status = status
        self.signers = [{"status": "signed"}] * signed + [{"status": "pending"}] * (total - signed)
        self.identity = {"creator_email": creator}


class _Adapter(object):
    def __init__(self, w, token=None):
        self.w, self.token = w, token

    def use_user_token(self, tok):
        return _Adapter(self.w, tok)

    def poll_status(self, doc):
        self.w["polls"].append(self.token)
        if self.w.get("missing"):
            raise PE("scts_document_not_found")
        if self.w.get("poll_fail"):
            raise PE("scts_network_error")
        if self.w.get("cancelled"):
            st = _State(self.w.get("status", "Đang xử lý"))
            st.identity["destroyed"] = True        # CMC: destroy=1, chu co the chua doi
            return st
        return _State(self.w.get("status", "Đang xử lý"), self.w.get("signed", 1),
                      self.w.get("total", 5))

    def cancel_document(self, doc, reason):
        self.w["cancels"].append({"token": self.token, "reason": reason,
                                  "commits_before": self.w["commits"],
                                  "events_before": len(self.w["events"]),
                                  "locked": dict(self.w["cache"])})
        if self.w.get("on_cancel"):
            self.w["on_cancel"]()
        fail = self.w.get("cancel_fail")
        if fail:
            raise fail
        if self.w.get("apply", True):
            self.w["cancelled"] = True
        return {"success": True}


def _load(w):
    for k, v in (("polls", []), ("cancels", []), ("events", []), ("writes", []), ("commits", 0),
                 ("rollbacks", 0), ("cache", {}), ("todos", [])):
        w.setdefault(k, v)
    fk = types.ModuleType("frappe")
    fk._ = lambda s: s
    fk.session = types.SimpleNamespace(user="Administrator")
    fk.log_error = lambda *a, **k: w.setdefault("errors", []).append(a)
    fk.get_traceback = lambda: ""
    fk.conf = w.get("conf", {})

    def throw(msg, *a, **k):
        raise RuntimeError(msg)
    fk.throw = throw

    class Cache(object):
        def set(self, key, val, nx=False, ex=None):
            if nx and key in w["cache"]:
                return False
            w["cache"][key] = val
            return True

        def delete(self, key):
            w["cache"].pop(key, None)
    fk.cache = lambda: Cache()

    def get_value(dt, name, fields=None, **k):
        if dt == "EC Digital Signature Package":
            p = dict(name=name, status=w.get("pkg_status", "Active"), provider="SCTS",
                     environment="Production", scts_document_id=w.get("doc", "DOC-1"),
                     approval_request="AR-1", business_doctype=w.get("bdt", "EC Payment Request"),
                     business_name="PR-1", error_code=w.get("err"),
                     signed_bundle_complete=w.get("sbc", 0))
            if w.get("err_after_lock") and w["cache"] and w["rollbacks"]:
                p["error_code"] = w["err_after_lock"]   # chi thay sau khi BO snapshot
            return _D(p)
        if dt == "EC Approval Request":
            return _D(name=name, approval_status=w.get("ar", "Rejected"),
                      completed_at="2026-11-18 09:00:00")
        if dt == "EC Digital Signature Provider Settings":
            return _D(provider="SCTS", environment="Production", username="hoan@x",
                      integration_enabled=0 if w.get("closed") else 1)
        return None

    def get_all(dt, filters=None, fields=None, **k):
        f = filters or {}
        if dt == "EC Digital Signature Request":
            return [_D(x) for x in w.get("live", [])]
        if dt == "EC Approval Request":
            w.setdefault("ar_filters", []).append(f)
            return [_D(name=x) for x in w.get("neg_ars", ["AR-1"])]
        if dt == "EC Digital Signature Package":
            w.setdefault("pkg_filters", []).append(f)
            return [_D(x) for x in w.get("pkgs", [{"name": "PKG-1", "business_name": "PR-1"}])]
        if dt == "EC Digital Signature Event":
            if isinstance(f, list):                      # auto_armed
                w.setdefault("arm_filters", []).append(f)
                return [_D(name="E")] if w.get("armed", True) else []
            vr = f.get("verification_result")
            if vr == ["like", "cancel_skip:%"]:
                return [_D(name="S")] if w.get("skipped") else []
            if vr == ["like", "cancel_poll_failed:%"]:
                n = int(w.get("poll_fails", 0)) + len([e for e in w["events"] if str(
                    e[1].get("verification_result", "")).startswith("cancel_poll_failed")])
                first = w.get("first_fail", NOW)
                return [_D(creation=first)] * n
            if vr == "cancel_sent" and fields == ["name"]:            # _prior_sent
                return [_D(name="P")] if w.get("prior_sent") else []
            return [_D(creation=x) for x in w.get("tries", [])]
        return []

    def set_value(*a, **k):
        w["writes"].append(a)

    def commit():
        w["commits"] += 1

    def rollback():
        w["rollbacks"] += 1
    fk.db = types.SimpleNamespace(get_value=get_value, set_value=set_value, commit=commit,
                                  rollback=rollback,
                                  exists=lambda dt, f=None, **k: bool(w["todos"]))
    fk.get_all = get_all

    class _Todo(object):
        def __init__(self, d):
            self.d = d

        def insert(self, **k):
            w["todos"].append(self.d)
            return self
    fk.get_doc = lambda d: _Todo(d)
    fu = types.ModuleType("frappe.utils")
    fu.now_datetime = lambda: NOW
    fu.get_datetime = lambda v: v
    fu.add_to_date = lambda d, minutes=0, hours=0, **k: d + datetime.timedelta(minutes=minutes,
                                                                                hours=hours)
    ev = types.ModuleType("ev")
    ev.emit = lambda et, **k: w["events"].append((et, k))
    pv = types.ModuleType("pv")
    pv.get_adapter = lambda s: _Adapter(w)
    pb = types.ModuleType("pb")
    pb.ProviderError = PE
    sa = types.ModuleType("sa")
    sa.safe_error = lambda e: getattr(e, "code", str(e))
    tk = types.ModuleType("tk")
    tk._disabled = lambda: bool(w.get("disabled"))
    root = types.ModuleType("ecentric_workspace.platform.esign")
    root.tasks, root.events = tk, ev
    mods = {"frappe": fk, "frappe.utils": fu, "ecentric_workspace.platform.esign": root,
            "ecentric_workspace.platform.esign.events": ev,
            "ecentric_workspace.platform.esign.providers": pv,
            "ecentric_workspace.platform.esign.providers.base": pb,
            "ecentric_workspace.platform.esign.sanitize": sa,
            "ecentric_workspace.platform.esign.tasks": tk}
    saved = {k: sys.modules.get(k) for k in mods}
    sys.modules.update(mods)
    m = types.ModuleType("_provider_cancel")
    exec(compile(_read("provider_cancel.py"), "provider_cancel.py", "exec"), m.__dict__)
    m.time = types.SimpleNamespace(sleep=lambda s: w.setdefault("sleeps", []).append(s),
                                   time=lambda: 0)
    m._restore = lambda: [sys.modules.pop(k, None) if v is None else
                          sys.modules.__setitem__(k, v) for k, v in saved.items()]
    return m


class Base(unittest.TestCase):
    def mk(self, **w):
        m = _load(w)
        self.addCleanup(m._restore)
        return m, w

    def marks(self, w):
        return [a for a in w["writes"] if a[0] == "EC Digital Signature Package"]


class TestCanon(Base):
    def test_danh_sach_cho_phep(self):
        m, w = self.mk()
        import unicodedata
        for s, want in (("Đang xử lý", "processing"), ("dang xu ly", "processing"),
                        (unicodedata.normalize("NFD", "Đang xử lý"), "processing"),
                        ("Đã hủy", "cancelled"), ("Đã huỷ", "cancelled"), ("cancelled", "cancelled"),
                        ("Đã kết thúc", "completed"), ("Hoàn thành", "completed"),
                        ("completed", "completed"), ("Từ chối", "rejected"),
                        ("3", "unknown"), (None, "unknown"), ("Chờ ký", "unknown")):
            self.assertEqual(m._canon(s), want, s)


class TestCancelOne(Base):
    def test_phieu_khong_bi_tu_choi_thi_khong(self):
        for st in ("Pending", "Approved", "Information Required", None):
            m, w = self.mk(ar=st)
            r = m.cancel_one("PKG-1", dry_run=False)
            self.assertEqual(r["result"], "stop", st)
            self.assertEqual((w["cancels"], w["writes"], w["polls"]), ([], [], []))

    def test_chi_payment_request(self):
        m, w = self.mk(bdt="EC Contract Review Request")
        self.assertTrue(m.cancel_one("PKG-1", dry_run=False)["reason"].startswith(
            "doctype_not_enabled"))
        self.assertEqual(w["polls"], [])

    def test_goi_khong_active_hoac_da_luu_pdf_ky_hoac_da_danh_dau(self):
        for kw, why in (({"pkg_status": "Completed"}, "package_status"),
                        ({"sbc": 1}, "signed_bundle_complete"),
                        ({"err": "provider_document_cancelled"}, "already_marked")):
            m, w = self.mk(**kw)
            self.assertTrue(m.cancel_one("PKG-1", dry_run=False)["reason"].startswith(why), kw)
            self.assertEqual(w["polls"], [])

    def test_chan_dang_bay_thi_cho(self):
        for st in ("Queued", "Provider Accepted", "Verifying", "Retryable Failure", "Signed"):
            m, w = self.mk(live=[{"name": "DSR-9", "status": st}])
            self.assertTrue(m.cancel_one("PKG-1", dry_run=False)["reason"].startswith(
                "live_legs"), st)
            self.assertEqual((w["polls"], w["cancels"]), ([], []))

    def test_cong_tich_hop_dong_thi_khong(self):
        m, w = self.mk(closed=True)
        self.assertEqual(m.cancel_one("PKG-1", dry_run=False)["reason"], "integration_closed")
        self.assertEqual(w["polls"], [])

    def test_khong_dang_xu_ly_thi_khong_bao_gio_huy(self):
        for st in ("Đã kết thúc", "completed", "Từ chối", "3", "Chờ gì đó"):
            m, w = self.mk(status=st)
            r = m.cancel_one("PKG-1", dry_run=False)
            self.assertTrue(r["reason"].startswith("provider_status:"), st)
            self.assertEqual((w["cancels"], w["writes"]), ([], []))

    def test_khong_co_dong_ky_thi_khong_huy(self):
        m, w = self.mk(signed=0, total=0)
        self.assertEqual(m.cancel_one("PKG-1", dry_run=False)["reason"], "no_signers")
        self.assertEqual(w["cancels"], [])

    def test_moi_nguoi_da_ky_thi_khong_huy(self):
        m, w = self.mk(signed=5, total=5)
        self.assertEqual(m.cancel_one("PKG-1", dry_run=False)["reason"], "all_signers_signed")
        self.assertEqual(w["cancels"], [])

    def test_404_khong_coi_la_da_huy(self):
        m, w = self.mk(missing=True)
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(r["reason"], "poll_failed:scts_document_not_found")
        self.assertFalse(r["transient"])
        self.assertEqual((w["writes"], w["cancels"]), ([], []))
        m, w = self.mk(poll_fail=True)
        self.assertTrue(m.cancel_one("PKG-1", dry_run=False)["transient"])

    def test_da_huy_tren_cong_thi_chi_danh_dau(self):
        m, w = self.mk(cancelled=True)
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual((r["result"], r["reason"]), ("marked", "cancelled_on_portal"))
        self.assertEqual(w["cancels"], [])
        self.assertEqual(self.marks(w)[0][2]["error_code"], "provider_document_cancelled_by_erp")
        m, w = self.mk(cancelled=True, prior_sent=True)
        self.assertEqual(m.cancel_one("PKG-1", dry_run=False)["reason"],
                         "cancelled_after_prior_send", "khong do cho nguoi tren cong")

    def test_chay_thu_khong_ghi_khong_khoa(self):
        m, w = self.mk()
        r = m.cancel_one("PKG-1", dry_run=True)
        self.assertEqual(r["result"], "would_cancel")
        self.assertEqual((w["cancels"], w["writes"], w["events"], w["commits"], w["cache"]),
                         ([], [], [], 0, {}))

    def test_huy_trong_khoa_chung_vet_truoc_roi_danh_dau(self):
        m, w = self.mk()
        r = m.cancel_one("PKG-1", dry_run=False, source="auto_cancel")
        self.assertEqual(r["result"], "cancelled")
        c = w["cancels"][0]
        self.assertIsNone(c["token"], "tai khoan tich hop")
        self.assertIn("esign:provider_resync:PKG-1", c["locked"], "khoa CHUNG voi provider_resync")
        self.assertGreaterEqual(c["commits_before"], 1)
        self.assertEqual(w["events"][0][1]["verification_result"], "cancel_sent")
        self.assertIn("PR-1", c["reason"])
        mk = self.marks(w)
        self.assertEqual(len(mk), 1)
        self.assertEqual(mk[0][2]["error_code"], "provider_document_cancelled_by_erp")
        self.assertEqual(w["events"][-1][0], "Cancelled")
        self.assertEqual(w["events"][-1][1]["verification_result"],
                         "provider_document_cancelled_by_erp:cancelled")
        self.assertEqual(w["cache"], {}, "nha khoa")

    def test_trong_khoa_bo_snapshot_roi_doc_lai_goi(self):
        m, w = self.mk(err_after_lock="provider_document_cancel_unverified")
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertTrue(r["reason"].startswith("already_marked"), r)
        self.assertEqual(w["cancels"], [])
        self.assertEqual(w["rollbacks"], 1)

    def test_doc_lai_co_cho(self):
        m, w = self.mk(apply=False)
        m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(w["sleeps"], [2, 3, 5, 8])

    def test_mark_ghi_environment_de_len_co(self):
        m, w = self.mk()
        m.cancel_one("PKG-1", dry_run=False, source="sm_cancel")
        meta = w["events"][-1][1]["request_meta"]
        self.assertEqual((meta["environment"], meta["source"], meta["detail"]),
                         ("Production", "sm_cancel", "acked"))

    def test_bi_tu_choi_khong_dung_token_nguoi_khac_khong_cho(self):
        m, w = self.mk(apply=False, cancel_fail=PE("scts_cancel_rejected", "no perm"))
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual((r["result"], r["reason"]), ("failed", "scts_cancel_rejected"))
        self.assertEqual([c["token"] for c in w["cancels"]], [None])
        self.assertEqual(self.marks(w), [])
        self.assertEqual(w.get("sleeps", []), [], "tu choi chac chan: doc lai mot lan, khong cho")

    def test_adapter_khong_co_lenh_huy(self):
        m, w = self.mk()
        orig = _Adapter.cancel_document
        del _Adapter.cancel_document
        self.addCleanup(setattr, _Adapter, "cancel_document", orig)
        self.assertEqual(m.cancel_one("PKG-1", dry_run=False)["reason"], "adapter_no_cancel")
        self.assertEqual(w["events"], [], "khong ghi cancel_sent")

    def test_cong_da_nhan_ma_chua_huy_thi_khong_gui_lai(self):
        m, w = self.mk(apply=False)
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(r["result"], "unverified")
        self.assertEqual(self.marks(w)[0][2]["error_code"], "provider_document_cancel_unverified")
        self.assertEqual(len(w["todos"]), 1)
        # luot sau: goi da danh dau provider_document_ -> candidates bo, cancel_one dung
        m2, w2 = self.mk(err="provider_document_cancel_unverified")
        self.assertTrue(m2.cancel_one("PKG-1", dry_run=False)["reason"].startswith("already_marked"))
        self.assertEqual(w2["cancels"], [])

    def test_mo_ho_doc_lai_thay_huy_thi_danh_dau_nhan_khac(self):
        def amb():
            w["cancelled"] = True
        m, w = self.mk(on_cancel=None)
        w["on_cancel"] = amb
        w["cancel_fail"] = PE("scts_cancel_outcome_unknown", ambiguous=True)
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(r["result"], "cancelled")
        self.assertEqual(w["events"][-1][1]["verification_result"],
                         "provider_document_cancelled_by_erp:cancelled_read_back",
                         "KHONG len co tu dong khi cong chua nhan lenh")

    def test_mo_ho_chua_huy_thi_failed_khong_danh_dau(self):
        m, w = self.mk(apply=False, cancel_fail=PE("scts_cancel_outcome_unknown",
                                                   ambiguous=True))
        r = m.cancel_one("PKG-1", dry_run=False)
        self.assertEqual(r["result"], "failed")
        self.assertEqual(self.marks(w), [])
        self.assertTrue(w["events"][-1][1]["request_meta"]["ambiguous"])

    def test_dang_khoa_thi_khong(self):
        m, w = self.mk(cache={"esign:provider_resync:PKG-1": "1"})
        self.assertEqual(m.cancel_one("PKG-1", dry_run=False)["reason"], "locked")
        self.assertEqual((w["cancels"], w["polls"]), ([], []))


class TestSweep(Base):
    def test_kill_switch_va_chua_len_co(self):
        for kw in ({"disabled": True}, {"armed": False},
                   {"conf": {"ec_esign_auto_cancel_disabled": 1}}):
            m, w = self.mk(**kw)
            m.sweep()
            self.assertEqual((w["polls"], w["cancels"]), ([], []), kw)

    def test_huy_phieu_moi(self):
        m, w = self.mk()
        m.sweep()
        self.assertEqual(len(w["cancels"]), 1)
        self.assertEqual(w["ar_filters"][0]["completed_at"], [">=", m.AUTO_SINCE],
                         "cron loc theo completed_at (khong phai modified)")
        self.assertEqual(w["ar_filters"][0]["reference_doctype"], ["in", ["EC Payment Request"]])
        self.assertEqual(w["pkg_filters"][0]["business_doctype"], ["in", ["EC Payment Request"]])

    def test_toi_da_lenh_gui_va_khoang_cach(self):
        m, w = self.mk(tries=[NOW - datetime.timedelta(hours=h) for h in range(1, 4)])
        m.sweep()
        self.assertEqual(w["polls"], [], "da gui du MAX_AUTO_TRIES lenh")
        self.assertEqual(len(w["todos"]), 1, "het luot -> bao ops")
        self.assertTrue(w["events"][0][1]["verification_result"].startswith(
            "cancel_skip:retries_exhausted"), "ghi mot lan -> cac luot sau bo qua (khong bao lai)")
        m, w = self.mk(tries=[NOW - datetime.timedelta(minutes=5)])
        m.sweep()
        self.assertEqual(w["polls"], [])
        m, w = self.mk(tries=[NOW - datetime.timedelta(minutes=45)])
        m.sweep()
        self.assertEqual(len(w["cancels"]), 1)

    def test_ly_do_ben_vung_ghi_mot_lan_va_bo_qua_sau_do(self):
        m, w = self.mk(status="Chờ gì đó")
        m.sweep()
        ticks = [e for e in w["events"] if e[0] == "PollTick"]
        self.assertTrue(ticks[0][1]["verification_result"].startswith("cancel_skip:provider_status"))
        self.assertEqual(len(w["todos"]), 1, "trang thai la -> bao ops")
        m, w = self.mk(skipped=True)
        m.sweep()
        self.assertEqual(w["polls"], [])

    def test_da_xong_tren_cong_bo_qua_khong_bao(self):
        m, w = self.mk(status="Đã kết thúc")
        m.sweep()
        self.assertEqual(w["todos"], [])

    def test_loi_mang_tam_thoi_dung_ca_luot_co_tran_theo_tuoi(self):
        m, w = self.mk(poll_fail=True, pkgs=[{"name": "P1", "business_name": "A"},
                                             {"name": "P2", "business_name": "B"}])
        m.sweep()
        ticks = [e[1]["verification_result"] for e in w["events"] if e[0] == "PollTick"]
        self.assertEqual(ticks, ["cancel_poll_failed:poll_failed:scts_network_error"],
                         "cong loi: dung ca luot, khong tinh loi cho goi thu hai")
        self.assertEqual(w["todos"], [])
        # du so lan nhung loi dau tien moi 1 gio -> chua bo
        m, w = self.mk(poll_fail=True, poll_fails=8, first_fail=NOW - datetime.timedelta(hours=1))
        m.sweep()
        self.assertEqual(w["todos"], [])
        # du so lan va loi dau tien > 24h -> bo + bao ops
        m, w = self.mk(poll_fail=True, poll_fails=8, first_fail=NOW - datetime.timedelta(hours=30))
        m.sweep()
        ticks = [e[1]["verification_result"] for e in w["events"] if e[0] == "PollTick"]
        self.assertTrue(ticks[-1].startswith("cancel_skip:poll_failed_repeatedly"))
        self.assertEqual(len(w["todos"]), 1)

    def test_loi_le_van_giu_error_log(self):
        m, w = self.mk()
        def boom(*a, **k):
            raise RuntimeError("x")
        m.cancel_one = boom
        m.sweep()
        self.assertEqual(w["rollbacks"], 1)
        self.assertGreaterEqual(w["commits"], 1, "commit sau log_error")
        self.assertTrue(w["errors"])

    def test_ngan_sach_thoi_gian(self):
        m, w = self.mk()
        t = [0]
        def fake_time():
            t[0] += 200
            return t[0]
        m.time = types.SimpleNamespace(sleep=lambda s: None, time=fake_time)
        m.sweep()
        self.assertEqual(w["cancels"], [], "het ngan sach truoc khi bat dau goi")

    def test_tai_lieu_bi_tu_choi_tren_cong_bo_qua_khong_bao(self):
        m, w = self.mk(status="Từ chối")
        m.sweep()
        self.assertEqual(w["todos"], [])
        self.assertTrue(w["events"][0][1]["verification_result"].startswith("cancel_skip:"))

    def test_len_co_chi_tu_lenh_sm_cong_da_nhan_o_production(self):
        m, w = self.mk()
        m.sweep()
        f = w["arm_filters"][0]
        self.assertIn(["verification_result", "=", "provider_document_cancelled_by_erp:cancelled"], f)
        self.assertIn(["request_meta", "like", '%"source": "sm_cancel"%'], f)
        self.assertIn(["request_meta", "like", '%"environment": "Production"%'], f)

    def test_cho_chan_dang_bay_khong_ghi_gi(self):
        m, w = self.mk(live=[{"name": "DSR-9", "status": "Queued"}])
        m.sweep()
        self.assertEqual(w["events"], [])


class TestCandidatesVaLenhSm(Base):
    def test_bo_goi_da_danh_dau_chet(self):
        m, w = self.mk(pkgs=[{"name": "P1", "business_name": "A", "error_code": None},
                             {"name": "P2", "business_name": "B",
                              "error_code": "provider_document_cancelled"},
                             {"name": "P3", "business_name": "C", "error_code": "x"}])
        self.assertEqual([c.name for c in m.candidates()], ["P1", "P3"])

    def test_lenh_sm_gom_ton_dong_va_loc_theo_phieu(self):
        m, w = self.mk()
        m.candidates(include_before=True, business_names=["PR-1"])
        self.assertNotIn("completed_at", w["ar_filters"][0])
        self.assertEqual(w["pkg_filters"][0]["business_name"], ["in", ["PR-1"]])

    def test_khong_co_phieu_tu_choi_thi_khong_hoi_goi(self):
        m, w = self.mk(neg_ars=[])
        self.assertEqual(m.candidates(), [])
        self.assertNotIn("pkg_filters", w)

    def test_lenh_sm_chay_thu_va_chay_that_phai_liet_ke(self):
        m, w = self.mk()
        r = m.cancel_rejected_documents(dry_run=True)
        self.assertEqual((r["count"], r["summary"]), (1, {"would_cancel": 1}))
        self.assertEqual(w["cancels"], [])
        with self.assertRaises(RuntimeError):
            m.cancel_rejected_documents(dry_run=False)
        with self.assertRaises(RuntimeError):
            m.cancel_rejected_documents(dry_run=False, business_names=["X%d" % i
                                                                       for i in range(4)])
        r = m.cancel_rejected_documents(dry_run=False, business_names=["PR-1", "PR-NOPE"])
        self.assertEqual(r["summary"], {"cancelled": 1, "not_candidate": 1})


class TestResolveUnverified(Base):
    def test_da_huy_thi_ghi_nhan(self):
        m, w = self.mk(err="provider_document_cancel_unverified", cancelled=True)
        r = m.resolve_unverified("PKG-1", "ops da xem tren cong ngay 18/11")
        self.assertEqual(r["result"], "marked")
        self.assertEqual(self.marks(w)[0][2]["error_code"], "provider_document_cancelled_by_erp")
        self.assertEqual(w["cancels"], [], "chi doc")

    def test_chua_huy_thi_go_moc_co_vet_va_cron_khong_tu_gui(self):
        m, w = self.mk(err="provider_document_cancel_unverified")
        r = m.resolve_unverified("PKG-1", "ops da xem tren cong ngay 18/11")
        self.assertEqual(r["result"], "cleared")
        self.assertEqual(self.marks(w)[0][2], {"error_code": None, "error_message": None})
        fails = [e for e in w["events"] if e[0] == "Failed"]
        self.assertEqual(fails[0][1]["request_meta"]["ly_do"], "ops da xem tren cong ngay 18/11")
        skips = [e for e in w["events"] if e[0] == "PollTick"]
        self.assertEqual(skips[0][1]["verification_result"], "cancel_skip:unverified_cleared")
        self.assertEqual(skips[0][1]["request_meta"]["source"], "auto_cancel")
        self.assertEqual(w["cancels"], [])

    def test_bat_buoc_ly_do_va_dung_trang_thai(self):
        m, w = self.mk(err="provider_document_cancel_unverified")
        with self.assertRaises(RuntimeError):
            m.resolve_unverified("PKG-1", "ngan")
        m, w = self.mk()
        self.assertTrue(m.resolve_unverified("PKG-1", "ops da xem tren cong")["reason"]
                        .startswith("not_unverified"))


class TestAdapterDestroy(unittest.TestCase):
    def test_destroy(self):
        fk = types.ModuleType("frappe")
        fk._ = lambda s: s
        fk.log_error = lambda *a, **k: None
        fu = types.ModuleType("frappe.utils")
        fu.now_datetime = fu.get_datetime = fu.add_to_date = lambda *a, **k: None
        fp = types.ModuleType("frappe.utils.password")
        fp.get_decrypted_password = lambda *a, **k: None
        mods = {"frappe": fk, "frappe.utils": fu, "frappe.utils.password": fp}
        saved = {k: sys.modules.get(k) for k in mods}
        sys.modules.update(mods)
        try:
            spec = importlib.util.spec_from_file_location(
                "_scts_destroy", os.path.join(_ESIGN, "providers", "scts.py"))
            m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m)
        finally:
            for k, v in saved.items():
                if v is None:
                    sys.modules.pop(k, None)
                else:
                    sys.modules[k] = v
        a = m.SctsAdapter.__new__(m.SctsAdapter)
        for d, want in ((1, True), ("1", True), (True, True), (0, False), ("0", False),
                        (False, False), (None, False)):
            raw = {"id": "D", "statusName": "Đang xử lý", "signers": [], "files": []}
            if d is not None:
                raw["destroy"] = d
            st = a._normalize_document("D", raw)
            self.assertEqual(st.identity["destroyed"], want, repr(d))
            self.assertEqual(st.status, "processing", "KHONG doi status chung")


class TestWiring(unittest.TestCase):
    def test_hooks_cron(self):
        with io.open(os.path.join(_APP, "ecentric_workspace", "hooks.py"), encoding="utf-8") as fh:
            src = fh.read()
        self.assertIn('"ecentric_workspace.platform.esign.provider_cancel.sweep"', src)
        self.assertEqual(src.count("provider_cancel.sweep"), 1, "dang ky MOT lan")

    def test_api_sm_post_chay_thu_mac_dinh(self):
        src = _read("api.py")
        i = src.index("def cancel_rejected_documents(")
        head = src[src.rindex("@frappe.whitelist", 0, i):i]
        body = src[i:src.index("\n\n\n", i) if "\n\n\n" in src[i:] else len(src)]
        self.assertIn('methods=["POST"]', head)
        self.assertIn("perms.assert_system_manager()", body)
        self.assertIn("dry_run=_live_flag(dry_run)", body)


if __name__ == "__main__":
    unittest.main()
