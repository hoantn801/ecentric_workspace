# Copyright (c) 2026, eCentric and contributors
"""Bo live + Kho host (fix10b): domain kit_plan + service voi repository / may chay video gia."""
import json
import unittest

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application.get_kit_service import GetKitService
from ecentric_workspace.ai_tools.features.ai_live.application.host_image_service import HostImageService
from ecentric_workspace.ai_tools.features.ai_live.application.host_image_status_service import HostImageStatusService
from ecentric_workspace.ai_tools.features.ai_live.application.host_save_service import HostSaveService
from ecentric_workspace.ai_tools.features.ai_live.application.list_hosts_service import ListHostsService
from ecentric_workspace.ai_tools.features.ai_live.application.motion_set_service import MotionSetService
from ecentric_workspace.ai_tools.features.ai_live.application.save_kit_service import SaveKitService
from ecentric_workspace.ai_tools.features.ai_live.application.send_kit_service import SendKitService
from ecentric_workspace.ai_tools.features.ai_live.application.start_build_kit_service import StartBuildKitService
from ecentric_workspace.ai_tools.features.ai_live.domain import kit_plan

CONTENT = ["EC AI Content"]


def V(f, dur=10, ver=1):
    return {"file": "/private/files/%s" % f, "name": f, "dur": dur, "version": ver}


def kit_payload(**kw):
    d = {"brand": "friso", "title": "Friso T11", "host_key": "H_BOO3HGI9JF", "mode": "full", "break_sec": 20,
         "products": [{"id": "sp01", "name": "Gold 4", "platformIds": {"shopee": "2234567", "tiktok": ""},
                       "main_free": [V("a.mp3", 50), V("b.mp3", 75, 2)], "main_hold": [V("c.mp3", 60)], "putdown": True, "pickup": True}],
         "faq": [{"topic": "Giá", "videos": [V("g1.mp3", 12), V("g2.mp3", 11)]}, {"topic": "", "videos": []}],
         "generic": {"greet": [V("chao.mp3", 4)], "thanks": [], "answer": []}}
    d.update(kw)
    return d


class FakeKits:
    def __init__(self):
        self.rows, self.n = {}, 0

    def get(self, name):
        r = self.rows.get(name)
        return json.loads(json.dumps(r)) if r else None

    def save(self, name, values):
        if not name:
            self.n += 1
            name = "kit%d" % self.n
            self.rows[name] = {"name": name, "state": {}, "products": [], "faq": [], "generic": {}}
        self.rows[name].update(json.loads(json.dumps(values)))
        return name

    def list(self, brand=None):
        return [r for r in self.rows.values() if not brand or r["brand"] == brand]


class FakeFiles:
    def __init__(self, owner="me"):
        self.own = owner

    def owner(self, url):
        return None if "missing" in url else ("other" if "other" in url else self.own)

    def content(self, url):
        return None if "missing" in url else b"bytes:" + url.encode()


class FakeWorker:
    def __init__(self, fail_upload_at=None):
        self.calls, self.uploads, self.fail_at = [], [], fail_upload_at
        self.tasks = []

    def upload(self, dest, fname, content):
        if self.fail_at is not None and len(self.uploads) == self.fail_at:
            raise RuntimeError("Không gửi được file lên máy chạy video.")
        self.uploads.append(dest)
        return "ecv6/" + dest

    def call(self, action, **kw):
        self.calls.append((action, kw))
        if action == "enqueue":
            return {"task_ids": ["T%d" % i for i in range(len(kw["steps"]))]}
        if action == "status":
            return {"tasks": self.tasks}
        if action == "hosts_list":
            return {"hosts": [{"host": "H_BOO3HGI9JF", "anchor": "ecv6/hosts/H_BOO3HGI9JF/anchor.png", "talks": 81}]}
        if action == "anchor_pick":
            return {"anchor": "ecv6/hosts/%s/anchor.png" % kw["host"]}
        return {}

    def sign(self, path, ttl=None, width=None):
        return "https://w/" + path + ("?w=%s" % width if width else "")


class FakeLabels:
    def __init__(self):
        self.d = {"H_BOO3HGI9JF": "Linh"}

    def all(self):
        return dict(self.d)

    def set(self, host, label):
        self.d[host] = label


class FakeBrands:
    def get(self, brand, with_keys=False):
        return {"brand": brand, "brand_name": "Friso", "kit_folder": "G:\\AI Live\\friso"} if brand == "friso" else None

    def list_names(self):
        return ["friso"]


