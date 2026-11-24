# Copyright (c) 2026, eCentric and contributors
"""violation: app gui 1 loi (CONTRACTS A.4). Idempotent theo id - gui lai thi CAP NHAT, khong tao trung.

- Tao moi: review = Pending (hoac Need Review neu Critical / ma co default_review / app gui Need Review).
- Cap nhat (app keo dai end, nang Minor -> Critical...): sua noi dung, KHONG dung toi ket qua duyet -
  duyet chi lam tren ERP (anh Vinh chot 23/11).
Sau moi lan ghi: tinh lai diem phien."""
from ecentric_workspace.host_qc.constants import messages as M
from ecentric_workspace.host_qc.constants.rules import EXCERPT_MAX, QUOTE_MAX, TEXT_MAX, VIOLATION_ID_RE
from ecentric_workspace.host_qc.constants.statuses import APP_SET_REVIEWS, ClipStatus, Review, Severity
from ecentric_workspace.host_qc.exceptions import ForbiddenError, InvalidInput, NotFoundError
from ecentric_workspace.host_qc.repositories.session_repository import SessionRepository
from ecentric_workspace.host_qc.repositories.violation_repository import ViolationRepository
from ecentric_workspace.host_qc.services.build_rules_config_service import BuildRulesConfigService
from ecentric_workspace.host_qc.services.rescore_session_service import RescoreSessionService
from ecentric_workspace.host_qc.utils.time import rel, to_dt, to_ms

SOURCES = ("rule", "llm", "rule+llm")
LEVEL = {Severity.MINOR.value: 1, Severity.MAJOR.value: 2, Severity.CRITICAL.value: 3}


def mark(text, spans):
    """Danh dau cau loi bang « » theo highlight [[i, j]] cua app (neu doan chep loi chua co dau)."""
    text = str(text or "")
    if "«" in text or not isinstance(spans, list):
        return text
    for sp in sorted([s for s in spans if isinstance(s, (list, tuple)) and len(s) == 2], reverse=True):
        i, j = int(sp[0]), int(sp[1])
        if 0 <= i < j <= len(text):
            text = text[:i] + "«" + text[i:j] + "»" + text[j:]
    return text


def needs_check(severity, review):
    """Critical chua duoc QC chot (Valid / False Positive) = con cho xac minh."""
    return 1 if severity == Severity.CRITICAL.value and review not in (Review.VALID.value,
                                                                       Review.FALSE_POSITIVE.value) else 0


class RecordViolationService:
    def __init__(self, sessions=None, violations=None, rules_config=None, rescore=None):
        self.sessions = sessions or SessionRepository()
        self.violations = violations or ViolationRepository()
        self.rules_config = rules_config or BuildRulesConfigService()
        self.rescore = rescore or RescoreSessionService(self.sessions, self.violations, self.rules_config)

    def execute(self, machine, v):
        vid = str(v.get("id") or v.get("violation_id") or "").strip()
        if not VIOLATION_ID_RE.match(vid):
            raise InvalidInput(M.BAD_VIOLATION_ID)
        s = self.sessions.get_brief(str(v.get("session_id") or ""))
        if not s:
            raise NotFoundError(M.NO_SESSION % v.get("session_id"))
        if s["machine"] != machine["name"]:
            raise ForbiddenError(M.WRONG_MACHINE)
        rules = self.rules_config.execute()
        old = self.violations.get(vid)
        vals = self._content(v, s, rules)
        if old:
            if LEVEL.get(vals["severity"], 0) > LEVEL.get(old.get("severity"), 0) \
                    and vals["severity"] == Severity.CRITICAL.value and old.get("review") == Review.PENDING.value:
                vals["review"] = Review.NEED_REVIEW.value
            vals["needs_verification"] = needs_check(vals["severity"], vals.get("review") or old.get("review"))
            self.violations.update(vid, vals)
        else:
            vals.update(violation_id=vid, session=s["name"], review=self._first_review(v, vals, rules),
                        clip_status=ClipStatus.NONE.value)
            vals["needs_verification"] = needs_check(vals["severity"], vals["review"])
            self.violations.insert(vals)
        self.rescore.execute(s["name"], rules)
        return {"name": vid}

    @staticmethod
    def _first_review(v, vals, rules):
        code_rule = (rules.get("codes") or {}).get(vals["code"]) or {}
        if vals["severity"] == Severity.CRITICAL.value or code_rule.get("default_review") == Review.NEED_REVIEW.value:
            return Review.NEED_REVIEW.value
        return v.get("review") if v.get("review") in APP_SET_REVIEWS else Review.PENDING.value

    def _content(self, v, s, rules):
        sev = v.get("severity") if v.get("severity") in LEVEL else Severity.MINOR.value
        start, end = to_dt(v.get("start")), to_dt(v.get("end") or v.get("start"))
        t0 = to_ms(s.get("started_at")) if s.get("started_at") else None
        srel = v.get("start_rel_ms") if v.get("start_rel_ms") is not None else ((to_ms(start) - t0) if (t0 and start) else 0)
        erel = v.get("end_rel_ms") if v.get("end_rel_ms") is not None else ((to_ms(end) - t0) if (t0 and end) else 0)
        code = str(v.get("code") or "")[:20]
        host_id = str(v.get("host_id") or "")[:20] or None
        return {"code": code, "group": str(v.get("group") or ((rules.get("codes") or {}).get(code) or {}).get("group") or "")[:4],
                "severity": sev, "host_id": host_id, "host_name": self._host_name(s["name"], host_id, v),
                "start_time": start, "end_time": end, "start_rel": rel(srel), "end_rel": rel(erel),
                "quote": str(v.get("quote") or "")[:QUOTE_MAX], "reason": str(v.get("reason") or "")[:TEXT_MAX],
                "transcript_excerpt": mark(v.get("transcript_excerpt"), v.get("highlight"))[:EXCERPT_MAX],
                "source": v.get("source") if v.get("source") in SOURCES else "rule",
                "model": str(v.get("model") or "")[:80],
                "deduction": int(float(v.get("deduction") or (rules.get("deduction") or {}).get(sev) or 0))}

    def _host_name(self, session_name, host_id, v):
        if v.get("host_name"):
            return str(v["host_name"])[:140]
        if not host_id:
            return ""
        for h in self.sessions.hosts(session_name):
            if h["host_id"] == host_id:
                return h.get("host_name") or host_id
        return host_id
