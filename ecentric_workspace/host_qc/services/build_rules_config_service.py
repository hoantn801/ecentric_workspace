# Copyright (c) 2026, eCentric and contributors
"""Dung RulesConfig (CONTRACTS A.3) tu Host QC Settings + Host QC Rule - "bang huong dan" gui cho may.

App gop: mac dinh cua app <- RulesConfig nay <- formats[format] <- rules rieng phien. Khoa ERP khong
co (coalesce_s, step_s, timeout_s...) thi app giu mac dinh cua no."""
from ecentric_workspace.host_qc.constants.rules import FORMATS, GENERAL_GROUP, GROUPS
from ecentric_workspace.host_qc.repositories.rule_repository import RuleRepository
from ecentric_workspace.host_qc.repositories.settings_repository import SettingsRepository

ON, OFF = "Bật", "Tắt"


def num(v):
    """Float tu DB -> int neu tron (5.0 -> 5) cho giong mac dinh cua app."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return v
    return int(f) if f.is_integer() else f


class BuildRulesConfigService:
    def __init__(self, settings=None, rules=None):
        self.settings = settings or SettingsRepository()
        self.rules = rules or RuleRepository()

    def execute(self):
        s = self.settings.get()
        rows = self.rules.list_all(s.get("rules_version"))
        cfg = {
            "version": s.get("rules_version") or "",
            "groups": {g: {"name": n, "max": m} for g, (n, m) in GROUPS.items()},
            "deduction": {"Minor": num(s.get("deduction_minor")), "Major": num(s.get("deduction_major")),
                          "Critical": num(s.get("deduction_critical"))},
            "status": {k: num(s.get(k)) for k in ("green_min", "yellow_min", "yellow_minor_count", "red_major_count")},
            "alert": {"minor_at": num(s.get("alert_minor_at")), "major_at": num(s.get("alert_major_at")),
                      "critical_each": True},
            "evidence": {"before_s": num(s.get("evidence_before_s")), "after_s": num(s.get("evidence_after_s")),
                         "max_s": num(s.get("evidence_max_s")), "height": num(s.get("evidence_height")),
                         "bitrate_k": num(s.get("evidence_bitrate_k")), "keep_days": num(s.get("clip_keep_days"))},
            "llm": {"window_s": num(s.get("llm_window_s")), "models": self._lines(s.get("llm_models")),
                    "claude_backup": s.get("claude_model") or ""},
            "codes": {}, "formats": {f: {} for f in FORMATS}, "guide": [],
        }
        for r in rows:
            cfg["guide"].append({"code": r["code"], "title": r.get("title") or "", "how": r.get("how") or "",
                                 "default": r.get("default_text") or "", "tune_tip": r.get("tune_tip") or ""})
            if r.get("group") == GENERAL_GROUP:
                continue
            cfg["codes"][r["code"]] = self._code(r)
            for o in r.get("format_overrides") or []:
                self._format(cfg["formats"], r["code"], o)
        return cfg

    @staticmethod
    def _lines(text):
        return [x.strip() for x in (text or "").splitlines() if x.strip()]

    @staticmethod
    def _code(r):
        c = {"group": r["group"], "enabled": bool(r.get("enabled"))}
        if r.get("severity"):
            c["severity"] = r["severity"]
        if r.get("default_review"):
            c["default_review"] = r["default_review"]
        if r.get("count_after_valid"):
            c["count_after_valid"] = True
        if r.get("experimental"):
            c["experimental"] = True
        for p in r.get("params") or []:
            if p.get("key"):
                c[p["key"]] = num(p.get("value"))
        return c

    @staticmethod
    def _format(formats, code, o):
        if o.get("format") not in formats:
            return
        tgt = formats[o["format"]].setdefault(code, {})
        if o.get("enabled") in (ON, OFF):
            tgt["enabled"] = o["enabled"] == ON
        if o.get("key"):
            tgt[o["key"]] = num(o.get("value"))
