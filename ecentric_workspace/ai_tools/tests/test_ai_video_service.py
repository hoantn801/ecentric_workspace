# Copyright (c) 2026, eCentric and contributors
"""Nghiep vu AI Video hang loat (application/service.py) chay ngoai Frappe.

`frappe` gia (kho doc trong bo nho) + worker gia (ghi lai cac buoc enqueue, tra trang thai
do test dat). Di tron mot vong: tao du an -> them SKU -> tao anh cam -> chon -> master ->
khung neo -> clip ha -> duyet -> cam A -> duyet -> cam B -> tron + ZIP."""
import itertools
import json
import sys
import types
import unittest


# ------------------------------------------------------------------ frappe gia ---
class _Err(Exception):
    pass


class FakeDoc:
    def __init__(self, store, d):
        self._store, self.__dict__["_d"] = store, dict(d)

    def __getattr__(self, k):
        if k.startswith("_"):
            raise AttributeError(k)
        return self._d.get(k)

    def __setattr__(self, k, v):
        if k.startswith("_"):
            object.__setattr__(self, k, v)
        else:
            self._d[k] = v

    def get(self, k, default=None):
        return self._d.get(k, default)

    def set(self, k, v):
        self._d[k] = v

    def as_dict(self):
        return _Dict(self._d)

    def insert(self, ignore_permissions=False):
        self._d.setdefault("name", "%s-%d" % (self._d["doctype"][-7:].strip().replace(" ", ""), next(self._store.seq)))
        self._d.setdefault("creation", "2026-10-01 01:00:%02d" % (next(self._store.seq) % 60))
        self._store.rows.setdefault(self._d["doctype"], {})[self._d["name"]] = dict(self._d)
        return self

    def save(self, ignore_permissions=False):
        self._store.rows[self._d["doctype"]][self._d["name"]] = dict(self._d)
        return self

    def db_set(self, k, v):
        self._d[k] = v
        self.save()


class _Dict(dict):
    __getattr__ = dict.get


class Store:
    def __init__(self):
        self.rows, self.seq, self.defaults = {}, itertools.count(1), {}


def make_frappe(store):
    f = types.ModuleType("frappe")
    f.ValidationError, f.PermissionError, f.DoesNotExistError = _Err, type("P", (_Err,), {}), type("D", (_Err,), {})
    f.conf = {"ec_video_worker_url": "https://w.example", "ec_video_worker_secret": "s3cret"}
    f.session = types.SimpleNamespace(user="a@ec.vn")
    f.get_roles = lambda u=None: ["EC AI Content"]

    def match(row, filters):
        for k, v in (filters or {}).items():
            if isinstance(v, list) and v[0] == "in":
                if row.get(k) not in v[1]:
                    return False
            elif row.get(k) != v:
                return False
        return True

    def get_doc(a, b=None):
        if isinstance(a, dict):
            return FakeDoc(store, a)
        row = store.rows.get(a, {}).get(b)
        if row is None:
            raise f.DoesNotExistError(b)
        return FakeDoc(store, row)

    def get_all(dt, filters=None, fields=None, pluck=None, order_by=None, limit_page_length=None):
        rows = [r for r in store.rows.get(dt, {}).values() if match(r, filters)]
        if pluck:
            return [r[pluck] for r in rows]
        return [_Dict(r) for r in rows]

    f.get_doc, f.get_all = get_doc, get_all
    f.delete_doc = lambda dt, n, ignore_permissions=False: store.rows[dt].pop(n)
    f.db = types.SimpleNamespace(
        exists=lambda dt, flt=None: any(match(r, flt if isinstance(flt, dict) else {"name": flt}) for r in store.rows.get(dt, {}).values()),
        get_value=lambda dt, flt, field: next((r.get(field) for r in store.rows.get(dt, {}).values() if match(r, flt if isinstance(flt, dict) else {"name": flt})), None),
        set_value=lambda dt, n, vals: store.rows[dt][n].update(vals),
        commit=lambda: None, rollback=lambda: None,
        get_default=lambda k: store.defaults.get(k), set_default=lambda k, v: store.defaults.__setitem__(k, v))
    f.log_error = lambda *a, **k: None
    f.whitelist = lambda **k: (lambda fn: fn)
    f.utils = types.SimpleNamespace(now_datetime=lambda: "2026-10-01 01:00:00", strip_html=lambda s: s)
    return f


