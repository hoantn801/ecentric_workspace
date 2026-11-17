# Copyright (c) 2026, eCentric and contributors
"""Ban quyen AI Live (17/11/2026): license_request / license_checkin + trang duyet - chay ngoai Frappe voi repo gia.
Theo dung muc kiem tra A.6 / B.6 cua hop dong gui chat ERP. Token kiem bang chinh ham ky (khoa thu, khong dung khoa that)."""
import base64
import hashlib
import hmac
import json
import os
import time
import unittest
import uuid
from datetime import datetime, timedelta, timezone

from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from ecentric_workspace.ai_tools.features.ai_live import license_constants as L
from ecentric_workspace.ai_tools.features.ai_live.application.license_action_service import LicenseActionService
from ecentric_workspace.ai_tools.features.ai_live.application.license_checkin_service import LicenseCheckinService
from ecentric_workspace.ai_tools.features.ai_live.application.license_detail_service import LicenseDetailService
from ecentric_workspace.ai_tools.features.ai_live.application.license_notify_service import LicenseNotifyService
from ecentric_workspace.ai_tools.features.ai_live.application.license_query_service import LicenseQueryService
from ecentric_workspace.ai_tools.features.ai_live.application.license_request_service import LicenseRequestService
from ecentric_workspace.ai_tools.features.ai_live.domain import ec_license_issuer as I
from ecentric_workspace.ai_tools.features.ai_live.domain import license_rules as R

