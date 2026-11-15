# Copyright (c) 2026, eCentric and contributors
"""Giong doc AI: service chay ngoai Frappe voi kho gia + may eVoice gia. Di het vong doi phieu
(tao -> gui -> callback / poll -> tai MP3 -> nghe / xoa) va cac kich ban loi: may tat, tunnel 524,
hang doi day, token sai, may khoi dong lai mat phieu, callback gia / lap / den tre, huy luc dang chay.
    python -m unittest ecentric_workspace.ai_tools.tests.test_ai_voice_service"""
import datetime
import itertools
import json
import unittest

from ecentric_workspace.ai_tools.features.ai_voice import constants as C
from ecentric_workspace.ai_tools.features.ai_voice.application.add_voice_service import AddVoiceService
from ecentric_workspace.ai_tools.features.ai_voice.application.audio_service import AudioService
from ecentric_workspace.ai_tools.features.ai_voice.application.cancel_job_service import CancelJobService
from ecentric_workspace.ai_tools.features.ai_voice.application.create_job_service import CreateJobService
from ecentric_workspace.ai_tools.features.ai_voice.application.delete_job_service import DeleteJobService
from ecentric_workspace.ai_tools.features.ai_voice.application.fetch_audio_service import FetchAudioService
from ecentric_workspace.ai_tools.features.ai_voice.application.get_state_service import GetStateService
from ecentric_workspace.ai_tools.features.ai_voice.application.handle_callback_service import (
    BadSignature, HandleCallbackService)
from ecentric_workspace.ai_tools.features.ai_voice.application.list_jobs_service import ListJobsService
from ecentric_workspace.ai_tools.features.ai_voice.application.machine_status_service import MachineStatusService
from ecentric_workspace.ai_tools.features.ai_voice.application.poll_jobs_service import PollJobsService
from ecentric_workspace.ai_tools.features.ai_voice.application.remove_voice_service import RemoveVoiceService
from ecentric_workspace.ai_tools.features.ai_voice.application.settings_service import SettingsService
from ecentric_workspace.ai_tools.features.ai_voice.application.submit_job_service import SubmitJobService
from ecentric_workspace.ai_tools.features.ai_voice.application.sync_voices_service import SyncVoicesService
from ecentric_workspace.ai_tools.features.ai_voice.application.update_voice_service import UpdateVoiceService
from ecentric_workspace.ai_tools.features.ai_voice.application.upload_voice_service import UploadVoiceService
from ecentric_workspace.ai_tools.features.ai_voice.domain import rules as R
from ecentric_workspace.ai_tools.features.ai_voice.infrastructure.evoice_client import EVoiceDown, EVoiceHttpError

U, U2, M, A = "u@x", "u2@x", "m@x", "admin@x"
UR, MR, AR = ("EC AI Voice User",), ("EC AI Voice Manager",), ("System Manager",)


# ------------------------------------------------------------------ kho gia ---
class Clock:
    def __init__(self):
        self.t = datetime.datetime(2026, 11, 15, 9, 0, 0)

    def __call__(self):
        return self.t

    def adv(self, s):
        self.t += datetime.timedelta(seconds=s)

    def s(self):
        return self.t.strftime("%Y-%m-%d %H:%M:%S")


class Jobs:
    def __init__(self, clock, user):
        self.rows, self.clock, self.user, self.seq = {}, clock, user, itertools.count(1)

    def _touch(self, d):
        d["modified"] = self.clock.s()

    def insert(self, v):
        n = "J%d" % next(self.seq)
        d = dict(v, name=n, owner=self.user[0], creation=self.clock.s(), attempts=0, fetch_attempts=0, cancel_requested=0,
                 audio_file=None, evoice_job_id=None, position=0)
        self._touch(d)
        self.rows[n] = d
        return n

    def get(self, name, for_update=False):
        r = self.rows.get(name)
        return dict(r) if r else None

    def find_by_remote_id(self, rid, for_update=False):
        for r in self.rows.values():
            if rid and r.get("evoice_job_id") == rid:
                return dict(r)
        return None

    def update(self, name, values):
        self.rows[name].update({k: (v.strftime("%Y-%m-%d %H:%M:%S") if isinstance(v, datetime.datetime) else v)
                                for k, v in values.items()})
        self._touch(self.rows[name])

    def delete(self, name):
        self.rows.pop(name)

    def list(self, owner=None, statuses=None, limit=50, start=0):
        rows = [dict(r) for r in reversed(list(self.rows.values()))
                if (not owner or r["owner"] == owner) and (not statuses or r["status"] in statuses)]
        return rows[start:start + limit]

    def count_active(self, owner):
        return len([r for r in self.rows.values() if r["owner"] == owner and r["status"] in C.JobStatus.ACTIVE])

    def active_names(self):
        return [n for n, r in self.rows.items()
                if r["status"] in C.JobStatus.ACTIVE or (r["status"] == C.JobStatus.DONE and not r.get("audio_file"))]


class Profiles:
    def __init__(self, clock):
        self.rows, self.clock, self.seq = {}, clock, itertools.count(1)

    def add(self, **v):
        n = "P%d" % next(self.seq)
        base = {"name": n, "voice_name": "Giọng " + n, "status": "active", "voice_id": "v" + n, "restricted": 0,
                "missing_on_server": 0, "source": "erp", "gender": "Nữ", "modified": self.clock.s(), "creation": self.clock.s()}
        base.update(v)
        self.rows[n] = base
        return n

    def list(self, include_inactive=False):
        return [dict(r) for r in self.rows.values() if include_inactive or r["status"] == "active"]

    def get(self, name):
        r = self.rows.get(name)
        return dict(r) if r else None

    def get_by_voice_id(self, vid):
        return next((dict(r) for r in self.rows.values() if r.get("voice_id") == vid), None)

    def known_voice_ids(self):
        return {r["voice_id"] for r in self.rows.values() if r.get("voice_id")}

    def insert(self, v):
        return self.add(**dict({"voice_id": ""}, **{k: (x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime.datetime) else x)
                                                    for k, x in v.items()}))

    def update(self, name, v):
        self.rows[name].update({k: (x.strftime("%Y-%m-%d %H:%M:%S") if isinstance(x, datetime.datetime) else x) for k, x in v.items()})
        self.rows[name]["modified"] = self.clock.s()

    def delete(self, name):
        self.rows.pop(name)

    def lock(self, name):
        r = self.rows.get(name)
        return r and r["status"]