# ------------------------------------------------------------------ worker gia ---
class FakeWorker:
    def __init__(self):
        self.steps, self.tasks, self.jobs, self.host_files, self.uploads, self.ids = [], {}, {}, {}, [], itertools.count(1)
        self.calls = []

    def call(self, action, **p):
        self.calls.append((action, p))
        if action == "enqueue":
            ids = []
            for s in p["steps"]:
                tid = "t%d" % next(self.ids)
                self.steps.append((tid, s))
                self.tasks[tid] = {"id": tid, "state": "running"}
                ids.append(tid)
            return {"ok": True, "task_ids": ids}
        if action == "status":
            return {"ok": True, "tasks": list(self.tasks.values()), "breaker": {},
                    "jobs": [dict(self.jobs.get(j, {}), job_id=j) for j in p.get("jobs") or []],
                    "hosts": [{"host": h, "files": self.host_files} for h in p.get("hosts") or []]}
        if action == "export":
            if p.get("sku"):
                return {"ok": True, "zip": "ecv6/exports/Friso/%s/%s.zip" % (p["batch_id"], p["sku"])}
            return {"ok": True, "zip": "ecv6/exports/Friso/%s.zip" % p["batch_id"]}
        return {"ok": True}

    def upload(self, dest, filename, content):
        self.uploads.append(dest)
        return "ecv6/" + dest

    def finish(self, op):
        for tid, s in self.steps:
            if s["op"] == op and self.tasks[tid]["state"] == "running":
                self.tasks[tid]["state"] = "done"
                if op == "mix":
                    self.tasks[tid]["result"] = {"files": ["ecv6/output/Friso/lo1/%s/a_mix_01.mp4" % s["sku"]]}

    def last(self, op):
        return [s for _, s in self.steps if s["op"] == op][-1]


