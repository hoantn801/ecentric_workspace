# Copyright (c) 2026, eCentric and contributors
"""Cham diem phien tu danh sach loi - CUNG cong thuc voi app (src/rules/scoring.js), thuan tuy, khong I/O.

- Loi khong phai False Positive tru `deduction[muc]` vao nhom cua ma; diem nhom khong am; tong = 4 nhom.
- Ma co `count_after_valid` (VOI-02, ma thu nghiem): chi tru khi da duyet Valid Violation.
- RED: tong < yellow_min, hoac >= red_major_count Major, hoac >= 1 Critical.
  YELLOW: tong < green_min, hoac >= 1 Major, hoac >= yellow_minor_count Minor. Con lai GREEN.
"""
from ecentric_workspace.host_qc.constants.statuses import Color, Review, SEVERITIES, Severity
from ecentric_workspace.host_qc.utils.time import rel, to_ms


class ComputeScoreService:
    def execute(self, violations, rules, t0=None):
        groups = {g: {"name": d.get("name"), "max": int(d.get("max") or 0), "lost": 0}
                  for g, d in (rules.get("groups") or {}).items()}
        codes = rules.get("codes") or {}
        ded = rules.get("deduction") or {}
        counts = {s: 0 for s in SEVERITIES}
        explain, needs = [], False
        t0ms = to_ms(t0) if t0 else None
        for v in sorted(violations, key=lambda x: to_ms(x.get("start_time")) or 0):
            if not self._counted(v, codes.get(v.get("code")) or {}):
                if v.get("review") != Review.FALSE_POSITIVE.value:      # giong app: ghi "chua tinh, cho QC"
                    explain.append(self._line(v, 0, t0ms) + " – chưa tính, chờ QC xác nhận")
                continue
            sev = v.get("severity")
            if sev not in counts:
                continue
            counts[sev] += 1
            minus = int(ded.get(sev) or 0)
            if v.get("group") in groups:
                groups[v["group"]]["lost"] += minus
            if sev == Severity.CRITICAL.value and v.get("review") != Review.VALID.value:
                needs = True
            explain.append(self._line(v, minus, t0ms))
        total = 0
        out_groups = {}
        for g, d in groups.items():
            score = max(0, d["max"] - d["lost"])
            total += score
            out_groups[g] = {"name": d["name"], "max": d["max"], "score": score}
        return {"total": total, "groups": out_groups, "counts": counts,
                "status": self._color(total, counts, rules.get("status") or {}),
                "needs_verification": needs, "explain": explain}

    @staticmethod
    def _counted(v, code_rule):
        review = v.get("review")
        if review == Review.FALSE_POSITIVE.value:
            return False
        if code_rule.get("count_after_valid") and review != Review.VALID.value:
            return False
        return True

    @staticmethod
    def _color(total, counts, st):
        green_min, yellow_min = int(st.get("green_min", 85)), int(st.get("yellow_min", 70))
        minor_yellow, major_red = int(st.get("yellow_minor_count", 5)), int(st.get("red_major_count", 2))
        if total < yellow_min or counts["Major"] >= major_red or counts["Critical"] >= 1:
            return Color.RED.value
        if total < green_min or counts["Major"] >= 1 or counts["Minor"] >= minor_yellow:
            return Color.YELLOW.value
        return Color.GREEN.value

    @staticmethod
    def _line(v, minus, t0ms):
        s, e = to_ms(v.get("start_time")), to_ms(v.get("end_time") or v.get("start_time"))
        span = "%s–%s" % (rel((s or 0) - t0ms), rel((e or 0) - t0ms)) if t0ms and s else ""
        who = " · %s" % (v.get("host_name") or v.get("host_id")) if (v.get("host_name") or v.get("host_id")) else ""
        rv = v.get("review")
        tail = " (%s)" % rv if rv and rv != Review.PENDING.value else ""
        return "%s −%d: %s %s %s%s%s" % (v.get("group"), minus, v.get("code"), v.get("severity"), span, who, tail)