class Settings:
    def __init__(self, token="tok"):
        self.d = {"base_url": "https://voice.x", "token": token, "default_quality": "", "default_speed": None, "timeout": 30,
                  "callback_base_url": "", "last_check_at": "", "last_check_result": ""}
        self.saved = []

    def get(self, with_token=False):
        d = dict(self.d, token_set=bool(self.d["token"]))
        if not with_token:
            d.pop("token")
        return d

    def save(self, values, token=None):
        self.d.update(values)
        if token is not None:
            self.d["token"] = token
        self.saved.append((values, token))

    def mark_check(self, r):
        self.d["last_check_result"] = r

    def site_url(self):
        return "https://team.ecentric.vn"


class Files:
    def __init__(self):
        self.store, self.meta = {}, {}

    def put(self, url, content, owner, name=None):
        self.store[url], self.meta[url] = content, {"name": url, "owner": owner, "file_name": name or url.split("/")[-1], "size": len(content)}

    def info(self, url):
        return dict(self.meta[url]) if url in self.meta else None

    def content(self, url):
        return self.store.get(url)

    def save(self, file_name, content, doctype, docname, fieldname=None):
        url = "/private/files/" + file_name
        self.put(url, content, "Administrator")
        return url

    def delete(self, url):
        self.store.pop(url, None)
        self.meta.pop(url, None)


class Machine:
    """May eVoice gia: hang loi lap trinh duoc theo ten ham."""

    def __init__(self):
        self.fail, self.calls, self.jobs, self.voices_list, self.n = {}, [], {}, [], itertools.count(1)
        self.audio = (b"ID3mp3data", "audio/mpeg")

    def __call__(self, timeout=None):
        return self

    def _hit(self, fn, *a):
        self.calls.append((fn,) + a)
        e = self.fail.get(fn)
        if isinstance(e, list):
            e = e.pop(0) if e else None
        if e:
            raise e

    def health(self):
        self._hit("health")
        return {"ready": True, "voices": 3, "engine": "PerfectVoice"}

    def brands(self):
        self._hit("brands")
        return [{"name": "Lix", "current": "v1", "current_name": "Lan"}, {"name": "NoVoice", "current": None},
                {"name": "Lạ", "current": "v-la", "current_name": "Giọng chưa có trên ERP"}]

    def voices(self):
        self._hit("voices")
        return list(self.voices_list)

    def create_job(self, payload):
        self._hit("create_job", payload)
        jid = "r%d" % next(self.n)
        self.jobs[jid] = payload
        return {"id": jid, "status": "queued", "position": 2}

    def get_job(self, jid):
        self._hit("get_job", jid)
        return {"id": jid, "status": "running", "progress": "1/3"}

    def delete_job(self, jid):
        self._hit("delete_job", jid)
        return {"ok": True}

    def job_audio(self, jid):
        self._hit("job_audio", jid)
        return self.audio

    def voice_sample(self, vid):
        self._hit("voice_sample", vid)
        return b"RIFFwav", "audio/wav"

    def create_voice(self, payload, timeout):
        self._hit("create_voice", payload)
        return {"id": "nv1", "ref_text": "xin chào", "clip_seconds": 9.5}

    def delete_voice(self, vid):
        self._hit("delete_voice", vid)
        return {"ok": True}


class Cache:
    def __init__(self):
        self.d = {}

    def get_value(self, k):
        return self.d.get(k)

    def set_value(self, k, v, expires_in_sec=None):
        self.d[k] = v

    def delete_value(self, k):
        self.d.pop(k, None)


class World(unittest.TestCase):
    def setUp(self):
        self.clock, self.me = Clock(), [U]
        self.jobs, self.profiles, self.settings = Jobs(self.clock, self.me), Profiles(self.clock), Settings()
        self.files, self.machine, self.cache = Files(), Machine(), Cache()
        self.enq, self.pub, self.committed = [], [], []
        self.p1 = self.profiles.add(voice_name="Lan", voice_id="v1", consent_by="Lan", consent_date="2026-11-01")

    def enqueue(self, mod, **kw):
        self.enq.append((mod, kw))

    def after(self, fn):
        self.committed.append(fn)
        fn()

    def publish(self, user, job):
        self.pub.append((user, job))

    def kw(self):
        return dict(jobs=self.jobs, settings=self.settings, client=self.machine, now=self.clock, publish=self.publish)

    def create(self, roles=UR, **over):
        payload = dict(text="Xin chào cả nhà", voice="profile:" + self.p1, quality="quality_fast", speed=1.1, language="vi")
        payload.update(over)
        return CreateJobService(jobs=self.jobs, profiles=self.profiles, enqueue=self.enqueue, settings=self.settings,
                                client=self.machine).execute(self.me[0], roles, payload)

    def submit(self, name):
        return SubmitJobService(**self.kw()).execute(name)

    def poll(self):
        svc = PollJobsService(**dict(self.kw(), submit=None, fetch=self.fetcher()))
        return {n: svc.process(n) for n in svc.targets()}

    def fetcher(self):
        return FetchAudioService(files=self.files, after_commit=self.after, **self.kw())

    def callback(self, body, token="tok", sig=None):
        raw = json.dumps(body).encode()
        return HandleCallbackService(jobs=self.jobs, settings=self.settings, enqueue=self.enqueue, now=self.clock,
                                     publish=self.publish).execute(raw, sig if sig is not None else R.sign(token, raw))


