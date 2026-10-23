# Copyright (c) 2026, eCentric and contributors
"""May phat gui tin hieu moi ~30 s: trang thai tung live, so lieu OBS/may, canh bao, lich live, anh nho.
Luu ban moi nhat (ghi de) + 1 mau so lieu/phut. Anh hong khong lam hong ca lan gui."""
import base64
import binascii

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.application import _common
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R
from ecentric_workspace.ai_tools.features.ai_live.domain import machine_watch_rules as W
from ecentric_workspace.ai_tools.features.ai_live.domain import session_rules as S


def decode_thumb(b64):
    """chuoi base64 (co the kem tien to data:) -> (bytes, 'jpg'|'png'). Loi -> AiLiveError."""
    s = str(b64 or "")
    if s.startswith("data:"):
        s = s.split(",", 1)[-1]
    if len(s) > C.MAX_THUMB_BYTES * 4 // 3 + 8:
        raise C.AiLiveError(C.MonMsg.BAD_HB % "ảnh quá lớn")
    try:
        data = base64.b64decode(s, validate=True)
    except (binascii.Error, ValueError):
        raise C.AiLiveError(C.MonMsg.BAD_HB % "ảnh")
    if data[:3] == b"\xff\xd8\xff":
        return data, "jpg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return data, "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":            # fix10g: platform_thumb_b64 co the la WEBP
        return data, "webp"
    raise C.AiLiveError(C.MonMsg.BAD_HB % "ảnh không phải jpg/png/webp")


class PushHeartbeatService:
    def __init__(self, machines=None, health=None, samples=None, thumbs=None, clock=None, summaries=None):
        from ecentric_workspace.ai_tools.features.ai_live.application import _deps_monitor as D
        self.machines = machines or D.machines()
        self.health = health or D.health()
        self.samples = samples or D.samples()
        self.thumbs = thumbs or D.thumbs()
        self.clock = clock or R.now_ts
        self._summaries = summaries               # fix10d: tong ket cuoi phien gui kem tin hieu (nap muon)

    def execute(self, user, payload):
        p = payload if isinstance(payload, dict) else (_common.parse_json(payload, "tín hiệu") or {})
        m = _common.require_machine(self.machines, user, p.get("machine"))
        lives = p.get("lives")
        if isinstance(lives, str):
            lives = _common.parse_json(lives, "lives")
        if not isinstance(lives, list):
            raise C.AiLiveError(C.MonMsg.BAD_HB % "lives")
        lives = lives[:C.MAX_HB_LIVES]              # fix10g: thua thi cat, khong bo ca nhip (bo nhip = bao "may im lang" gia)
        now, allowed, top = self.clock(), _common.machine_brands(m), p.get("thumb_b64")
        self._minimal = bool(p.get("minimal"))          # may tai cao: lives rut gon -> giu so lieu / canh bao lan truoc
        self._m = m
        self.machines.save_heartbeat(m["machine_code"], W.heartbeat_vals(p, lives, m, now))  # fix10f: nhip tim ca may
        saved, skipped = [], []
        for lv in lives:
            why = self._one(m["machine_code"], allowed, lv if isinstance(lv, dict) else {}, top, len(lives), now)
            live = str((lv or {}).get("live") or "")[:40] if isinstance(lv, dict) else ""
            (skipped.append({"live": live, "why": why}) if why else saved.append(live))
        return {"saved": saved, "skipped": skipped, "server_time": now}

    def _one(self, machine, allowed, lv, top, n_lives, now):
        live, brand = str(lv.get("live") or ""), str(lv.get("brand") or "")
        if not C.LIVE_RE.match(live):
            return "mã live"
        if brand and brand not in allowed:
            return "brand chưa giao cho máy"
        key = R.key_of(machine, live)
        prev = self.health.get(key) or {}
        state = str(lv.get("state") or "").lower()
        state = state if state in C.LIVE_STATES else "idle"
        if self._minimal and "metrics" not in lv:
            metrics = prev.get("metrics") or {}
            app_alerts = [a for a in prev.get("alerts") or [] if a.get("src") == "app"]
        else:
            metrics, app_alerts = R.normalize_metrics(lv.get("metrics"), now), lv.get("alerts")
        alerts = R.merge_alerts(app_alerts, R.metric_reasons(state, metrics), prev.get("alerts"), now)
        row = {"machine": machine, "live": live, "brand": brand, "state": state, "last_seen_ts": now,
               "app_version": str(lv.get("app_version") or "")[:20], "metrics": metrics, "alerts": alerts,
               "schedule": R.sanitize_schedule(lv["schedule"]) if "schedule" in lv else (prev.get("schedule") or [])}
        if "detail" in lv:                       # fix10d: chi tiet phien (dang phat, sap phat, hang cau hoi...) - ghi de
            row["detail"] = S.sanitize_detail(lv.get("detail"), now) or {}
        obs = lv.get("thumb_b64") or (top.get(live) if isinstance(top, dict) else (top if n_lives == 1 else None))
        bad = []
        for kind, b64 in (("obs", obs), ("phone", lv.get("phone_thumb_b64")), ("platform", lv.get("platform_thumb_b64")),
                         ("stream", lv.get("stream_thumb_b64"))):
            if not b64:
                continue
            try:
                data, ext = decode_thumb(b64)
            except C.AiLiveError:
                bad.append(kind)
                continue
            self.thumbs.save(key, kind, data, ext)
            row[kind + "_thumb_ts"] = now
        self.health.upsert(key, row)
        if now - self.samples.last_ts(key) >= C.SAMPLE_EVERY_S and not (self._minimal and "metrics" not in lv):
            top_level = max([C.LEVEL_RANK[a["level"]] for a in alerts] or [0])
            self.samples.insert(key, now, {3: C.Level.CRIT, 2: C.Level.WARN}.get(top_level, C.Level.OK), metrics)
        if lv.get("session_summary"):
            try:
                self._summary_svc().save(self._m, live, brand, lv["session_summary"])
            except C.AiLiveError as e:
                bad.append("tổng kết phiên (%s)" % e)
        return ("ảnh hỏng: " + ", ".join(bad)) if bad else None

    def _summary_svc(self):
        if self._summaries is None:
            from ecentric_workspace.ai_tools.features.ai_live.application.push_session_summary_service import \
                PushSessionSummaryService
            self._summaries = PushSessionSummaryService(machines=self.machines, clock=self.clock)
        return self._summaries
