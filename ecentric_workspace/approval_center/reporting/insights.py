# Copyright (c) 2026, eCentric and contributors
"""Rule-based (NOT generative) insight generation for the Approval Center dashboard.

Each rule inspects the already-computed dashboard datasets and, when its threshold is
met, emits an insight: {code, severity(info|warning|critical), statement, metric,
filter}. `filter` is a governed patch the frontend applies for drill-down (or None).
All thresholds are module constants so they can move to config later.
"""

PENDING_SWING_PCT = 20.0           # pending changed vs prior period
COMPLETION_DROP_PCT = -10.0        # completion-rate decline
AVG_TIME_DETERIORATION_PCT = 20.0  # average approval time worsened
APPROVER_HIGH_LOAD = 10            # pending items on one approver


def _fmt_pct(v):
    return ("+" if (v or 0) > 0 else "") + str(v) + "%"


def generate(dash, now=None):
    ins = []
    kpis = dash.get("kpis", {})
    comp = dash.get("comparison", {})

    # 1) Pending swing vs prior period
    c = comp.get("pending")
    if c and c.get("pct") is not None and abs(c["pct"]) >= PENDING_SWING_PCT:
        up = c["pct"] > 0
        ins.append({
            "code": "pending_swing",
            "severity": "warning" if up else "info",
            "statement": ("Hồ sơ chờ xử lý %s %s so với kỳ trước."
                          % ("tăng" if up else "giảm", _fmt_pct(c["pct"]))),
            "metric": "%d → %d" % (c.get("previous") or 0, c.get("current") or 0),
            "filter": {"status": "Pending", "view": "open"},
        })

    # 2) Top department contributing to SLA breaches
    dp = sorted(dash.get("department_performance", []), key=lambda x: -(x.get("breaches") or 0))
    if dp and (dp[0].get("breaches") or 0) > 0:
        top = dp[0]
        ins.append({
            "code": "top_breach_department",
            "severity": "critical" if top["breaches"] >= 3 else "warning",
            "statement": "Phòng ban '%s' đang dẫn đầu về số hồ sơ quá hạn SLA." % (top.get("department") or "—"),
            "metric": "%d hồ sơ quá hạn" % top["breaches"],
            "filter": {"department": top.get("department"), "sla_state": "breached", "view": "open"},
        })

    # 3) Top bottleneck level
    bl = dash.get("bottleneck_levels", [])
    if bl and (bl[0].get("avg_completed_seconds") or bl[0].get("avg_pending_seconds")):
        top = bl[0]
        secs = top.get("avg_completed_seconds") or top.get("avg_pending_seconds")
        ins.append({
            "code": "top_bottleneck_level",
            "severity": "warning",
            "statement": "Cấp duyệt '%s' đang là điểm nghẽn lâu nhất." % top.get("level"),
            "metric": "TB %.1f giờ" % ((secs or 0) / 3600.0),
            "filter": None,
        })

    # 4) Approver with unusually high pending workload
    ap = dash.get("pending_by_approver", [])
    if ap and (ap[0].get("count") or 0) >= APPROVER_HIGH_LOAD:
        top = ap[0]
        ins.append({
            "code": "approver_high_load",
            "severity": "warning",
            "statement": "Người duyệt '%s' đang tồn đọng khối lượng lớn bất thường." % top.get("label"),
            "metric": "%d hồ sơ chờ" % top["count"],
            "filter": {"approver": top.get("label"), "view": "open"},
        })

    # 5) Requests older than P90 of completed duration
    p90 = None
    for b in bl:
        if b.get("p90_seconds"):
            p90 = max(p90 or 0, b["p90_seconds"])
    longest = dash.get("longest_pending", [])
    if p90 and longest:
        over = [r for r in longest if (r.get("pending_age_seconds") or 0) > p90]
        if over:
            ins.append({
                "code": "older_than_p90",
                "severity": "critical",
                "statement": "Có %d hồ sơ đang chờ lâu hơn ngưỡng P90 của thời gian duyệt." % len(over),
                "metric": "P90 ≈ %.1f giờ" % (p90 / 3600.0),
                "filter": {"sla_state": "breached", "view": "open"},
            })

    # 6) Completion-rate decline vs prior period
    cr = comp.get("completion_rate")
    if cr and cr.get("delta") is not None and cr["delta"] <= COMPLETION_DROP_PCT:
        ins.append({
            "code": "completion_decline",
            "severity": "warning",
            "statement": "Tỷ lệ hoàn tất giảm so với kỳ trước.",
            "metric": "%s%% → %s%%" % (cr.get("previous"), cr.get("current")),
            "filter": {"status": "Completed", "view": "period"},
        })

    # 7) Average approval time deterioration
    at = comp.get("avg_approval_seconds")
    if at and at.get("pct") is not None and at["pct"] >= AVG_TIME_DETERIORATION_PCT:
        ins.append({
            "code": "avg_time_deterioration",
            "severity": "warning",
            "statement": "Thời gian duyệt trung bình xấu đi %s so với kỳ trước." % _fmt_pct(at["pct"]),
            "metric": "%.1f → %.1f giờ" % ((at.get("previous") or 0) / 3600.0, (at.get("current") or 0) / 3600.0),
            "filter": None,
        })

    if not ins:
        ins.append({"code": "all_clear", "severity": "info",
                    "statement": "Không phát hiện bất thường trong phạm vi và kỳ đã chọn.",
                    "metric": "", "filter": None})
    return ins