# ------------------------------------------------------------------ vong doi ---
class TestHappyPath(World):
    def test_create_submit_callback_fetch_play_delete(self):
        j = self.create()
        self.assertEqual(j["status"], "pending")
        self.assertEqual(self.enq[-1], ("submit_job_job", {"name": j["name"]}))
        self.assertEqual(self.submit(j["name"]), "submitted")
        row = self.jobs.rows[j["name"]]
        self.assertEqual((row["status"], row["evoice_job_id"], row["position"]), ("queued", "r1", 2))
        sent = self.machine.jobs["r1"]
        self.assertEqual((sent["voice"], sent["ref"]), ("v1", j["name"]))
        self.assertEqual(sent["callback_url"], "https://team.ecentric.vn" + C.CALLBACK_METHOD)
        self.assertEqual(self.callback({"id": "r1", "ref": j["name"], "status": "running", "progress": "1/2"}), "ok")
        self.assertEqual(self.callback({"id": "r1", "ref": j["name"], "status": "done", "seconds": 4.2}), "ok")
        self.assertEqual(self.enq[-1], ("fetch_audio_job", {"name": j["name"]}))
        self.assertEqual(self.fetcher().execute(j["name"]), "saved")
        row = self.jobs.rows[j["name"]]
        self.assertTrue(row["audio_file"].endswith(".mp3"))
        self.assertIn(("delete_job", "r1"), self.machine.calls, "don file ben may sau khi luu ERP")
        fname, content, mime = AudioService(jobs=self.jobs, profiles=self.profiles, settings=self.settings,
                                            files=self.files, client=self.machine).job_audio(U, UR, j["name"])
        self.assertEqual((content, mime), (b"ID3mp3data", "audio/mpeg"))
        self.assertTrue(fname.endswith(".mp3") and "/" not in fname)
        self.assertEqual(self.pub[-1][0], U, "bao realtime dung chu phieu")
        DeleteJobService(jobs=self.jobs, files=self.files).execute(U, UR, j["name"])
        self.assertNotIn(j["name"], self.jobs.rows)
        self.assertNotIn(row["audio_file"], self.files.store, "xoa phieu xoa ca file MP3")

    def test_callback_base_override(self):
        self.settings.d["callback_base_url"] = "https://erp-public.x"
        j = self.create()
        self.submit(j["name"])
        self.assertTrue(self.machine.jobs["r1"]["callback_url"].startswith("https://erp-public.x/api/method/"))

    def test_brand_voice(self):
        j = self.create(voice="brand:Lix")
        self.submit(j["name"])
        self.assertEqual(self.machine.jobs["r1"]["voice"], "v1", "khoa vao dung ma giong brand dang dung luc tao")
        self.assertIn("Lix", j["voice_label"])
        self.assertEqual(self.jobs.rows[j["name"]]["voice_profile"], self.p1)

    def test_brand_voice_rules(self):
        with self.assertRaises(C.AiVoiceError, msg="giong brand chua co tren ERP / chua dong y"):
            self.create(voice="brand:Lạ")
        with self.assertRaises(C.AiVoiceError):
            self.create(voice="brand:NoVoice")
        with self.assertRaises(C.AiVoiceError):
            self.create(voice="brand:KhongCo")
        self.profiles.rows[self.p1].update(restricted=1, owner_user="o@x")
        with self.assertRaises(C.AiVoicePermission, msg="giong han che khong lach qua brand: duoc"):
            self.create(voice="brand:Lix")
        self.profiles.rows[self.p1].update(restricted=0, consent_by="")
        with self.assertRaises(C.AiVoiceError, msg="thieu dong y -> khong dung qua brand"):
            self.create(voice="brand:Lix")
        self.profiles.rows[self.p1]["consent_by"] = "Lan"
        self.machine.fail["brands"] = EVoiceDown("x")
        with self.assertRaises(C.AiVoiceError):
            self.create(voice="brand:Lix")
        self.assertEqual(self.jobs.rows, {})


# ------------------------------------------------------------------ tao phieu: kiem dau vao ---
class TestCreateValidation(World):
    def test_permission(self):
        with self.assertRaises(C.AiVoicePermission):
            self.create(roles=("Employee",))

    def test_bad_inputs(self):
        for over in ({"text": ""}, {"text": "!!!"}, {"text": "a" * (C.MAX_CHARS + 1)}, {"voice": ""}, {"voice": "x:1"},
                     {"voice": "brand:"}, {"voice": "brand:" + "x" * 81}, {"voice": "profile:NOPE"}, {"quality": "zz"},
                     {"speed": "9"}, {"language": "klingon"}):
            with self.assertRaises(C.AiVoiceError, msg=str(over)):
                self.create(**over)
        self.assertEqual(self.jobs.rows, {}, "dau vao sai khong de lai phieu rac")
        self.assertEqual(self.enq, [])

    def test_disabled_restricted_processing_voices(self):
        off = self.profiles.add(status="disabled")
        busy = self.profiles.add(status="processing", voice_id="")
        priv = self.profiles.add(restricted=1, owner_user="o@x")
        with self.assertRaises(C.AiVoiceError):
            self.create(voice="profile:" + off)
        with self.assertRaises(C.AiVoiceError):
            self.create(voice="profile:" + busy)
        with self.assertRaises(C.AiVoicePermission):
            self.create(voice="profile:" + priv)
        self.me[0] = "o@x"
        self.assertEqual(self.create(voice="profile:" + priv)["status"], "pending")

    def test_active_limit(self):
        for _ in range(C.MAX_ACTIVE_PER_USER):
            self.create()
        with self.assertRaises(C.AiVoiceError):
            self.create()
        self.me[0] = U2
        self.create()  # nguoi khac van tao duoc

    def test_breath_and_title(self):
        j = self.create(breath="0", title="")
        row = self.jobs.rows[j["name"]]
        self.assertEqual(row["breath"], 0)
        self.assertEqual(row["title"], "Xin chào cả nhà")
        self.assertEqual(self.create(breath=None)["name"] and self.jobs.rows["J2"]["breath"], 1)