class TestKitPlan(unittest.TestCase):
    def test_generic_four_sets_scripts_and_defaults(self):
        gen = kit_plan.normalize_generic({"cho": [V("cho_1.mp3")], "thanks": [V("camon.mp3")],
                                          "scripts": {"cho": ["  Dạ em xem chút nha  ", 5, "x" * 300], "bogus": ["y"]}})
        self.assertEqual(set(gen) - {"scripts"}, {"greet", "thanks", "answer", "cho",                  # fix10e: + 4 nhom dua vit
                                                  "race_call", "race_commentary", "race_winner", "race_claim"})
        self.assertEqual(gen["scripts"], {"cho": ["Dạ em xem chút nha", "x" * C.MAX_SCRIPT_CHARS]})
        ents = kit_plan.audio_entries([], [], gen)
        self.assertEqual([e[0] for e in ents], ["thanks_1", "cho_1"])
        st = kit_plan.build_step({"name": "k", "brand": "friso", "host_key": "H_X"}, [], [], gen,
                                 {a["file"]: "ecv6/inbox/k/" + n for n, a in ents})
        self.assertEqual(sorted(st["generic"]), ["answer", "cho", "greet", "race_call", "race_claim", "race_commentary",
                                                 "race_winner", "thanks"])
        self.assertEqual(st["generic"]["cho"][0]["audio"], "ecv6/inbox/k/cho_1")
        d = kit_plan.generic_defaults()
        self.assertEqual({g: (d[g]["min"], d[g]["max"], len(d[g]["scripts"])) for g in d},
                         {"greet": (3, 5, 5), "thanks": (3, 3, 3), "answer": (2, 2, 2), "cho": (3, 3, 3),
                          "race_call": (2, 2, 2), "race_commentary": (3, 4, 4), "race_winner": (2, 2, 2), "race_claim": (1, 2, 2)})

    def test_normalize_and_step(self):
        p = kit_plan.normalize_products(kit_payload()["products"] + [{"name": "Mum"}])
        self.assertEqual([x["id"] for x in p], ["sp01", "sp02"])
        self.assertEqual(p[0]["platformIds"], {"shopee": "2234567", "tiktok": ""})
        self.assertEqual(p[0]["main_free"][1]["version"], 2)
        faq = kit_plan.normalize_faq([{"topic": "Giá", "videos": [V("g.mp3")]}])
        gen = kit_plan.normalize_generic({"greet": [V("chao.mp3")]})
        ents = kit_plan.audio_entries(p, faq, gen)
        self.assertEqual([e[0] for e in ents], ["sp01_free_1", "sp01_free_2", "sp01_hold_1", "faq01_1", "greet_1"])
        rels = {a["file"]: "ecv6/inbox/x/" + n for n, a in ents}
        kit = {"name": "abc", "brand": "friso", "host_key": "H_X", "mode": "lite", "break_sec": "25", "background": "/files/bg.png", "bake_bg": 1}
        st = kit_plan.build_step(kit, p, faq, gen, rels, "ecv6/inbox/x/background.png")
        self.assertEqual((st["op"], st["mode"], st["break_sec"], st["bake_bg"], st["background_kind"]), ("build_kit", "lite", 25, True, "image"))
        self.assertEqual(st["products"][0]["main_hold"][0]["audio"], "ecv6/inbox/x/sp01_hold_1")
        self.assertEqual(st["products"][0]["platformIds"]["shopee"], "2234567")
        self.assertEqual(st["out"], "ecv6/kits/friso/abc")
        kit["background"] = "/files/bg.mp4"
        self.assertFalse(kit_plan.build_step(kit, p, faq, gen, rels, "x.mp4")["bake_bg"])   # nen dong khong ghep san

    def test_rejects(self):
        bad = [lambda: kit_plan.normalize_products([{"id": "sp 1"}]),
               lambda: kit_plan.normalize_products([{"id": "a"}, {"id": "A"}]),
               lambda: kit_plan.normalize_products([{"id": "a", "platformIds": {"shopee": "x y"}}]),
               lambda: kit_plan.normalize_products([{"id": "a", "main_free": [V("x.mp4")]}]),
               lambda: kit_plan.normalize_products([{"id": "a", "main_free": [V("x%d.mp3" % i) for i in range(7)]}]),
               lambda: kit_plan.normalize_faq([{"topic": "", "videos": [V("x.mp3")]}]),
               lambda: kit_plan.motion_plan([{"dur": 5, "n": 2}]),
               lambda: kit_plan.motion_plan([{"dur": 10, "n": 0}]),
               lambda: kit_plan.motion_plan([{"dur": 10, "n": 21}]),
               lambda: kit_plan.image_cost("dall-e", 4)]
        for i, f in enumerate(bad):
            with self.assertRaises(C.AiLiveError, msg=str(i)):
                f()

    def test_motion_proposal_and_cost(self):
        p = kit_plan.motion_plan()
        self.assertEqual(p, [{"dur": 10, "n": 10}, {"dur": 8, "n": 5}, {"dur": 6, "n": 3}, {"dur": 4, "n": 2}])
        c = kit_plan.motion_cost(p)
        self.assertEqual((c["clips"], c["seconds"], c["credits"], c["vnd"]), (20, 166, 747, 59760))
        self.assertEqual(kit_plan.image_cost("nano-banana-full", 4), {"credits": 40, "vnd": 3200})
        self.assertIsNone(kit_plan.image_cost("seedream", 4)["credits"])

    def test_tasks_summary(self):
        self.assertEqual(kit_plan.tasks_summary([{"state": "done"}, {"state": "running"}])[0], C.KitStatus.BUILDING)
        self.assertEqual(kit_plan.tasks_summary([{"state": "done"}])[0], C.KitStatus.DONE)
        st, p = kit_plan.tasks_summary([{"state": "done"}, {"state": "failed", "error": "lipsync loi"}])
        self.assertEqual((st, p["failed"], p["errors"]), (C.KitStatus.ERROR, 1, ["lipsync loi"]))


