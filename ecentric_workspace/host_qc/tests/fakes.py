# Copyright (c) 2026, eCentric and contributors
"""Repo gia cho test service khong can bench (frappe-rules muc 13). Chay:
python -m unittest discover -s ecentric_workspace/host_qc/tests -t ."""
import datetime as _dt

NOW = _dt.datetime(2026, 11, 24, 20, 0, 0)


def clock():
    return NOW


SETTINGS = {"rules_version": "v1", "deduction_minor": 3, "deduction_major": 10, "deduction_critical": 18,
            "green_min": 85, "yellow_min": 70, "yellow_minor_count": 5, "red_major_count": 2,
            "alert_minor_at": 5, "alert_major_at": 2, "evidence_before_s": 15, "evidence_after_s": 15,
            "evidence_max_s": 30, "evidence_height": 480, "evidence_bitrate_k": 1000, "clip_keep_days": 30,
            "llm_window_s": 60, "llm_models": "m1\nm2", "claude_model": "claude-x"}


class FakeSettings:
    def __init__(self, **over):
        self.d = dict(SETTINGS, **over)
        self.secrets = {"kie_api_key": "kie-secret", "claude_api_key": "cl-secret"}

    def get(self):
        return dict(self.d)

    def secret(self, f):
        return self.secrets.get(f, "")

    def set_rules_version(self, v):
        self.d["rules_version"] = v


def rule(code, group, severity="", default_review="", deduct_only_valid=0, params=(), fmts=(), enabled=1):
    return {"name": code, "code": code, "title": code, "group": group, "enabled": enabled, "severity": severity,
            "default_review": default_review, "deduct_only_valid": deduct_only_valid, "how": "", "default_text": "",
            "tune_tip": "", "params": [{"key": k, "value": v, "unit": "", "description": ""} for k, v in params],
            "format_overrides": [dict(zip(("format", "enabled", "key", "value"), f)) for f in fmts]}


RULES = [rule("VOI-01", "A", "Minor", params=[("min_db", -38.0), ("clear_ratio", 0.95)]),
         rule("VOI-02", "A", "Major", "Need Review", 1, params=[("dedupe_min", 10.0)]),
         rule("CMP-01", "B", "Critical"), rule("ENG-01", "C"),
         rule("SAL-01", "D", "Major", params=[("gap_min", 5.0)], fmts=[("branding", "Kế thừa", "gap_min", 10.0)]),
         rule("SAL-02", "D", "Major", fmts=[("branding", "Tắt", "", None)]),
         rule("GENERAL-01", "–")]


class FakeRules:
    def __init__(self, rows=None):
        self.rows = list(RULES if rows is None else rows)

    def list_all(self, version=None):
        return [dict(r) for r in self.rows]

    def exists(self, code):
        return any(r["code"] == code for r in self.rows)

    def insert(self, values):
        self.rows.append(dict(values, name=values["code"]))
        return values["code"]


class FakeMachines:
    def __init__(self):
        self.m = {}
        self.mic_rows = {}
        self.current = {}
        self.hb = {}

    def add(self, mid, token_hash="", enabled=1):
        self.m[mid] = {"name": mid, "machine_id": mid, "enabled": enabled, "token_hash": token_hash}
        self.mic_rows.setdefault(mid, [])

    def get_auth(self, mid):
        return self.m.get(mid)

    def exists(self, mid):
        return mid in self.m

    def set_token(self, mid, h, user, at):
        self.m[mid]["token_hash"] = h

    def update_heartbeat(self, mid, vals):
        self.hb[mid] = vals

    def mics(self, mid):
        return [dict(r) for r in self.mic_rows.get(mid, [])]

    def touch_mic(self, name, ch, at):
        for rows in self.mic_rows.values():
            for r in rows:
                if r["name"] == name:
                    r.update(channels=ch, last_seen=at)

    def add_mic(self, mid, idx, dev, hostapi, ch, at):
        self.mic_rows[mid].append({"name": "%s-%d" % (mid, idx), "idx": idx, "device_name": dev,
                                   "hostapi": hostapi, "channels": ch, "last_seen": at})

    def set_current_session(self, mid, sid):
        self.current[mid] = sid

    def current_session(self, mid):
        return self.current.get(mid)


class FakeSessions:
    def __init__(self):
        self.s = {}
        self.created = []

    def add(self, sid, machine="M1", status="Ready", planned_start=NOW, **kw):
        self.s[sid] = dict({"name": sid, "session_id": sid, "machine": machine, "status": status,
                            "planned_start": planned_start, "started_at": None, "hosts": [], "platform": "tiktok",
                            "format": "sales"}, **kw)

    def get_brief(self, sid):
        return dict(self.s[sid]) if sid in self.s else None

    def get_full(self, sid):
        return dict(self.s[sid]) if sid in self.s else None

    def ready_for_machine(self, mid, frm, to, status):
        return [{"name": d["name"], "planned_start": d["planned_start"]} for d in self.s.values()
                if d["machine"] == mid and d["status"] == status and frm <= d["planned_start"] <= to]

    def hosts(self, sid):
        return list(self.s[sid].get("hosts") or [])

    def create(self, values, from_machine=False):
        self.created.append((values, from_machine))
        self.s[values["session_id"]] = dict(values, name=values["session_id"])
        return values["session_id"]

    def update(self, sid, vals):
        self.s[sid].update(vals)


class FakeViolations:
    def __init__(self):
        self.v = {}
        self.logs = []

    def get(self, vid):
        return dict(self.v[vid]) if vid in self.v else None

    def insert(self, vals):
        self.v[vals["violation_id"]] = dict(vals, name=vals["violation_id"])

    def update(self, vid, vals):
        self.v[vid].update(vals)

    def for_scoring(self, sid):
        return [dict(x) for x in self.v.values() if x["session"] == sid]

    def reviewed(self, sid):
        return [dict(x) for x in self.v.values() if x["session"] == sid and x.get("reviewed_at")]

    def add_review_log(self, vid, row):
        self.logs.append((vid, row))


class FakeLogs:
    def __init__(self):
        self.rows = {}

    def exists(self, key):
        return key in self.rows

    def insert(self, vals):
        self.rows[vals["idem_key"]] = vals


class FakeAttempts:
    def __init__(self):
        self.n = {}

    def failures(self, ip):
        return self.n.get(ip, 0)

    def add_failure(self, ip):
        self.n[ip] = self.n.get(ip, 0) + 1