# ------------------------------------------------------------------ gui sang may: loi ---
class TestSubmitFailures(World):
    def test_machine_down_retries_then_gives_up(self):
        j = self.create()
        self.machine.fail["create_job"] = EVoiceDown("HTTP 530")
        for k in range(C.SUBMIT_MAX_ATTEMPTS - 1):
            self.assertEqual(self.submit(j["name"]), "retry")
            self.assertEqual(self.jobs.rows[j["name"]]["status"], "pending")
        self.assertEqual(self.submit(j["name"]), "gave_up")
        row = self.jobs.rows[j["name"]]
        self.assertEqual(row["status"], "error")
        self.assertIn("530", row["error"])

    def test_queue_full_and_bad_token_retry(self):
        j = self.create()
        self.machine.fail["create_job"] = [EVoiceHttpError(429, "Hàng đợi đầy"), EVoiceHttpError(401, "bad token")]
        self.assertEqual(self.submit(j["name"]), "retry")
        self.assertEqual(self.submit(j["name"]), "retry")
        self.assertIn("token", self.jobs.rows[j["name"]]["last_error"])
        self.assertEqual(self.submit(j["name"]), "submitted")

    def test_rejected_payload_fails_fast(self):
        j = self.create()
        self.machine.fail["create_job"] = EVoiceHttpError(400, "Giọng không tồn tại")
        self.assertEqual(self.submit(j["name"]), "error")
        self.assertEqual(self.jobs.rows[j["name"]]["error"], "Giọng không tồn tại")

    def test_not_configured(self):
        j = self.create()

        def nocfg(timeout=None):
            raise C.AiVoiceError(C.Msg.NOT_CONFIGURED)
        r = SubmitJobService(jobs=self.jobs, settings=self.settings, client=nocfg, now=self.clock, publish=self.publish).execute(j["name"])
        self.assertEqual(r, "retry")

    def test_idempotent_and_cancel_before_send(self):
        j = self.create()
        self.assertEqual(self.submit(j["name"]), "submitted")
        self.assertEqual(self.submit(j["name"]), "skip", "job nen chay 2 lan khong gui trung")
        self.assertEqual(len(self.machine.jobs), 1)
        j2 = self.create()
        self.jobs.update(j2["name"], {"cancel_requested": 1})
        self.assertEqual(self.submit(j2["name"]), "cancelled")
        self.assertEqual(len(self.machine.jobs), 1)

    def test_missing_remote_id(self):
        j = self.create()
        self.machine.create_job = lambda payload: {"status": "queued"}
        self.assertEqual(self.submit(j["name"]), "retry")


# ------------------------------------------------------------------ callback ---
class TestCallback(World):
    def setUp(self):
        super().setUp()
        self.j = self.create()
        self.submit(self.j["name"])

    def test_forged_signature(self):
        with self.assertRaises(BadSignature):
            self.callback({"id": "r1", "status": "done"}, token="wrong")
        with self.assertRaises(BadSignature):
            self.callback({"id": "r1", "status": "done"}, sig="")
        self.assertEqual(self.jobs.rows[self.j["name"]]["status"], "queued")

    def test_no_token_rejects_everything(self):
        self.settings.d["token"] = ""
        with self.assertRaises(BadSignature):
            self.callback({"id": "r1", "status": "done"}, token="")

    def test_unknown_ref_mismatch_badjson(self):
        self.assertEqual(self.callback({"id": "nope", "status": "done"}), "unknown")
        self.assertEqual(self.callback({"id": "r1", "ref": "J999", "status": "done"}), "ref_mismatch")
        raw = b"not json"
        svc = HandleCallbackService(jobs=self.jobs, settings=self.settings, enqueue=self.enqueue, now=self.clock, publish=self.publish)
        self.assertEqual(svc.execute(raw, R.sign("tok", raw)), "bad_json")
        raw = b"[1,2]"
        self.assertEqual(svc.execute(raw, R.sign("tok", raw)), "bad_json")
        self.assertEqual(self.jobs.rows[self.j["name"]]["status"], "queued")

    def test_duplicate_and_late(self):
        self.assertEqual(self.callback({"id": "r1", "status": "done"}), "ok")
        n = len(self.enq)
        self.assertEqual(self.callback({"id": "r1", "status": "done"}), "stale", "callback lap khong tai lai")
        self.assertEqual(self.callback({"id": "r1", "status": "running"}), "stale", "den tre khong keo lui")
        self.assertEqual(len(self.enq), n)

    def test_error(self):
        self.callback({"id": "r1", "status": "error", "error": "CUDA out of memory"})
        row = self.jobs.rows[self.j["name"]]
        self.assertEqual((row["status"], row["error"]), ("error", "CUDA out of memory"))
        self.assertTrue(row["finished_at"])