_PRIV = rsa.generate_private_key(public_exponent=65537, key_size=2048).private_bytes(
    serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode()
_ED = Ed25519PrivateKey.generate().private_bytes(serialization.Encoding.Raw, serialization.PrivateFormat.Raw,
                                                 serialization.NoEncryption())
SECRETS = {"elive": json.dumps({"mk": I._b64u_e(os.urandom(32)), "app_secret": I._b64u_e(os.urandom(32)),
                                "rsa_private_pem": _PRIV}),
           "esync": json.dumps({"mk": I._b64u_e(os.urandom(32)), "app_secret": I._b64u_e(os.urandom(32)),
                                "rsa_private_pem": _PRIV, "premium_fernet_key": Fernet.generate_key().decode()}),
           "evoice": json.dumps({"private_key": base64.b64encode(_ED).decode(),
                                 "master_key": base64.b64encode(os.urandom(32)).decode(),
                                 "app_secret": base64.b64encode(os.urandom(32)).decode()})}
DIST_KEY = "ab" * 32
ADMIN, ROLES, NOBODY = "hoan@ecentric.vn", ["System Manager"], ["Employee"]
T0 = time.time()


# ------------------------------------------------------------------ du lieu app gui ---
def hexs(seed, n):
    return hashlib.sha256(seed.encode()).hexdigest()[:n]


def fp(guid="g1", disk="d1", macs=("m1",)):
    return {"guid_h": hexs(guid, 20), "disk_h": hexs(disk, 20) if disk else "", "mac_h": [hexs(m, 20) for m in macs]}


def dist(kind="khach", label="Gói Lix", days_old=0, signed=True, **over):
    created = (datetime.now(timezone.utc) - timedelta(days=days_old)).isoformat()
    d = {"dist_id": str(uuid.uuid4()), "kind": kind, "label": label, "created_at": created, "package": "p1"}
    d["sig"] = hmac.new(DIST_KEY.encode(), I.dist_message(d), hashlib.sha256).hexdigest() if signed else ""
    d.update(over)
    return d


def payload(product="elive", f=None, d=None, host="MAY-A", hwseed="A", **over):
    if product == "evoice":
        hw = hexs("ev" + hwseed, 24)
        code = hw
    elif product == "esync":
        hw = hexs("es" + hwseed, 32).upper()
        mid = "SYNC-%s" % "-".join([hexs(hwseed, 16).upper()[i:i + 4] for i in range(0, 16, 4)])
        code = "YC-" + I._b64u_e(("ESYNC1|%s|%s" % (mid, hw)).encode())
    else:
        hw = hexs("el" + hwseed, 32).upper()
        code = "EC-" + I._b64u_e(("ELIVE1|%s" % hw).encode())
    p = {"v": "1", "product": product, "build_id": "1.0.40", "hw": hw, "request_code": code,
         "fp": f or fp(), "dist": d or {}, "host": host, "user": "live", "os": "Windows-10", "app_dir": "C:\\eLive",
         "at": 1}
    p.update(over)
    return p


# ------------------------------------------------------------------ repo gia ---
class Settings:
    def __init__(self, **kw):
        self.v = {"enabled": 1, "log_only": 0, "office_ips": "", "teams_format": "workflows", "killed": 0}
        self.v.update(kw)
        self.secrets, self.dist_key, self.webhook = dict(SECRETS), DIST_KEY, "https://hook"

    def get(self):
        return dict(self.v)

    def secret(self, p):
        return self.secrets.get(p, "")

    def dist_secret(self):
        return self.dist_key

    def teams_webhook(self):
        return self.webhook

    def set_mode(self, en, lo):
        self.v.update(enabled=en, log_only=lo)


class Machines:
    def __init__(self):
        self.rows, self.n = {}, 0

    def _view(self, r):
        m = json.loads(json.dumps(r))
        m["hw"] = {i["product"]: i.get("hw") for i in m["installs"] if i.get("hw")}
        m["reissued_at"] = {i["product"]: i["reissued_at"] for i in m["installs"] if i.get("reissued_at")}
        return m

    def by_guid(self, g):
        return [self._view(r) for r in self.rows.values() if r["fp"]["guid_h"] == g]

    def get(self, name):
        return self._view(self.rows[name]) if name in self.rows else None

    def create(self, vals, installs):
        self.n += 1
        name = "LIC-%05d" % self.n
        r = {"name": name, "status": "pending", "label": "", "blocked_manual": 0, "clone_warning": 0, "via_checkin": 0,
             "creation": self.n, "installs": []}
        r.update(vals)
        r["installs"] = [dict(i) for i in installs]
        self.rows[name] = r
        return name

    def save(self, name, vals):
        self.rows[name].update(vals)

    touch = save

    def upsert_install(self, name, product, vals):
        inst = next((i for i in self.rows[name]["installs"] if i["product"] == product), None)
        if inst is None:
            self.rows[name]["installs"].append(dict(vals, product=product))
        else:
            inst.update(vals)

    def dist_owner(self, did, exclude=None):
        rows = [r for r in self.rows.values() if r.get("source_dist") == did and r["status"] == "approved"
                and not r.get("via_checkin") and r["name"] != exclude]
        rows.sort(key=lambda r: (r.get("approved_at") or 0, r["creation"]))
        return {"name": rows[0]["name"]} if rows else None

    def count_approved(self, did):
        return sum(1 for r in self.rows.values() if r.get("source_dist") == did and r["status"] == "approved")

    def count_pending_by_dist(self):
        out = {}
        for r in self.rows.values():
            if r["status"] == "pending":
                out[r.get("source_dist") or ""] = out.get(r.get("source_dist") or "", 0) + 1
        return out

    def counts(self, since):
        rs = self.rows.values()
        return {"pending": sum(r["status"] == "pending" for r in rs), "running": len(rs),
                "blocked": sum(r["status"] == "blocked" for r in rs), "clone": sum(bool(r["clone_warning"]) for r in rs)}

    def search(self, flt, q, order, page):
        rows = [self._view(r) for r in self.rows.values() if all(r.get(k) == v for k, v in flt.items()
                                                                   if not isinstance(v, list))]
        if q:
            rows = [r for r in rows if q.lower() in (r["name"] + r.get("host", "") + r.get("label", "")).lower()]
        return rows, False

    def children(self, name):
        return [self._view(r) for r in self.rows.values() if r.get("parent_machine") == name]

    def tree_rows(self, dist=None):
        return [r for r in self.rows.values() if not dist or r.get("source_dist") == dist]

    def labels(self, names):
        return {n: self.rows[n].get("label") or self.rows[n].get("host") for n in names if n in self.rows}


class Dists:
    def __init__(self):
        self.rows = {}

    def ensure(self, d):
        self.rows.setdefault(d["dist_id"], {"name": d["dist_id"], "label": d.get("label"), "kind": d.get("kind"),
                                            "first_machine": None, "issued_count": 0})
        return d["dist_id"]

    def get(self, did):
        return self.rows.get(did)

    def set_first(self, did, m, ts):
        if not self.rows[did]["first_machine"]:
            self.rows[did]["first_machine"] = m

    def set_count(self, did, n):
        self.rows[did]["issued_count"] = n

    def set_label(self, did, label):
        self.rows[did]["label"] = label

    def all(self):
        return list(self.rows.values())

    def labels(self, names):
        return {n: self.rows[n]["label"] for n in names if n in self.rows}


class Events:
    def __init__(self):
        self.rows = []

    def add(self, machine, product, kind, ip="", user="", detail=""):
        self.rows.append({"machine": machine, "product": product, "kind": kind, "ip": ip, "user": user, "detail": detail})

    def kinds(self, machine=None):
        return [e["kind"] for e in self.rows if machine is None or e["machine"] == machine]

    def for_machine(self, m, limit=50):
        return [e for e in self.rows if e["machine"] == m][-limit:]

    def search(self, f, page):
        return [e for e in self.rows if not f.get("kind") or e["kind"] == f["kind"]], False


class Locks:
    def __init__(self, free=True):
        self.free, self.held, self.log, self.commits, self.rollbacks = free, set(), [], 0, 0

    def lock(self, keys):
        if not self.free or self.held & set(keys):
            return False
        self.held |= set(keys)
        self.log.append(sorted(keys))
        return True

    def unlock(self, keys):
        self.held -= set(keys)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class Notifier:
    def __init__(self):
        self.sent = []

    def enqueue(self, kind, name):
        self.sent.append((kind, name))


class World:
    def __init__(self, **settings):
        self.now = T0
        self.settings, self.machines, self.dists = Settings(**settings), Machines(), Dists()
        self.events, self.locks, self.notifier = Events(), Locks(), Notifier()
        kw = dict(settings=self.settings, machines=self.machines, dists=self.dists, events=self.events)
        clock = lambda: self.now  # noqa: E731
        self.req = LicenseRequestService(locks=self.locks, notifier=self.notifier, clock=clock, **kw)
        self.chk = LicenseCheckinService(locks=self.locks, notifier=self.notifier, clock=clock, **kw)
        self.act = LicenseActionService(locks=self.locks, clock=clock, **kw)
        self.qry = LicenseQueryService(clock=clock, dt=lambda ts: "T%d" % ts, **kw)
        self.det = LicenseDetailService(**kw)

    def request(self, p, ip="1.1.1.1"):
        return self.req.execute(p, ip)

    def checkin(self, p, ip="1.1.1.1"):
        return self.chk.execute(p, ip)


# ------------------------------------------------------------------ A.6 ---
class TestRequest(unittest.TestCase):
    def test_a6_1_new_machine_new_dist_issues_three_apps_one_machine(self):
        w, d = World(), dist()
        for prod in ("elive", "esync", "evoice"):
            r = w.request(payload(prod, d=d))
            self.assertEqual(r["status"], "issued", prod)
            self.assertTrue(r["token"])
        self.assertEqual(len(w.machines.rows), 1)
        m = w.machines.get("LIC-00001")
        self.assertEqual(sorted(i["product"] for i in m["installs"]), ["elive", "esync", "evoice"])
        self.assertEqual(m["status"], "approved")
        self.assertEqual(w.dists.rows[d["dist_id"]]["first_machine"], "LIC-00001")
        self.assertEqual(w.dists.rows[d["dist_id"]]["issued_count"], 1)
        self.assertNotIn("token", json.dumps(w.events.rows))

    def test_token_is_real_license_for_this_hw(self):
        w = World()
        p = payload("elive", d=dist())
        tok = w.request(p)["token"]
        body = json.loads(base64.b64decode(tok[len("ELIVEKEY-"):]))
        self.assertEqual(body["hwid"], p["hw"])
        self.assertEqual(body["cust"], "MAY-A")

    def test_a6_2_copy_is_pending_with_teams_and_client_sees_neutral_message(self):
        w, d = World(), dist()
        w.request(payload(d=d))
        r = w.request(payload(d=d, f=fp("g2", "d2", ("m2",)), host="MAY-B", hwseed="B"))
        self.assertEqual(r, {"status": "pending", "message": I.CLIENT_PENDING_MSG, "poll_s": 30})
        m2 = w.machines.get("LIC-00002")
        self.assertEqual((m2["status"], m2["parent_machine"]), ("pending", "LIC-00001"))
        self.assertIn("bản chép từ máy LIC-00001", m2["reason"])
        self.assertEqual(w.notifier.sent, [("pending", "LIC-00002")])
        for _ in range(3):   # app hoi lai moi 15-30 s: khong bao Teams lai, khong rac nhat ky
            w.request(payload(d=d, f=fp("g2", "d2", ("m2",)), host="MAY-B", hwseed="B"))
        self.assertEqual(len(w.notifier.sent), 1)
        self.assertEqual(w.events.kinds("LIC-00002").count("pending"), 1)
        w.act.approve(ADMIN, ROLES, ["LIC-00002"])
        r = w.request(payload(d=d, f=fp("g2", "d2", ("m2",)), host="MAY-B", hwseed="B"))
        self.assertEqual(r["status"], "issued")
        self.assertEqual(w.dists.rows[d["dist_id"]]["first_machine"], "LIC-00001")

    def test_owner_is_per_machine_not_per_app(self):
        w, d = World(), dist()
        w.request(payload("elive", d=d))
        r = w.request(payload("esync", d=d, f=fp("g2", "d2", ("m2",)), host="MAY-B", hwseed="B"))
        self.assertEqual(r["status"], "pending")

    def test_a6_5_internal_dist_and_office_ip_auto_approve(self):
        w, d = World(office_ips="9.9.9.9, 8.8.8.8"), dist(kind="noi_bo")
        w.request(payload(d=d))
        self.assertEqual(w.request(payload(d=d, f=fp("g2"), hwseed="B"))["status"], "issued")
        w2, d2 = World(office_ips="9.9.9.9"), dist()
        w2.request(payload(d=d2))
        self.assertEqual(w2.request(payload(d=d2, f=fp("g3"), hwseed="C"), ip="9.9.9.9")["status"], "issued")
        old = dist(kind="noi_bo", days_old=40)
        self.assertEqual(World().request(payload(d=old))["status"], "pending")

    def test_a6_6_tampered_dist_is_treated_as_no_dist(self):
        w, d = World(), dist()
        bad = dict(d, kind="noi_bo")         # tu sua kind -> chu ky sai
        self.assertEqual(w.request(payload(d=bad))["status"], "pending")
        self.assertEqual(w.dists.rows, {})
        self.assertIn("không có mã gói", w.machines.get("LIC-00001")["reason"])
        self.assertEqual(World().request(payload(d=dist(signed=False)))["status"], "pending")
        w3 = World()
        w3.settings.dist_key = ""            # ERP chua co khoa ky goi -> khong tin ma goi
        self.assertEqual(w3.request(payload(d=dist()))["status"], "pending")

    def test_a6_7_two_copies_same_new_dist_lock_on_dist(self):
        w, d = World(), dist()
        w.request(payload(d=d))
        self.assertIn(["d:" + d["dist_id"], "g:" + fp()["guid_h"]], w.locks.log)
        w.locks.held.add("d:" + d["dist_id"])    # may kia dang giu khoa goi -> may nay cho, khong thanh "may dau"
        r = w.request(payload(d=d, f=fp("g9"), hwseed="Z"))
        self.assertEqual(r["status"], "pending")
        self.assertIsNone(w.machines.by_guid(fp("g9")["guid_h"]) or None)

    def test_a6_9_bad_payload_never_blocked(self):
        w = World()
        for bad in (None, [], {"product": "x"}, payload(fp="abc"), payload(hw="A" * 1000),
                    payload(fp={"guid_h": "zz-not-hex", "disk_h": "", "mac_h": []}),
                    payload(fp={"guid_h": "ab", "mac_h": ["ab"] * 40})):
            self.assertEqual(w.request(bad)["status"], "pending")
            self.assertEqual(w.checkin(bad)["status"], "ok")
        self.assertEqual(w.machines.rows, {})

    def test_bad_request_code_blocked_without_record(self):
        w = World()
        r = w.request(payload(request_code="EC-xxxx"))
        self.assertEqual(r, {"status": "blocked", "message": "Mã yêu cầu không hợp lệ"})
        self.assertEqual(w.machines.rows, {})

    def test_a6_4_disabled_or_kill_switch(self):
        self.assertEqual(World(enabled=0).request(payload())["status"], "unknown")
        self.assertEqual(World(enabled=0).checkin(payload())["status"], "ok")
        self.assertEqual(World(killed=1).request(payload())["status"], "unknown")

    def test_missing_signing_key_is_unknown_not_crash(self):
        w = World()
        w.settings.secrets["elive"] = ""
        r = w.request(payload(d=dist()))
        self.assertEqual(r["status"], "unknown")
        self.assertEqual(w.machines.rows, {})            # rollback: chua cap thi chua ghi may
        self.assertEqual(w.locks.rollbacks, 1)
        self.assertIn("error", w.events.kinds())
        self.assertNotIn("rsa", json.dumps(w.events.rows))

    def test_c1_changed_disk_reissue_once_per_30_days(self):
        w = World()
        w.request(payload(d=dist()))
        f2 = fp(disk="d2")                                   # doi o C:, giu card mang -> cung may
        self.assertEqual(w.request(payload(f=f2, hwseed="A2"))["status"], "issued")
        f3 = fp(disk="d3")
        w.now += 86400
        self.assertEqual(w.request(payload(f=f3, hwseed="A3"))["status"], "pending")
        m = w.machines.get("LIC-00001")
        self.assertEqual(m["status"], "pending")
        self.assertEqual(w.notifier.sent, [("pending", "LIC-00001")])
        w.act.approve(ADMIN, ROLES, ["LIC-00001"])
        self.assertEqual(w.request(payload(f=f3, hwseed="A3"))["status"], "issued")

    def test_blocked_machine_request_gets_block_message(self):
        w = World()
        w.request(payload(d=dist()))
        w.act.block(ADMIN, ROLES, "LIC-00001", "Liên hệ anh Hoàn")
        self.assertEqual(w.request(payload(product="esync"))["status"], "blocked")
        self.assertEqual(w.request(payload())["message"], "Liên hệ anh Hoàn")


class TestCheckin(unittest.TestCase):
    def test_a6_3_block_only_at_next_open_and_only_manual(self):
        w = World()
        w.request(payload(d=dist()))
        self.assertEqual(w.checkin(payload()), {"status": "ok"})
        w.act.block(ADMIN, ROLES, "LIC-00001", "")
        r = w.checkin(payload())
        self.assertEqual(r, {"status": "blocked", "manual": True, "message": L.Msg.DEFAULT_BLOCK})
        w.act.unblock(ADMIN, ROLES, "LIC-00001")
        self.assertEqual(w.checkin(payload()), {"status": "ok"})

    def test_b6_5_log_only_never_blocks(self):
        w = World(log_only=1)
        w.request(payload(d=dist()))
        w.act.block(ADMIN, ROLES, "LIC-00001", "x")
        self.assertEqual(w.checkin(payload()), {"status": "ok"})

    def test_blocked_without_manual_flag_is_ok(self):
        w = World()
        w.request(payload(d=dist()))
        w.machines.rows["LIC-00001"]["status"] = "blocked"     # vi ly do nao do khong qua nut Khoa
        self.assertEqual(w.checkin(payload()), {"status": "ok"})

    def test_a6_8_manual_key_machine_first_checkin_ok_and_recorded(self):
        w = World()
        self.assertEqual(w.checkin(payload(license_hw="X")), {"status": "ok"})
        m = w.machines.get("LIC-00001")
        self.assertEqual((m["status"], m["reason"], m["via_checkin"]), ("approved", L.REASON_MANUAL_KEY, 1))
        self.assertEqual(m["installs"][0]["hw"], payload()["hw"])

    def test_self_declared_checkin_record_cannot_mint_license(self):
        """Ai doc ec_online.py cung gui duoc checkin gia -> ban ghi do KHONG duoc tu cap license."""
        w = World()
        w.checkin(payload(product="elive"))
        r = w.request(payload(product="esync"))
        self.assertEqual(r["status"], "pending")
        m = w.machines.get("LIC-00001")
        self.assertEqual((m["status"], m["reason"]), ("pending", L.REASON_MANUAL_ASK))
        self.assertEqual(w.checkin(payload()), {"status": "ok"})         # app dang chay khong bi anh huong
        w.act.approve(ADMIN, ROLES, ["LIC-00001"])
        self.assertEqual(w.request(payload(product="esync"))["status"], "issued")

    def test_checkin_record_does_not_own_dist(self):
        w, d = World(), dist()
        w.checkin(payload(d=d, f=fp("gx"), hwseed="X"))
        self.assertEqual(w.request(payload(d=d))["status"], "issued")    # may that dau tien van la "may dau"

    def test_clone_warning_once_without_blocking(self):
        w = World()
        w.request(payload(d=dist()))
        ghost = payload(f=fp(macs=("m9",)), host="MAY-GHOST")
        self.assertEqual(w.checkin(ghost), {"status": "ok"})
        m = w.machines.get("LIC-00001")
        self.assertEqual((m["clone_warning"], m["clone_host"], m["host"]), (1, "MAY-GHOST", "MAY-A"))
        w.checkin(ghost)
        self.assertEqual(w.notifier.sent, [("clone", "LIC-00001")])
        self.assertEqual(m["status"], "approved")

    def test_mac_change_same_machine_updates_fp(self):
        w = World()
        w.request(payload(d=dist()))
        w.checkin(payload(f=fp(macs=("m1", "m5"))))
        self.assertEqual(len(w.machines.rows), 1)
        self.assertEqual(len(w.machines.get("LIC-00001")["fp"]["mac_h"]), 2)


# ------------------------------------------------------------------ B ---
class TestAdmin(unittest.TestCase):
    def setUp(self):
        self.w, self.d = World(), dist()
        self.w.request(payload(d=self.d))
        self.w.request(payload(d=self.d, f=fp("g2"), host="<script>x</script>", hwseed="B"))
        self.w.request(payload(f=fp("g3"), host="MAY-C", hwseed="C"))

    def test_b6_1_no_role_403(self):
        w = self.w
        for fn in (lambda: w.qry.summary(NOBODY), lambda: w.qry.machines_page(NOBODY, {}, 0),
                   lambda: w.det.machine(NOBODY, "LIC-00001"), lambda: w.det.tree(NOBODY),
                   lambda: w.act.approve(ADMIN, NOBODY, ["LIC-00002"]), lambda: w.act.block(ADMIN, NOBODY, "LIC-00001", ""),
                   lambda: w.act.set_mode(ADMIN, NOBODY, 1, 0), lambda: w.qry.events_page(NOBODY, {}, 0)):
            self.assertRaises(L.LicensePermission, fn)
        self.assertEqual(w.qry.badge(NOBODY), {"pending": 0})
        self.assertEqual(w.qry.badge(["AI Live License Admin"]), {"pending": 2})

    def test_summary_never_returns_secret_content(self):
        s = self.w.qry.summary(ROLES)
        self.assertEqual(s["counts"]["pending"], 2)
        self.assertEqual(s["secrets"], {"elive": "ok", "esync": "ok", "evoice": "ok", "dist": "ok"})
        self.assertNotIn("PRIVATE", json.dumps(s))

    def test_b6_7_bulk_approve_and_double_click(self):
        r = self.w.act.approve(ADMIN, ROLES, ["LIC-00002", "LIC-00003", "LIC-00002"])
        self.assertEqual(r["approved"], ["LIC-00002", "LIC-00003"])
        r = self.w.act.approve(ADMIN, ROLES, ["LIC-00002"])                     # nguoi thu hai bam sau
        self.assertEqual((r["approved"], len(r["skipped"])), ([], 1))
        self.assertEqual(self.w.events.kinds("LIC-00002").count("approve"), 1)
        self.assertEqual(self.w.events.rows[-1]["user"], ADMIN)

    def test_approve_waits_when_app_holds_lock(self):
        self.w.locks.held.add("g:" + fp("g2")["guid_h"])
        r = self.w.act.approve(ADMIN, ROLES, ["LIC-00002"])
        self.assertEqual(r["approved"], [])
        self.assertIn("đang được xử lý", r["skipped"][0]["why"])

    def test_list_detail_tree_and_xss_text_is_data(self):
        rows = self.w.qry.machines_page(ROLES, {"tab": "pending"}, 0)["rows"]
        self.assertEqual([r["name"] for r in rows], ["LIC-00002", "LIC-00003"])
        self.assertEqual(rows[0]["host"], "<script>x</script>")      # tra nguyen chu - trang escape khi ve
        self.assertEqual(rows[0]["parent"]["name"], "LIC-00001")
        self.assertEqual([a["installed"] for a in rows[0]["apps"]], [True, False, False])
        det = self.w.det.machine(ROLES, "LIC-00001")
        self.assertEqual([c["name"] for c in det["children"]], ["LIC-00002"])
        self.assertNotIn("hw", det["installs"][0])
        self.assertNotIn("fp", det["machine"])
        tree = self.w.det.tree(ROLES)["tree"]
        self.assertEqual(tree[0]["machines"][0]["name"], "LIC-00001")
        self.assertEqual(tree[0]["machines"][0]["children"][0]["name"], "LIC-00002")
        self.assertEqual(tree[-1]["label"], L.Msg.NO_DIST)
        self.assertRaises(L.LicenseError, self.w.qry.machines_page, ROLES, {"tab": "x"}, 0)

    def test_edit_and_mode_are_logged_before_after(self):
        self.w.act.update_machine(ADMIN, ROLES, "LIC-00001", "Máy Lix 2", None)
        self.w.act.update_dist(ADMIN, ROLES, self.d["dist_id"], "Lix tháng 11")
        self.w.act.set_mode(ADMIN, ROLES, 1, 1)
        det = [e["detail"] for e in self.w.events.rows[-3:]]
        self.assertIn("tên: (trống) → Máy Lix 2", det[0])
        self.assertIn("Gói Lix → Lix tháng 11", det[1])
        self.assertIn("Chỉ ghi nhận: tắt → bật", det[2])
        self.assertEqual(self.w.settings.v["log_only"], 1)

    def test_block_returns_log_only_flag(self):
        self.w.settings.v["log_only"] = 1
        self.assertEqual(self.w.act.block(ADMIN, ROLES, "LIC-00003", "")["log_only"], 1)
        self.assertRaises(L.LicenseError, self.w.act.block, ADMIN, ROLES, "LIC-00003", "")
        self.assertRaises(L.LicenseError, self.w.act.unblock, ADMIN, ROLES, "LIC-00001")


class Sender:
    def __init__(self):
        self.sent = []

    def send_teams_url(self, url, fmt, level, title, text, link, button=None):
        self.sent.append((title, text, link, button))
        return True, "200"


class TestNotify(unittest.TestCase):
    def test_teams_text_escaped_with_deep_link(self):
        w, d = World(), dist(label="Gói *Lix*")
        w.request(payload(d=d))
        w.request(payload(d=d, f=fp("g2"), host="<b>X</b>", hwseed="B"))
        s = Sender()
        svc = LicenseNotifyService(settings=w.settings, machines=w.machines, dists=w.dists, events=w.events,
                                   sender=s, site_url=lambda p: "https://team.ecentric.vn" + p)
        self.assertTrue(svc.execute("pending", "LIC-00002"))
        title, text, link, button = s.sent[0]
        self.assertEqual(link, "https://team.ecentric.vn/ai-live/ban-quyen#may-LIC-00002")
        self.assertEqual(button, "Mở để duyệt")
        self.assertIn("&lt;b&gt;X&lt;/b&gt;", text)
        self.assertNotIn("<b>", text)
        self.assertIn("eLive", text)
        self.assertIn("Gói \\*Lix\\*", text)
        w.settings.webhook = ""
        self.assertFalse(svc.execute("pending", "LIC-00002"))


class TestRules(unittest.TestCase):
    def test_tree_cycle_safe(self):
        t = R.build_tree([], [{"name": "a", "parent_machine": "b"}, {"name": "b", "parent_machine": "a"}])
        self.assertEqual(sum(len(x["machines"]) for x in t) + sum(len(m["children"]) for x in t for m in x["machines"]), 2)

    def test_clean_text_strips_controls(self):
        self.assertEqual(R.clean_text("A\x00B\u202eC" + "x" * 300, 5), "ABCxx")
        self.assertEqual(R.clean_text({"a": 1}, 5), "")

    def test_secret_state(self):
        self.assertEqual(R.secret_state("elive", ""), "missing")
        self.assertEqual(R.secret_state("elive", "{bad"), "bad")
        self.assertEqual(R.secret_state("esync", SECRETS["elive"]), "bad")      # thieu premium_fernet_key
        self.assertEqual(R.secret_state("evoice", SECRETS["evoice"]), "ok")


if __name__ == "__main__":
    unittest.main()