class TestService(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        sys.modules["frappe"] = make_frappe(self.store)
        sys.modules.setdefault("requests", types.ModuleType("requests"))
        for m in list(sys.modules):
            if m.startswith("ecentric_workspace.ai_tools.features.ai_video"):
                del sys.modules[m]
        from ecentric_workspace.ai_tools.features.ai_video.application import service
        from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client as wc
        self.svc, self.W, self.wc = service, FakeWorker(), wc
        self.real_sign = wc.sign
        wc.call, wc.upload = self.W.call, self.W.upload
        service._file_bytes = lambda url: b"img"
        self.store.rows["File"] = {str(i): {"name": str(i), "file_url": u, "owner": "a@ec.vn"} for i, u in enumerate(
            ["/private/files/host.png", "/private/files/f.png", "/h.png", "/a.png", "x"])}
        self.store.rows["File"]["99"] = {"name": "99", "file_url": "/private/files/other.png", "owner": "b@ec.vn"}

    def item(self, name):
        return self.store.rows["EC AI Video Item"][name]

    def test_full_round_trip(self):
        s, W = self.svc, self.W
        p = s.create_project(json.dumps({"brand": "Friso", "title": "T10", "host_image": "/private/files/host.png",
                                         "gate_motion": 1, "gate_hold_a": 1, "talk_count": 2, "anchor_source": "master"}))["name"]
        it = s.add_items(p, json.dumps([{"sku": "FRISO3", "product_image": "/private/files/f.png", "width_cm": 14,
                                         "extra_images": ["/private/files/host.png", "/a.png", "x", "/h.png", "/private/files/f.png"],
                                         "height_cm": 18, "batch": "lo1", "product_category": "milk_can"},
                                        {"sku": "", "product_image": "x"}]))["items"]
        self.assertEqual(len(it), 1)
        n = it[0]
        s.start_holds(p, json.dumps([n]))
        self.assertEqual(self.item(n)["stage"], "holds")
        hs = W.last("holds")
        self.assertTrue(hs["job_id"].endswith("_R1"))
        self.assertEqual(hs["fields"]["product_width_cm"], "14")
        self.assertEqual(len(hs["extra_images"]), 4)            # toi da 4 anh phu
        self.assertTrue(hs["extra_images"][0].endswith("_side1.png"))
        self.assertEqual(hs["files"]["host_video"], "ecv6/inbox/%s/host.png" % s.flow.slug(p, 20))
        job = hs["job_id"]
        # anh cam xong -> cho chon
        W.finish("holds")
        W.jobs[job] = {"candidates": [{"id": "hold_c01", "file": {"path": "jobs/%s/c1.png" % job}}]}
        s.tick(p)
        self.assertEqual(self.item(n)["stage"], "pick")
        s.pick(n, "hold_c01")
        self.assertEqual(W.last("master")["candidate"], "hold_c01")
        # master xong nhung chua co khung neo -> du an tao khung neo tu master
        W.finish("master")
        W.jobs[job]["master"] = {"path": "jobs/%s/m.png" % job}
        s.tick(p)
        self.assertEqual(self.item(n)["stage"], "wait_anchor")
        a = W.last("anchor")
        self.assertTrue(a["from_master"])
        self.assertIn(job, a["host_image"])
        s.tick(p)                                   # khong enqueue anchor lan 2
        self.assertEqual(len([1 for _, x in W.steps if x["op"] == "anchor"]), 1)
        # khung neo xong -> clip noi + clip ha
        W.finish("anchor")
        W.host_files = {"anchor": {"path": "ecv6/hosts/H/anchor.png"}}
        s.tick(p)
        self.assertEqual(self.item(n)["stage"], "motion")
        self.assertEqual(W.last("units")["holds"], 0)
        self.assertEqual(W.last("talk")["fill_to"], 2)
        W.finish("units")
        s.tick(p)
        self.assertEqual(self.item(n)["stage"], "qc_motion")
        s.regen_clip(n, json.dumps(["left"]))
        self.assertEqual(W.last("units")["dirs"], ["left"])
        self.assertIn(("regen", {"job_id": job, "stage": "unit", "units": ["putdown_left"]}), W.calls)
        W.finish("units")
        s.tick(p)
        s.approve(n)
        self.assertEqual((self.item(n)["stage"], W.last("units")["hold_start"]), ("hold_a", 1))
        W.finish("units")
        s.tick(p)
        s.approve(n)
        W.finish("units")
        s.tick(p)
        self.assertEqual(self.item(n)["stage"], "ready")
        # tron + zip
        ex = s.mix(p, json.dumps({"items": [n], "mode": "mix", "variants": 3, "batch": "lo1"}))
        self.assertEqual(ex["tasks"], 1)
        m = W.last("mix")
        self.assertEqual((m["n"], m["jobs"], m["batch_id"], m["duration_s"]), (3, [job], "lo1", 72.0))
        W.finish("mix")
        s.tick(p)
        e = self.store.rows["EC AI Video Export"][ex["export"]]
        self.assertEqual(e["status"], "done")
        self.assertIn("ecv6/exports/Friso/lo1/%s.zip" % m["sku"], json.loads(e["files_json"]))     # 1 ZIP / SKU
        view = s.get_project(p)
        self.assertEqual(view["items"][0]["stage_label"], "Đủ clip - sẵn sàng trộn")
        self.assertTrue(view["exports"][0]["zips"][0]["url"].startswith("https://w.example/webhook/ec-v6/file?p=ecv6%2Fexports"))

    def test_rejects_other_users_file(self):
        with self.assertRaises(Exception):
            p = self.svc.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/h.png"}))["name"]
            self.svc.add_items(p, json.dumps([{"sku": "A", "product_image": "/a.png", "extra_images": ["/private/files/other.png"]}]))
        with self.assertRaises(Exception):
            self.svc.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/private/files/other.png"}))
        with self.assertRaises(Exception):
            self.svc.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/private/files/nope.png"}))

    def test_failure_then_retry(self):
        s, W = self.svc, self.W
        p = s.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/h.png"}))["name"]
        n = s.add_items(p, json.dumps([{"sku": "A", "product_image": "/a.png"}]))["items"][0]
        s.start_holds(p, json.dumps([n]))
        tid = W.steps[-1][0]
        W.tasks[tid].update(state="failed", error="state=fail failCode=500")
        s.tick(p)
        self.assertEqual((self.item(n)["stage"], self.item(n)["stage_state"]), ("holds", "error"))
        s.retry(n)
        self.assertIn(("retry", {"task_ids": [tid]}), W.calls)
        self.assertEqual(self.item(n)["stage_state"], "running")
        # gen lai anh = job moi R2
        W.tasks[tid]["state"] = "failed"
        s.tick(p)
        s.regen_holds(n, json.dumps({"width_cm": 20}))
        self.assertTrue(W.last("holds")["job_id"].endswith("_R2"))
        self.assertEqual(W.last("holds")["fields"]["product_width_cm"], "20")

    def test_night_mode_auto_mix_and_zip(self):
        s, W = self.svc, self.W
        p = s.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/h.png", "night_mode": 1,
                                         "anchor_source": "host", "talk_count": 0}))["name"]
        n = s.add_items(p, json.dumps([{"sku": "A", "product_image": "/a.png", "batch": "L"}]))["items"][0]
        s.start_holds(p, json.dumps([n]))
        s.tick(p)
        self.assertEqual(W.last("anchor")["host_image"].endswith("host.png"), True)   # nguon host: tao ngay
        job = W.last("holds")["job_id"]
        W.finish("holds"); W.finish("anchor")
        W.jobs[job] = {"candidates": [{"id": "hold_c02", "file": {"path": "c"}}], "master": {"path": "m"}}
        W.host_files = {"anchor": {"path": "a"}}
        s.tick(p)
        s.pick(n, "hold_c02")
        for op in ("master", "units", "units", "units", "mix"):
            W.finish(op)
            s.tick(p)
        self.assertEqual(self.item(n)["stage"], "done")
        st = json.loads(self.store.rows["EC AI Video Project"][p]["state_json"])
        day = W.last("mix")["batch_id"]
        self.assertRegex(day, r"^\d{4}-\d{2}-\d{2}$")                     # chay dem: thu muc theo ngay
        self.assertEqual(st["zipped"], {"A": "ecv6/exports/Friso/%s/A.zip" % day})   # 1 ZIP / SKU