class TestKitServices(unittest.TestCase):
    def setUp(self):
        self.kits, self.files, self.worker = FakeKits(), FakeFiles(), FakeWorker()

    def _save(self, **kw):
        return SaveKitService(self.kits, self.files).execute("me", CONTENT, None, json.dumps(kit_payload(**kw)))

    def test_save_validates_and_checks_owner(self):
        r = self._save()
        self.assertEqual(r["summary"]["videos"], 6)
        self.assertEqual(self.kits.rows[r["name"]]["status"], C.KitStatus.DRAFT)
        self.assertEqual(len(self.kits.rows[r["name"]]["faq"]), 1)                 # dong chu de rong bi bo
        with self.assertRaises(C.AiLiveError):
            self._save(products=[{"id": "sp01", "main_free": [V("other.mp3")]}])  # file cua nguoi khac
        with self.assertRaises(C.AiLivePermission):
            SaveKitService(self.kits, self.files).execute("me", ["Guest"], None, kit_payload())
        for bad in ({"brand": ""}, {"brand": "Friso"}, {"mode": "x"}, {"break_sec": 15}, {"background": "/f/x.gif"}):
            with self.assertRaises(C.AiLiveError, msg=str(bad)):
                self._save(**bad)
        # file nguoi khac nhung DA nam trong Bo live (do dong nghiep them) thi van luu duoc
        self.kits.rows[r["name"]]["generic"]["thanks"] = [V("other.mp3")]
        SaveKitService(self.kits, self.files).execute("me", CONTENT, r["name"], kit_payload(generic={"greet": [], "thanks": [V("other.mp3")]}))

    def test_build_send_and_status(self):
        name = self._save(background="/private/files/bg.png", bake_bg=1)["name"]
        q = []
        StartBuildKitService(self.kits, enqueue=q.append).execute(CONTENT, name)
        self.assertEqual((q, self.kits.rows[name]["status"]), ([name], C.KitStatus.SENDING))
        with self.assertRaises(C.AiLiveError):
            StartBuildKitService(self.kits, enqueue=q.append).execute(CONTENT, name)    # dang gui
        w = FakeWorker(fail_upload_at=2)
        r = SendKitService(self.kits, self.files, w, FakeBrands()).execute(name)
        self.assertIn("error", r)
        self.assertEqual(self.kits.rows[name]["status"], C.KitStatus.ERROR)
        self.assertEqual(len(self.kits.rows[name]["state"]["rels"]), 2)                 # 2 file da gui duoc giu lai
        StartBuildKitService(self.kits, enqueue=q.append).execute(CONTENT, name)
        w2 = FakeWorker()
        r = SendKitService(self.kits, self.files, w2, FakeBrands()).execute(name)
        self.assertEqual(r, {"tasks": 1})
        self.assertEqual(len(w2.uploads), 5)                                              # 4 voice con lai + nen
        step = w2.calls[-1][1]["steps"][0]
        self.assertEqual(w2.calls[-1][1]["batch_id"], "kit_" + name)
        self.assertEqual((step["op"], step["brand_name"], step["bake_bg"], len(step["products"][0]["main_free"])), ("build_kit", "Friso", True, 2))
        k = self.kits.rows[name]
        self.assertEqual((k["status"], k["state"]["kit_folder"]), (C.KitStatus.BUILDING, "G:\\AI Live\\friso"))
        self.assertEqual(SendKitService(self.kits, self.files, w2, FakeBrands()).execute(name), {"skipped": True})
        w2.tasks = [{"id": "T0", "state": "running"}]
        d = GetKitService(self.kits, w2).execute(CONTENT, name, tick=True)
        self.assertEqual((d["status"], d["state"]["progress"]["running"]), (C.KitStatus.BUILDING, 1))
        self.assertNotIn("rels", d["state"])
        w2.tasks = [{"id": "T0", "state": "done"}, {"id": "OTHER", "state": "failed"}]
        self.assertEqual(GetKitService(self.kits, w2).execute(CONTENT, name, tick=True)["status"], C.KitStatus.DONE)
        with self.assertRaises(C.AiLiveError):
            SaveKitService(self.kits, self.files).execute("me", CONTENT, "nope", kit_payload())

    def test_build_requires_host_and_voice(self):
        name = self._save(host_key="")["name"]
        with self.assertRaises(C.AiLiveError):
            StartBuildKitService(self.kits, enqueue=lambda n: None).execute(CONTENT, name)
        name = self._save(products=[], faq=[], generic={})["name"]
        with self.assertRaises(C.AiLiveError):
            StartBuildKitService(self.kits, enqueue=lambda n: None).execute(CONTENT, name)