# ------------------------------------------------------------------ poll (luoi an toan) ---
class TestPoll(World):
    def test_pending_backoff(self):
        j = self.create()
        self.assertEqual(self.poll()[j["name"]], "wait", "phieu vua tao: de job gui ngay lo, poll khong gui trung")
        self.clock.adv(91)
        self.machine.fail["create_job"] = EVoiceDown("x")
        self.assertEqual(self.poll()[j["name"]], "retry")
        self.clock.adv(60)
        self.assertEqual(self.poll()[j["name"]], "wait")       # chua toi 2 phut
        self.clock.adv(61)
        self.machine.fail.clear()
        self.assertEqual(self.poll()[j["name"]], "submitted")
    def test_grace_then_query(self):
        j = self.create()
        self.submit(j["name"])
        self.assertEqual(self.poll()[j["name"]], "wait")
        self.clock.adv(C.POLL_GRACE_SECONDS + 1)
        self.assertEqual(self.poll()[j["name"]], "running")
        self.assertEqual(self.jobs.rows[j["name"]]["progress"], "1/3")

    def test_machine_restart_loses_job(self):
        j = self.create()
        self.submit(j["name"])
        self.clock.adv(120)
        self.machine.fail["get_job"] = EVoiceHttpError(404, "Not found")
        self.poll()
        row = self.jobs.rows[j["name"]]
        self.assertEqual((row["status"], row["error"]), ("error", C.Msg.LOST))

    def test_machine_down_keeps_waiting(self):
        j = self.create()
        self.submit(j["name"])
        self.clock.adv(120)
        self.machine.fail["get_job"] = EVoiceDown("HTTP 502")
        self.assertEqual(self.poll()[j["name"]], "down")
        self.assertEqual(self.jobs.rows[j["name"]]["status"], "queued")

    def test_timeout(self):
        j = self.create()
        self.submit(j["name"])
        self.clock.adv(C.RUNNING_TIMEOUT_SECONDS + 10)
        self.assertEqual(self.poll()[j["name"]], "running", "nam hang doi lau (gio live) chua bi coi la qua han")
        self.assertTrue(self.jobs.rows[j["name"]]["started_at"])
        self.clock.adv(C.RUNNING_TIMEOUT_SECONDS + 10)
        self.poll()
        self.assertEqual(self.jobs.rows[j["name"]]["error"], C.Msg.TIMEOUT)
        self.assertIn(("delete_job", "r1"), self.machine.calls)
        j2 = self.create()
        self.submit(j2["name"])
        self.clock.adv(C.QUEUED_TIMEOUT_SECONDS + 10)
        self.poll()
        self.assertEqual(self.jobs.rows[j2["name"]]["error"], C.Msg.TIMEOUT)

    def test_circuit_breaker(self):
        names = [self.create()["name"] for _ in range(3)]
        for n in names:
            self.submit(n)
        self.clock.adv(120)
        self.machine.fail["get_job"] = EVoiceDown("slow")
        out = self.poll()
        self.assertEqual(list(out.values()), ["down", "down", "down"])
        self.assertEqual(len([c for c in self.machine.calls if c[0] == "get_job"]), 1, "may hong: chi thu 1 lan / luot")
    def test_done_via_poll_downloads(self):
        j = self.create()
        self.submit(j["name"])
        self.clock.adv(120)
        self.machine.get_job = lambda jid: {"id": jid, "status": "done", "seconds": 3}
        self.assertEqual(self.poll()[j["name"]], "saved")
        self.assertTrue(self.jobs.rows[j["name"]]["audio_file"])
        self.assertEqual(self.poll(), {}, "xong roi khong poll nua")

    def test_fetch_retries_then_gives_up_and_404(self):
        j = self.create()
        self.submit(j["name"])
        self.callback({"id": "r1", "status": "done"})
        self.machine.fail["job_audio"] = EVoiceDown("reset")
        f = self.fetcher()
        self.assertEqual(f.execute(j["name"]), "retry")
        self.assertEqual(self.poll()[j["name"]], "wait", "tai lai gian dan, khong moi 2 phut")
        self.clock.adv(10 * 3600)
        self.assertEqual(f.execute(j["name"]), "retry", "10 gio sau van con thu (may giu file 24 gio)")
        self.clock.adv(14 * 3600)
        self.assertEqual(f.execute(j["name"]), "error")
        self.assertIn("Không tải được", self.jobs.rows[j["name"]]["error"])
        j2 = self.create()
        self.submit(j2["name"])
        self.callback({"id": "r2", "status": "done"})
        self.machine.fail["job_audio"] = EVoiceHttpError(404, "gone")
        self.assertEqual(f.execute(j2["name"]), "error")
        self.assertEqual(self.jobs.rows[j2["name"]]["error"], C.Msg.LOST)

    def test_remote_delete_only_after_commit(self):
        j = self.create()
        self.submit(j["name"])
        self.callback({"id": "r1", "status": "done"})
        f = FetchAudioService(files=self.files, after_commit=lambda fn: None, **self.kw())   # commit chua xay ra
        self.assertEqual(f.execute(j["name"]), "saved")
        self.assertNotIn(("delete_job", "r1"), self.machine.calls)
        self.assertEqual(self.fetcher().execute(j["name"]), "skip", "da co file -> khong tai lai")