class TestRegister(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        sys.modules["frappe"] = make_frappe(self.store)
        sys.modules.setdefault("requests", types.ModuleType("requests"))
        for m in list(sys.modules):
            if m.startswith("ecentric_workspace.ai_tools.features.ai_video"):
                del sys.modules[m]
        from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client
        self.wc = worker_client

    def sig(self, url, ts, key="s3cret"):
        import hashlib, hmac
        return hmac.new(key.encode(), ("%s|%s" % (url, ts)).encode(), hashlib.sha256).hexdigest()

    def test_register_quick_tunnel(self):
        import time
        ts = str(int(time.time()))
        u = "https://abc-def-123.trycloudflare.com"
        self.assertTrue(self.wc.register(u, ts, self.sig(u, ts)))
        self.assertEqual(self.wc._conf()[0], u)
        self.assertTrue(self.wc.sign("ecv6/x.mp4").startswith(u + "/webhook/ec-v6/file?"))

    def test_register_rejects_bad(self):
        import time
        ts = str(int(time.time()))
        u = "https://abc.trycloudflare.com"
        self.assertFalse(self.wc.register(u, ts, self.sig(u, ts, "wrong")))
        self.assertFalse(self.wc.register(u, str(int(ts) - 3600), self.sig(u, str(int(ts) - 3600))))
        evil = "https://evil.example.com"
        self.assertFalse(self.wc.register(evil, ts, self.sig(evil, ts)))
        self.assertEqual(self.store.defaults, {})


class TestKhungVaNhom(unittest.TestCase):
    """05/10: khung SP nguoi dung ve + prompt theo nhom SP + role quan tri."""
    setUp = TestService.setUp
    item = TestService.item

    def mk(self, cat="milk_can"):
        s = self.svc
        p = s.create_project(json.dumps({"brand": "Friso", "title": "T", "host_image": "/private/files/host.png"}))["name"]
        it = s.add_items(p, json.dumps([{"sku": "A1", "product_image": "/private/files/f.png", "product_category": cat},
                                        {"sku": "A2", "product_image": "/private/files/f.png", "product_category": cat}]))["items"]
        return p, it

    def worker_groups(self, groups):
        real = self.W.call

        def call(action, **p):
            if action == "groups_get":
                return {"ok": True, "groups": groups, "history": {}}
            return real(action, **p)
        self.wc.call = call

    def as_admin(self, yes=True):
        import frappe
        frappe.get_roles = lambda u=None: ["EC AI Content", "EC AI Video Admin"] if yes else ["EC AI Content"]

    def test_khung_sp_luu_va_gui_worker(self):
        s = self.svc
        p, (a, b) = self.mk()
        s.update_item(a, json.dumps({"guide_bbox": "0.3874,0.4748,0.2266,0.0505"}))
        self.assertEqual(json.loads(self.item(a)["state_json"])["guide_bbox"], "0.3874,0.4748,0.2266,0.0505")
        with self.assertRaises(Exception):
            s.update_item(a, json.dumps({"guide_bbox": "0.9,0.9,0.5,0.5"}))
        s.start_holds(p, json.dumps([a, b]))
        steps = [st for _, st in self.W.steps if st["op"] == "holds"]
        self.assertEqual(steps[0]["fields"]["guide_bbox"], "0.3874,0.4748,0.2266,0.0505")
        self.assertNotIn("guide_bbox", steps[1]["fields"])
        s.update_item(b, json.dumps({"guide_bbox": ""}))            # xoa khung = de AI tu tinh
        self.assertEqual(json.loads(self.item(b)["state_json"]).get("guide_bbox"), "")

    def test_chi_quan_tri_sua_prompt(self):
        s = self.svc
        import frappe
        with self.assertRaises(frappe.PermissionError):
            s.prompts_set(json.dumps({"talk": "x"}))
        with self.assertRaises(frappe.PermissionError):
            self._g().groups_set(json.dumps({"cat": "milk_can", "data": {"status": "ok"}}))
        self.as_admin()
        s.prompts_set(json.dumps({"talk": "x", "la": "bo"}))
        self.assertEqual(self.W.calls[-1], ("prompts_set", {"prompts": {"talk": "x"}}))
        g = self._g()
        g.groups_set(json.dumps({"cat": "milk_can", "data": {"status": "ok", "hold": "Đỡ đáy lon"}, "note": "v1"}))
        self.assertEqual(self.W.calls[-1][0], "groups_set")
        self.assertEqual(self.W.calls[-1][1]["data"], {"status": "ok", "hold": "Đỡ đáy lon"})
        self.assertEqual(self.W.calls[-1][1]["by"], "a@ec.vn")
        for bad in ({"cat": "../etc", "data": {}}, {"cat": "milk_can", "data": {"status": "zz"}}, {"cat": "milk_can", "data": "x"}, ["x"]):
            with self.assertRaises(frappe.ValidationError):
                g.groups_set(json.dumps(bad))
        g.groups_rollback("milk_can", "2")
        self.assertEqual(self.W.calls[-1], ("groups_rollback", {"cat": "milk_can", "v": 2, "by": "a@ec.vn"}))

    def _g(self):
        from ecentric_workspace.ai_tools.features.ai_video.application import groups
        return groups

    def test_nhom_dang_thu_bat_chot_duyet(self):
        s = self.svc
        self.worker_groups({"milk_can": {"status": "try"}})
        p, (a, b) = self.mk("milk_can")
        s.start_holds(p, json.dumps([a, b]))                     # ca lo cung luc: chi SKU dau dung cho duyet
        self.assertTrue(json.loads(self.item(a)["state_json"])["force_gate"])
        self.assertNotIn("force_gate", json.loads(self.item(b)["state_json"]))
        self.store.rows["EC AI Video Item"][a]["stage"] = "ready"   # SKU dau da ra clip
        s.start_holds(p, json.dumps([b]))
        self.assertNotIn("force_gate", json.loads(self.item(b)["state_json"]))
        self.assertTrue(s.get_project(p)["items"][0]["force_gate"])

    def test_tick_dang_chay_thi_bo_qua(self):
        s = self.svc
        held = set()

        class Cache:
            def make_key(self, k):
                return k

            def set(self, k, v, nx=False, ex=None):
                if nx and k in held:
                    return None
                held.add(k)
                return True

            def delete(self, k):
                held.discard(k)

        sys.modules["frappe"].cache = lambda: Cache()
        p = s.create_project(json.dumps({"brand": "Friso", "title": "T", "host_image": "/private/files/host.png"}))["name"]
        held.add("ai_video_tick|" + p)                      # tick khac dang giu khoa
        self.assertEqual(s.tick(p), {"ok": False, "busy": True})
        self.assertEqual(s.get_project(p, 1)["project"]["name"], p)   # van mo duoc du an
        held.clear()
        self.assertTrue(s.tick(p)["ok"])
        self.assertFalse(held)                              # tick xong tra khoa

    def test_tick_bi_ghi_de_van_mo_duoc(self):
        s = self.svc
        p = s.create_project(json.dumps({"brand": "Friso", "title": "T", "host_image": "/private/files/host.png"}))["name"]
        s.tick = lambda name: (_ for _ in ()).throw(Exception("EC AI Video Item x has been modified after you have opened it"))
        self.assertIsNone(s.get_project(p, 1)["worker_down"])

    def test_anh_cam_hien_loi_ai_kiem_tra(self):
        s, W = self.svc, self.W
        p = s.create_project(json.dumps({"brand": "Friso", "title": "T", "host_image": "/private/files/host.png"}))["name"]
        it = s.add_items(p, json.dumps([{"sku": "A1", "product_image": "/private/files/f.png"}]))["items"][0]
        s.start_holds(p, json.dumps([it]))
        job = self.item(it)["job_id"]
        W.finish("holds")
        qc = {"pass": False, "issues": ["ho rang", 'sai chu "300 g" -> "800 g"'], "warn": []}
        W.jobs[job] = {"candidates": [{"id": "hold_c01", "file": {"path": "jobs/%s/c1.png" % job}, "qc": qc},
                                      {"id": "hold_c02", "file": {"path": "jobs/%s/c2.png" % job}}]}
        s.tick(p)
        c = s.get_project(p)["items"][0]["candidates"]
        self.assertEqual((c[0]["qc"], c[1]["qc"]), (qc, None))
        st = json.loads(self.item(it)["state_json"])
        self.assertEqual(st["views"]["cands"][0][2], qc)            # luu kem link -> mo trang khong hoi laptop

    def test_mo_du_an_khong_hoi_worker_khi_da_co_link(self):
        s = self.svc
        p = s.create_project(json.dumps({"brand": "Friso", "title": "T", "host_image": "/private/files/host.png"}))["name"]
        it = s.add_items(p, json.dumps([{"sku": "A1", "product_image": "/private/files/f.png"}]))["items"][0]
        s.start_holds(p, json.dumps([it]))
        job = self.item(it)["job_id"]
        st = json.loads(self.item(it)["state_json"])
        st["views"] = {"cands": [["hold_c01", "jobs/%s/c1.png" % job]], "reco": "hold_c01", "master": None, "units": {"hold_01": "ecv6/units/x/hold_01.mp4"}}
        self.item(it)["state_json"] = json.dumps(st)
        calls = []
        real = self.wc.call
        self.wc.call = lambda a, **k: calls.append(a) or real(a, **k)
        v = s.get_project(p)
        self.assertEqual(calls, [])                                   # khong goi laptop
        self.assertEqual(v["items"][0]["candidates"][0]["id"], "hold_c01")
        self.assertIn("hold_01", v["items"][0]["units"])

    def test_bo_tick_clip_noi_khong_dung_khi_tron(self):
        s, W = self.svc, self.W
        p = s.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/h.png", "talk_count": 2}))["name"]
        W.host_files = {"talk_01": {"path": "t1"}, "talk_01_rev": {"path": "t1r"}, "talk_02": {"path": "t2"}}
        s.tick(p)
        self.assertEqual(s.set_talks(p, json.dumps(["talk_02", "talk_09_rev", "x"]))["talk_off"], ["talk_02"])
        self.assertEqual(s.get_project(p)["project"]["talk_off"], ["talk_02"])
        s.mix(p, json.dumps({"mode": "talk", "variants": 1}))
        self.assertEqual(W.last("mix")["talk_off"], ["talk_02"])
        s.set_talks(p, json.dumps(["talk_01", "talk_02"]))                # bo het -> khong tron, bao loi
        r = s.mix(p, json.dumps({"mode": "talk", "variants": 1}))
        self.assertEqual(r["tasks"], 0)
        self.assertIn("tick", self.store.rows["EC AI Video Export"][r["export"]]["status"])
        s.regen_talk(p, json.dumps(["talk_01"]))                          # gen lai -> tu tick lai
        self.assertEqual(s.get_project(p)["project"]["talk_off"], ["talk_02"])

    def _ready_item(self):
        s, W = self.svc, self.W
        p = s.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/h.png", "talk_count": 0}))["name"]
        n = s.add_items(p, json.dumps([{"sku": "A1", "product_image": "/a.png"}]))["items"][0]
        s.start_holds(p, json.dumps([n]))
        st = json.loads(self.item(n)["state_json"])
        st["views"] = {"cands": [], "units": {k: "u/" + k for k in ("putdown_left", "pickup_left", "putdown_right", "hold_01", "hold_02")}}
        self.item(n).update(stage="ready", stage_state="waiting", state_json=json.dumps(st))
        return p, n

    def test_bo_tick_clip_sku_va_gen_lai_tung_clip(self):
        s, W = self.svc, self.W
        p, n = self._ready_item()
        self.assertEqual(s.set_units(n, json.dumps(["putdown_left", "hold_02", "pickup_left", "xx"]))["unit_off"], ["hold_02", "putdown_left"])
        with self.assertRaises(Exception):                                  # phai con 1 clip ha + 1 clip cam
            s.set_units(n, json.dumps(["hold_01", "hold_02"]))
        s.mix(p, json.dumps({"items": [n], "variants": 1, "batch": "dot1"}))
        job = self.item(n)["job_id"]
        m = W.last("mix")
        self.assertEqual((m["unit_off"], m["batch_id"]), (sorted([job + ":hold_02", job + ":putdown_left"]), "dot1"))
        s.regen_clip(n, None, "putdown_left")                               # gen lai dung 1 clip
        u = W.last("units")
        self.assertEqual((u["dirs"], u["holds"], u["keep_dirs"]), (["left"], 0, True))
        self.assertEqual(self.item(n)["stage"], "fix")
        self.assertEqual(json.loads(self.item(n)["state_json"])["unit_off"], ["hold_02"])
        W.finish("units")
        s.tick(p)
        self.assertEqual(self.item(n)["stage"], "ready")
        s.regen_clip(n, None, "hold_02")
        self.assertEqual((W.last("units")["holds"], W.last("units")["hold_start"]), (1, 2))

    def test_xuat_zip_tung_sku(self):
        s, W = self.svc, self.W
        p, n = self._ready_item()
        r = s.mix(p, json.dumps({"items": [n], "variants": 1}))
        W.finish("mix")
        s.tick(p)
        ex = s.get_project(p)["exports"][0]
        self.assertEqual([z["sku"] for z in ex["zips"]], ["A1"])
        self.assertEqual(len(ex["files"]), 1)
        self.assertRegex(self.store.rows["EC AI Video Export"][r["export"]]["batch"], r"^\d{4}-\d{2}-\d{2}$")

    def test_chi_phi_theo_job_ca_viec_ngoai_erp(self):
        items = [{"sku": "Pin cúc áo", "job_id": "PIN_PIN_C_C_O_P1_R2"}, {"sku": "123", "job_id": None}]
        costs = {"usd_per_credit": 0.005, "job": {"PIN_PIN_C_C_O_P1_R1": {"usd": 1.0}, "PIN_PIN_C_C_O_P1_R2": {"usd": 2.0},
                                                   "PIN_PIN_C_C_O_P1_R2_X": {"usd": 9.0}, "B_123_P1_R1": {"usd": 0.5}}}
        from ecentric_workspace.ai_tools.features.ai_video.domain import flow
        flow.cost_view(costs, items)
        self.assertEqual((items[0]["cost_usd"], items[1]["cost_usd"]), (3.0, 0.5))

    def test_luu_tru_va_xoa_du_an(self):
        s = self.svc
        p, n = self._ready_item()
        s.mix(p, json.dumps({"items": [n], "variants": 1}))
        self.assertEqual(s.archive_project(p, 1)["status"], "Lưu trữ")
        self.assertEqual(s.archive_project(p, 0)["status"], "Đang chạy")
        self.store.rows["EC AI Video Project"][p]["owner"] = "b@ec.vn"      # nguoi khac, khong phai quan tri
        with self.assertRaises(Exception):
            s.delete_project(p)
        self.store.rows["EC AI Video Project"][p]["owner"] = "a@ec.vn"
        s.delete_project(p)
        self.assertNotIn(p, self.store.rows["EC AI Video Project"])
        self.assertEqual([r for r in self.store.rows["EC AI Video Item"].values() if r.get("project") == p], [])
        self.assertEqual([r for r in self.store.rows["EC AI Video Export"].values() if r.get("project") == p], [])

    def test_chan_sku_trung(self):
        s = self.svc
        p = s.create_project(json.dumps({"brand": "B", "title": "T", "host_image": "/h.png"}))["name"]
        s.add_items(p, json.dumps([{"sku": "PHN_001", "product_image": "/a.png"}]))
        for rows in ([{"sku": "PHN_003", "product_image": "/a.png"}, {"sku": "phn-003", "product_image": "/a.png"}],
                     [{"sku": "PHN 001", "product_image": "/a.png"}]):
            with self.assertRaises(Exception) as c:
                s.add_items(p, json.dumps(rows))
            self.assertIn("trùng", str(c.exception))
        self.assertEqual(len(self.store.rows["EC AI Video Item"]), 1)          # khong luu dong nao khi co trung

    def test_tat_du_phong_kie_va_so_clip_cam(self):
        s, W = self.svc, self.W
        p, n = self._ready_item()
        s.update_project(p, json.dumps({"px_fallback": False, "hold_count": 3}))
        s.mix(p, json.dumps({"items": [n], "variants": 1}))
        self.assertIs([c for c in W.calls if c[0] == "enqueue"][-1][1].get("px_fallback"), False)
        st = json.loads(self.store.rows["EC AI Video Project"][p]["state_json"])
        self.assertEqual((st["px_fallback"], st["hold_count"]), (False, 3))

    def test_chon_nha_cung_cap_ai(self):
        s, W = self.svc, self.W
        p, n = self._ready_item()
        s.update_project(p, json.dumps({"ai_provider": "plenx"}))
        s.mix(p, json.dumps({"items": [n], "variants": 1}))
        self.assertEqual([c for c in W.calls if c[0] == "enqueue"][-1][1].get("provider"), "plenx")
        s.update_project(p, json.dumps({"ai_provider": ""}))
        s.mix(p, json.dumps({"items": [n], "variants": 1}))
        self.assertNotIn("provider", [c for c in W.calls if c[0] == "enqueue"][-1][1])
        with self.assertRaises(Exception):
            s.update_project(p, json.dumps({"ai_provider": "abc"}))

    def test_ket_qua_tron_bao_thieu_ban(self):
        s, W = self.svc, self.W
        p, n = self._ready_item()
        r = s.mix(p, json.dumps({"items": [n], "variants": 2}))
        W.finish("mix")
        tid = [t for t, st in W.steps if st["op"] == "mix"][-1]
        W.tasks[tid]["result"]["short"] = {"sku": "PHN_004", "made": 0, "want": 2}
        s.tick(p)
        st = self.store.rows["EC AI Video Export"][r["export"]]["status"]
        self.assertIn("PHN_004 0/2", st)
        self.assertIn("thư mục mới", st)
        self.assertLessEqual(len(st), 140)

    def test_ket_qua_tron_bao_thieu_clip(self):
        s, W = self.svc, self.W
        p, n = self._ready_item()
        r = s.mix(p, json.dumps({"items": [n], "variants": 1}))
        W.finish("mix")
        tid = [t for t, st in W.steps if st["op"] == "mix"][-1]
        W.tasks[tid]["result"]["warn"] = ["A1_hold_01.mp4: kho clip khong du"]
        s.tick(p)
        self.assertIn("nên gen thêm", self.store.rows["EC AI Video Export"][r["export"]]["status"])

    def test_ket_qua_tron_ghi_theo_audio(self):
        s = self.svc
        p, n = self._ready_item()
        r = s.mix(p, json.dumps({"items": [n], "variants": 1}))
        self.assertEqual(self.store.rows["EC AI Video Export"][r["export"]]["duration"], 0)
        r = s.mix(p, json.dumps({"items": [n], "variants": 1, "duration": 45}))
        self.assertEqual(self.store.rows["EC AI Video Export"][r["export"]]["duration"], 45)

    def test_khoi_luong_gui_worker(self):
        s, W = self.svc, self.W
        p = s.create_project(json.dumps({"brand": "Pin", "title": "T", "host_image": "/private/files/host.png"}))["name"]
        it = s.add_items(p, json.dumps([{"sku": "THO40", "product_image": "/private/files/f.png", "weight_g": 900}]))["items"][0]
        self.assertEqual(self.item(it)["weight_g"], 900)
        s.start_holds(p, json.dumps([it]))
        self.assertIn("about 900 g", W.last("holds")["fields"]["product_notes"])

    def test_yeu_cau_nhom_moi(self):
        import frappe
        frappe.utils.escape_html = lambda x: x.replace("<", "&lt;")
        g = self._g()
        with self.assertRaises(frappe.ValidationError):        # chua ai co role quan tri
            g.group_request(json.dumps({"name": "Chai nuoc giat", "hold": "xach quai"}))
        self.store.rows["Has Role"] = {"r1": {"name": "r1", "role": "EC AI Video Admin", "parenttype": "User", "parent": "q@ec.vn"},
                                       "r2": {"name": "r2", "role": "EC AI Video Admin", "parenttype": "User", "parent": "off@ec.vn"}}
        self.store.rows["User"] = {"q@ec.vn": {"name": "q@ec.vn", "enabled": 1}, "off@ec.vn": {"name": "off@ec.vn", "enabled": 0}}
        with self.assertRaises(frappe.ValidationError):        # thieu mo ta cach cam
            g.group_request(json.dumps({"name": "X"}))
        r = g.group_request(json.dumps({"name": "<b>Chai</b>", "hold": "xach quai", "sku": "S9"}))
        self.assertEqual(r, {"sent_to": 1})
        todo = list(self.store.rows["ToDo"].values())[0]
        self.assertEqual(todo["allocated_to"], "q@ec.vn")
        self.assertIn("&lt;b>Chai", todo["description"])


if __name__ == "__main__":
    unittest.main()
