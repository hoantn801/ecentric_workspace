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
        self.assertEqual((e["status"], e["zip_path"]), ("done", "ecv6/exports/Friso/lo1.zip"))
        view = s.get_project(p)
        self.assertEqual(view["items"][0]["stage_label"], "Đủ clip - sẵn sàng trộn")
        self.assertTrue(view["exports"][0]["zip_url"].startswith("https://w.example/webhook/ec-v6/file?p=ecv6%2Fexports"))

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
        self.assertEqual(st["zipped"], {"L": "ecv6/exports/Friso/L.zip"})


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


if __name__ == "__main__":
    unittest.main()