# ------------------------------------------------------------------ huy / xoa / xem ---
class TestCancelDelete(World):
    def test_cancel_pending_queued_running(self):
        a = self.create()
        self.assertEqual(CancelJobService(**self._ck()).execute(U, UR, a["name"])["status"], "cancelled")
        b = self.create()
        self.submit(b["name"])
        self.assertEqual(CancelJobService(**self._ck()).execute(U, UR, b["name"])["status"], "cancelled",
                         "phieu trong hang doi: may bo luon, khong co callback -> huy ngay")
        c = self.create()
        self.submit(c["name"])
        self.callback({"id": "r2", "status": "running"})
        out = CancelJobService(**self._ck()).execute(U, UR, c["name"])
        self.assertEqual((out["status"], out["cancel_requested"]), ("running", 1), "dang doc: cho may bao cancelled")
        self.callback({"id": "r2", "status": "cancelled"})
        self.assertEqual(self.jobs.rows[c["name"]]["status"], "cancelled")

    def test_cancel_when_machine_down_then_poll(self):
        b = self.create()
        self.submit(b["name"])
        self.machine.fail["delete_job"] = EVoiceDown("x")
        out = CancelJobService(**self._ck()).execute(U, UR, b["name"])
        self.assertEqual((out["status"], out["error"]), ("cancelled", C.Msg.CANCELLED_OFFLINE),
                         "may mat ket noi: huy ngay tren ERP, khong treo 3 gio")
        self.assertEqual(self.jobs.count_active(U), 0, "khong con chiem suat 10 phieu")
        self.assertEqual(self.callback({"id": "r1", "status": "done"}), "stale", "may van doc xong: bo qua")
    def test_cancel_rules(self):
        a = self.create()
        self.me[0] = U2
        with self.assertRaises(C.AiVoicePermission):
            CancelJobService(**self._ck()).execute(U2, UR, a["name"])
        CancelJobService(**self._ck()).execute(M, MR, a["name"])
        with self.assertRaises(C.AiVoiceError):
            CancelJobService(**self._ck()).execute(M, MR, a["name"])
        with self.assertRaises(C.AiVoiceError):
            CancelJobService(**self._ck()).execute(M, MR, "NOPE")

    def test_delete_rules(self):
        a = self.create()
        d = DeleteJobService(jobs=self.jobs, files=self.files)
        with self.assertRaises(C.AiVoiceError):
            d.execute(U, UR, a["name"])     # dang chay
        self.jobs.update(a["name"], {"status": "error"})
        with self.assertRaises(C.AiVoicePermission):
            d.execute(U2, UR, a["name"])
        d.execute(M, MR, a["name"])

    def test_list_scope_and_text(self):
        self.create()
        self.me[0] = U2
        self.create(text="bí mật của u2")
        L = ListJobsService(jobs=self.jobs)
        self.assertEqual(len(L.execute(U, UR)["jobs"]), 1)
        self.assertEqual(L.execute(U, UR, scope="all")["scope"], "mine", "nguoi thuong khong xem duoc moi phieu")
        self.assertEqual(len(L.execute(M, MR, scope="all")["jobs"]), 2)
        self.assertNotIn("text", L.execute(M, MR, scope="all")["jobs"][0], "danh sach khong tra noi dung")
        with self.assertRaises(C.AiVoicePermission):
            L.get(U, UR, "J2")
        self.assertEqual(L.get(U2, UR, "J2")["text"], "bí mật của u2")
        page = L.execute(M, MR, scope="all", limit=1)
        self.assertTrue(page["more"])
        self.assertEqual(L.execute(U, UR, status="active")["jobs"][0]["status"], "pending")
        self.assertEqual(L.execute(U, UR, limit="abc")["jobs"][0]["name"], "J1")

    def test_audio_access(self):
        a = self.create()
        au = AudioService(jobs=self.jobs, profiles=self.profiles, settings=self.settings, files=self.files, client=self.machine)
        with self.assertRaises(C.AiVoiceError):
            au.job_audio(U, UR, a["name"])     # chua co file
        self.jobs.update(a["name"], {"status": "done", "audio_file": "/private/files/x.mp3"})
        self.files.put("/private/files/x.mp3", b"mp3", "Administrator")
        with self.assertRaises(C.AiVoicePermission):
            au.job_audio(U2, UR, a["name"])
        self.assertEqual(au.job_audio(M, MR, a["name"])[1], b"mp3")

    def _ck(self):
        return dict(jobs=self.jobs, settings=self.settings, client=self.machine, now=self.clock)


