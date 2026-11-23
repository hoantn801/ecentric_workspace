# Copyright (c) 2026, eCentric and contributors
"""next_session: phien Ready cua chinh may nay, planned_start trong [now-60', now+30'], gan gio nhat.

Tra SessionConfig (CONTRACTS A.1) + rules_config + ai. Khoa AI chi tra cho may da xac thuc token."""
import re

from ecentric_workspace.host_qc.constants.rules import NEXT_SESSION_AFTER_MIN, NEXT_SESSION_BEFORE_MIN
from ecentric_workspace.host_qc.constants.statuses import SessionStatus
from ecentric_workspace.host_qc.repositories.banned_phrase_repository import BannedPhraseRepository
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService, num
from ecentric_workspace.host_qc.utils.time import iso, now, to_dt
import datetime as _dt

SPLIT = re.compile(r"[,\n;]+")


def words(text):
    return [x.strip() for x in SPLIT.split(text or "") if x.strip()]


def lines(text):
    return [x.strip() for x in (text or "").splitlines() if x.strip()]


class GetNextSessionService:
    def __init__(self, sessions=None, banned=None, settings=None, rules_config=None, clock=now):
        self.sessions = sessions or SessionRepository()
        self.banned = banned or BannedPhraseRepository()
        self.settings = settings or SettingsRepository()
        self.rules_config = rules_config or BuildRulesConfigService(settings=self.settings)
        self.clock = clock

    def execute(self, machine):
        at = self.clock()
        rows = self.sessions.ready_for_machine(
            machine["name"], at - _dt.timedelta(minutes=NEXT_SESSION_BEFORE_MIN),
            at + _dt.timedelta(minutes=NEXT_SESSION_AFTER_MIN), SessionStatus.READY.value)
        if not rows:
            return None
        best = min(rows, key=lambda r: abs((to_dt(r["planned_start"]) - at).total_seconds()))
        doc = self.sessions.get_full(best["name"])
        cfg = self.to_config(doc, self.banned.for_platform(doc.get("platform")))
        cfg["rules_config"] = self.rules_config.execute()
        cfg["ai"] = self._ai()
        return cfg

    def _ai(self):
        s = self.settings.get()
        return {"kie_api_key": self.settings.secret("kie_api_key"),
                "claude_api_key": self.settings.secret("claude_api_key"),
                "models": lines(s.get("llm_models")), "claude_model": s.get("claude_model") or ""}

    @staticmethod
    def to_config(d, global_banned):
        banned = {"commitment": [], "offensive": []}
        for b in list(global_banned) + list(d.get("banned_phrases") or []):
            if b.get("kind") in banned and b.get("phrase") and b["phrase"] not in banned[b["kind"]]:
                banned[b["kind"]].append(b["phrase"])
        overrides = {}
        for o in d.get("rule_overrides") or []:
            overrides.setdefault(o["code"], {})[o["key"]] = num(o.get("value"))
        rng = lambda rows: [{"from": iso(r.get("from_time")), "to": iso(r.get("to_time")), "note": r.get("note") or ""}
                            for r in rows or []]
        return {
            "session_id": d["session_id"], "title": d.get("title") or "", "brand": d.get("brand") or "",
            "platform": d.get("platform") or "tiktok", "tiktok_username": d.get("tiktok_username") or "",
            "format": d.get("format") or "sales", "push_sale": d.get("push_sale") or "medium",
            "planned_start": iso(d.get("planned_start")), "planned_end": iso(d.get("planned_end")),
            "hosts": [{"host_id": h["host_id"], "name": h.get("host_name") or "", "role": h.get("role") or "main",
                       "mic_device": h.get("mic_device") or "", "on_camera": bool(h.get("on_camera"))}
                      for h in d.get("hosts") or []],
            "products": [{"code": p["code"], "name": p.get("product_name") or "", "aliases": words(p.get("aliases")),
                          "pronunciation": p.get("pronunciation") or "", "usp": lines(p.get("usp")),
                          "target": p.get("target") or "", "price": p.get("price") or "", "deal": p.get("deal") or ""}
                         for p in d.get("products") or []],
            "deals": [{"id": x["deal_id"], "text": x.get("text") or "", "keywords": words(x.get("keywords")),
                       "important": bool(x.get("important")), "from": iso(x.get("valid_from")),
                       "to": iso(x.get("valid_to"))} for x in d.get("deals") or []],
            "banned": banned,
            "scripted_silences": rng(d.get("scripted_silences")),
            "scripted_breaks": rng(d.get("scripted_breaks")),
            "rules": {"codes": overrides} if overrides else {},
        }