class TestHostServices(unittest.TestCase):
    def test_list_and_studio_flow(self):
        w, labels = FakeWorker(), FakeLabels()
        d = ListHostsService(w, labels).execute(CONTENT)
        self.assertEqual((d["hosts"][0]["label"], d["hosts"][0]["talks"]), ("Linh", 81))
        self.assertEqual(d["motion_cost"]["clips"], 20)
        r = HostImageService(w, FakeFiles(), labels).execute("me", CONTENT, {"prompt": "MC nữ", "model": "nano-banana-full",
                                                                               "refs": ["/private/files/r1.png"], "label": "Mai"})
        host = r["host"]
        self.assertRegex(host, C.HOST_RE.pattern)
        self.assertEqual((r["cost"]["credits"], labels.d[host], len(w.uploads)), (40, "Mai", 1))
        step = w.calls[-1][1]["steps"][0]
        self.assertEqual((step["op"], step["n"], step["refs"]), ("host_image", 4, ["ecv6/inbox/%s/ref_1.png" % host]))
        with self.assertRaises(C.AiLiveError):
            HostImageService(w, FakeFiles(), labels).execute("me", CONTENT, {"prompt": " ", "model": "nano-banana-full"})
        with self.assertRaises(C.AiLiveError):
            HostImageService(w, FakeFiles(), labels).execute("me", CONTENT, {"prompt": "x", "model": "nano-banana-full", "refs": ["/f/other.png"]})
        w.tasks = [{"id": "a", "state": "done", "out": "ecv6/hosts/%s/anchor_c3.png" % host}, {"id": "b", "state": "running"}]
        s = HostImageStatusService(w).execute(CONTENT, host)
        self.assertEqual((s["items"][0]["cand"], s["items"][1]["thumb"], s["done"]), (3, None, False))
        r = HostSaveService(w, labels).execute(CONTENT, host, "3", "Mai 2")
        self.assertEqual((w.calls[-1], labels.d[host]), (("anchor_pick", {"host": host, "cand": 3}), "Mai 2"))
        for bad in ((host, 0), (host, "x"), ("H_bad", 1)):
            with self.assertRaises(C.AiLiveError):
                HostSaveService(w, labels).execute(CONTENT, *bad)

    def test_motion_set(self):
        w = FakeWorker()
        r = MotionSetService(w).execute(CONTENT, "H_BOO3HGI9JF", json.dumps([{"dur": 10, "n": 4}, {"dur": 4, "n": 2}]), dry_run=True)
        self.assertEqual((r["cost"]["seconds"], r["queued"], w.calls), (48, 0, []))
        r = MotionSetService(w).execute(CONTENT, "H_BOO3HGI9JF", None, dry_run=False)
        self.assertEqual((r["queued"], w.calls[-1][1]["steps"][0]["op"], w.calls[-1][1]["batch_id"]), (1, "motion_set", "ms_H_BOO3HGI9JF"))
        with self.assertRaises(C.AiLiveError):
            MotionSetService(w).execute(CONTENT, "H_NOT_THERE", None, dry_run=False)


if __name__ == "__main__":
    unittest.main()