# ------------------------------------------------------------------ thu vien giong ---
class TestVoices(World):
    def add_kw(self):
        return dict(profiles=self.profiles, files=self.files, enqueue=self.enqueue, now=self.clock)

    def payload(self, **over):
        self.files.put("/private/files/lan.wav", b"RIFF" + b"0" * 100, M, "lan.wav")
        p = dict(voice_name="Lan Mới", gender="Nữ", sample_url="/private/files/lan.wav", consent_by="Lan",
                 consent_date="2026-11-10", consent_confirmed=1)
        p.update(over)
        return p

    def test_add_upload_active(self):
        v = AddVoiceService(**self.add_kw()).execute(M, MR, self.payload())
        self.assertEqual((v["status"], v["has_consent"]), ("processing", True))
        self.assertEqual(self.enq[-1][0], "upload_voice_job")
        self.assertEqual(self.enq[-1][1]["queue"], "long")
        up = UploadVoiceService(profiles=self.profiles, settings=self.settings, files=self.files, client=self.machine, now=self.clock)
        self.assertEqual(up.execute(v["name"]), "active")
        sent = [c for c in self.machine.calls if c[0] == "create_voice"][0][1]
        self.assertEqual(sent["consent"]["by"], "Lan")
        self.assertTrue(sent["audio_base64"])
        row = self.profiles.rows[v["name"]]
        self.assertEqual((row["voice_id"], row["status"], row["clip_seconds"]), ("nv1", "active", 9.5))
        self.assertEqual(up.execute(v["name"]), "skip", "job lap khong tao giong trung")

    def test_add_validation(self):
        add = AddVoiceService(**self.add_kw())
        with self.assertRaises(C.AiVoicePermission):
            add.execute(U, UR, self.payload())
        for over in ({"consent_confirmed": 0}, {"consent_by": ""}, {"consent_date": "hôm qua"}, {"voice_name": ""},
                     {"sample_url": ""}, {"sample_url": "/private/files/khong-co.wav"}):
            with self.assertRaises(C.AiVoiceError, msg=str(over)):
                add.execute(M, MR, self.payload(**over))
        self.files.put("/private/files/virus.exe", b"MZ", M, "virus.exe")
        with self.assertRaises(C.AiVoiceError):
            add.execute(M, MR, self.payload(sample_url="/private/files/virus.exe"))
        self.files.put("/private/files/cua-nguoi-khac.wav", b"RIFF", U2, "x.wav")
        with self.assertRaises(C.AiVoicePermission):
            add.execute(M, MR, self.payload(sample_url="/private/files/cua-nguoi-khac.wav"))
        self.files.put("/private/files/cf.pdf", b"%PDF", U2, "cf.pdf")
        with self.assertRaises(C.AiVoicePermission):
            add.execute(M, MR, self.payload(consent_file="/private/files/cf.pdf"))
        self.assertEqual(len(self.profiles.rows), 1, "khong ho so rac")

    def test_upload_timeout_then_reconcile(self):
        v = AddVoiceService(**self.add_kw()).execute(M, MR, self.payload())
        self.machine.fail["create_voice"] = EVoiceDown("HTTP 524", timeout=True)
        up = UploadVoiceService(profiles=self.profiles, settings=self.settings, files=self.files, client=self.machine, now=self.clock)
        self.assertEqual(up.execute(v["name"]), "pending_check")
        sent = [c for c in self.machine.calls if c[0] == "create_voice"][0][1]
        self.assertIn("[erp:%s]" % v["name"], sent["description"])
        self.assertEqual(self.profiles.rows[v["name"]]["status"], "processing")
        sync = SyncVoicesService(profiles=self.profiles, settings=self.settings, client=self.machine, now=self.clock)
        self.assertEqual(sync.reconcile(), 0, "chua toi 2 phut")
        self.clock.adv(130)
        self.machine.voices_list = [{"id": "v1", "name": "Lan"}, {"id": "nv8", "name": "Lan Mới", "description": "tao tay trong app"},
                                    {"id": "nv9", "name": "Lan Mới", "description": "x [erp:%s]" % v["name"]}]
        self.assertEqual(sync.reconcile(), 1)
        self.assertEqual((self.profiles.rows[v["name"]]["voice_id"], self.profiles.rows[v["name"]]["status"]), ("nv9", "active"),
                         "gan theo dau [erp:], khong gan nham giong trung ten tao tay")

    def test_sync_during_processing_links_instead_of_duplicating(self):
        v = AddVoiceService(**self.add_kw()).execute(M, MR, self.payload())
        self.machine.voices_list = [{"id": "v1", "name": "Lan"}, {"id": "nv9", "name": "Lan Mới", "description": "[erp:%s]" % v["name"]}]
        out = SyncVoicesService(profiles=self.profiles, settings=self.settings, client=self.machine, now=self.clock).execute(MR)
        self.assertEqual(out["added"], 0, "khong tao ho so 'tu may' trung")
        self.assertEqual((self.profiles.rows[v["name"]]["voice_id"], self.profiles.rows[v["name"]]["status"]), ("nv9", "active"))
        up = UploadVoiceService(profiles=self.profiles, settings=self.settings, files=self.files, client=self.machine, now=self.clock)
        self.assertEqual(up.execute(v["name"]), "skip", "upload cham ve sau khong ghi de")
    def test_upload_gives_up_after_30min(self):
        v = AddVoiceService(**self.add_kw()).execute(M, MR, self.payload())
        sync = SyncVoicesService(profiles=self.profiles, settings=self.settings, client=self.machine, now=self.clock)
        self.clock.adv(31 * 60)
        self.assertEqual(sync.reconcile(), 1)
        self.assertEqual(self.profiles.rows[v["name"]]["status"], "failed")
        r = AddVoiceService(**self.add_kw()).retry(M, MR, v["name"])
        self.assertEqual(r["status"], "processing")

    def test_upload_hard_errors(self):
        v = AddVoiceService(**self.add_kw()).execute(M, MR, self.payload())
        self.machine.fail["create_voice"] = EVoiceHttpError(400, "File quá ngắn")
        up = UploadVoiceService(profiles=self.profiles, settings=self.settings, files=self.files, client=self.machine, now=self.clock)
        self.assertEqual(up.execute(v["name"]), "failed")
        self.assertEqual(self.profiles.rows[v["name"]]["upload_error"], "File quá ngắn")

    def test_sync_from_machine(self):
        self.machine.voices_list = [{"id": "v1", "name": "Lan (máy)"}, {"id": "v7", "name": "Minh", "gender": "Nam"},
                                    {"id": "v7", "name": "dup"}, {"id": "", "name": "rong"}]
        gone = self.profiles.add(voice_id="v99")
        out = SyncVoicesService(profiles=self.profiles, settings=self.settings, client=self.machine, now=self.clock).execute(MR)
        self.assertEqual((out["added"], out["updated"], out["missing"]), (1, 1, 1))
        new = self.profiles.get_by_voice_id("v7")
        self.assertEqual((new["status"], new["source"], new["gender"]), ("disabled", "machine", "Nam"),
                         "giong moi tu may: NGUNG cho toi khi co bang chung dong y")
        self.assertEqual(self.profiles.rows[self.p1]["voice_name"], "Lan", "giong tao tu ERP khong bi may doi ten")
        self.assertEqual(self.profiles.rows[gone]["missing_on_server"], 1)
        with self.assertRaises(C.AiVoicePermission):
            SyncVoicesService(profiles=self.profiles, settings=self.settings, client=self.machine, now=self.clock).execute(UR)
        self.machine.fail["voices"] = EVoiceDown("x")
        with self.assertRaises(C.AiVoiceError):
            SyncVoicesService(profiles=self.profiles, settings=self.settings, client=self.machine, now=self.clock).execute(MR)

    def test_enable_requires_consent(self):
        v = self.profiles.add(status="disabled", source="machine", voice_id="v7")
        upd = UpdateVoiceService(profiles=self.profiles, files=self.files)
        with self.assertRaises(C.AiVoiceError):
            upd.execute(M, MR, v, {"status": "active"})
        with self.assertRaises(C.AiVoiceError):
            upd.execute(M, MR, v, {"status": "active", "consent_by": "Minh", "consent_date": "2026-11-01"})  # thieu tick
        out = upd.execute(M, MR, v, {"status": "active", "consent_by": "Minh", "consent_date": "2026-11-01", "consent_confirmed": 1})
        self.assertEqual((out["status"], out["has_consent"]), ("active", True))
        with self.assertRaises(C.AiVoicePermission):
            upd.execute(U, UR, v, {"voice_name": "x"})
        with self.assertRaises(C.AiVoiceError):
            upd.execute(M, MR, v, {"status": "processing"})
        busy = self.profiles.add(status="processing", voice_id="")
        with self.assertRaises(C.AiVoiceError):
            upd.execute(M, MR, busy, {"status": "active"})

    def test_remove(self):
        rm = RemoveVoiceService(profiles=self.profiles, settings=self.settings, client=self.machine)
        v = self.profiles.add(voice_id="v5")
        rm.execute(MR, v, from_machine=False)
        self.assertNotIn(("delete_voice", "v5"), self.machine.calls)
        v = self.profiles.add(voice_id="v6")
        self.machine.fail["delete_voice"] = EVoiceHttpError(404, "")
        self.assertTrue(rm.execute(MR, v, from_machine=True)["from_machine"])
        v = self.profiles.add(voice_id="v8")
        self.machine.fail["delete_voice"] = EVoiceDown("x")
        with self.assertRaises(C.AiVoiceError):
            rm.execute(MR, v, from_machine=True)
        self.assertIn(v, self.profiles.rows, "may tat -> khong xoa ERP de khoi lech")
        busy = self.profiles.add(status="processing")
        with self.assertRaises(C.AiVoiceError):
            rm.execute(MR, busy)

    def test_sample_cached(self):
        au = AudioService(jobs=self.jobs, profiles=self.profiles, settings=self.settings, files=self.files, client=self.machine)
        f1 = au.sample(U, UR, self.p1)
        f2 = au.sample(U, UR, self.p1)
        self.assertEqual(f1[1], f2[1])
        self.assertEqual(len([c for c in self.machine.calls if c[0] == "voice_sample"]), 1, "lan 2 phat tu ERP")
        off = self.profiles.add(status="disabled")
        with self.assertRaises(C.AiVoicePermission):
            au.sample(U, UR, off)

    def test_state_filters_voices(self):
        self.profiles.add(status="disabled")
        self.profiles.add(restricted=1, owner_user="o@x")
        st = GetStateService(jobs=self.jobs, profiles=self.profiles, settings=self.settings)
        u = st.execute(U, UR)
        self.assertEqual([v["voice_name"] for v in u["voices"]], ["Lan"])
        self.assertNotIn("consent_by", u["voices"][0], "nguoi thuong khong thay chi tiet dong y")
        self.assertTrue(u["configured"])
        self.assertNotIn("token", json.dumps(u))
        m = st.execute(M, MR)
        self.assertEqual(len(m["voices"]), 3)
        self.assertTrue(m["is_manager"] and not m["is_admin"])
        with self.assertRaises(C.AiVoicePermission):
            st.execute("x@x", ("Employee",))


# ------------------------------------------------------------------ cai dat + trang thai may ---
class TestSettingsAndStatus(World):
    def svc(self):
        return SettingsService(settings=self.settings, client=self.machine, cache=self.cache)

    def test_admin_only_and_token_write_only(self):
        with self.assertRaises(C.AiVoicePermission):
            self.svc().get(MR)
        out = self.svc().get(AR)
        self.assertNotIn("token", out)
        self.assertTrue(out["token_set"])
        self.svc().save(AR, {"base_url": "https://v2.x/", "token": "", "default_speed": "1.2", "timeout": "999"})
        self.assertEqual(self.settings.d["token"], "tok", "token rong = giu nguyen")
        self.assertEqual((self.settings.d["base_url"], self.settings.d["timeout"]), ("https://v2.x", 120))
        self.svc().save(AR, {"base_url": "https://v2.x", "token": "  new  "})
        self.assertEqual(self.settings.d["token"], "new")
        with self.assertRaises(C.AiVoiceError):
            self.svc().save(AR, {"base_url": "javascript:alert(1)"})

    def test_test_connection(self):
        self.assertTrue(self.svc().test(AR)["ok"])
        self.assertTrue(self.settings.d["last_check_result"].startswith("OK"))
        self.machine.fail["health"] = EVoiceHttpError(401, "Unauthorized")
        r = self.svc().test(AR)
        self.assertFalse(r["ok"])
        self.assertIn("token", r["message"].lower())

    def test_machine_status_cache_and_down(self):
        ms = MachineStatusService(settings=self.settings, client=self.machine, cache=self.cache, profiles=self.profiles)
        self.assertTrue(ms.execute(UR)["online"])
        ms.execute(UR)
        self.assertEqual(len([c for c in self.machine.calls if c[0] == "health"]), 1, "30 giay dau lay tu cache")
        self.machine.fail["health"] = EVoiceDown("x")
        out = ms.execute(UR, fresh=True)
        self.assertEqual((out["online"], out["message"]), (False, C.Msg.DOWN))
        b = ms.brands(U, UR)
        self.assertEqual([x["name"] for x in b["brands"]], ["Lix"], "brand chua chon giong / giong chua co tren ERP bi an")
        self.assertEqual(b["hidden"], 1)
        self.profiles.rows[self.p1].update(restricted=1, owner_user="o@x")
        self.assertEqual(ms.brands(U, UR)["brands"], [], "loc theo NGUOI XEM, ke ca tu cache")
        self.assertEqual(len(ms.brands("o@x", UR)["brands"]), 1)
        self.machine.fail["brands"] = EVoiceDown("x")
        self.cache.d.clear()
        self.assertEqual(ms.brands(U, UR), {"online": False, "brands": []})
        with self.assertRaises(C.AiVoicePermission):
            ms.execute(("Employee",))


if __name__ == "__main__":
    unittest.main()
