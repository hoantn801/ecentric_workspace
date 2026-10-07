# Copyright (c) 2026, eCentric and contributors
"""PURE: dong EC AI Usage Log -> so lieu cho trang /ai-usage. Khong import frappe.

Bon goc Hoan chon 07/10: muc dung theo nguoi/phong, theo tinh nang, chi phi, chat luong.
"""
import datetime

#: Ten tinh nang tren man hinh (purpose cua gateway -> ten nguoi doc hieu).
FEATURES = {
    "khay": "eC Mate (trợ lý góc trang)",
    "chat": "Hỏi đáp số liệu",
    "formfill": "AI điền hộ phiếu",
    "weekly_report": "Chấm điểm báo cáo tuần",
    "company_summary": "Tóm tắt công ty",
    "ai_content": "AI Content livestream",
    "post_write": "Viết bài nội bộ",
    "post_cover": "Ý tưởng ảnh bìa",
    "post_cover_check": "Kiểm ảnh bìa",
    "image": "Tạo ảnh",
    "feedback_digest": "Tổng hợp góp ý",
}
SYSTEM_USERS = ("Administrator", "Guest", "")
#: AI tu chay tren du lieu cua nguoi khac (cham bao cao tuan khi nop, tong hop gop y hang thang):
#: tinh vao luot / chi phi cua tinh nang nhung KHONG tinh la "nguoi do dung AI" - neu khong,
#: ai nop bao cao tuan cung thanh "dang dung AI" va ti le ap dung vo nghia.
AUTO_PURPOSES = ("weekly_report", "feedback_digest")
USD_PER_CREDIT = 0.005


def feature_label(purpose):
    return FEATURES.get(purpose or "", purpose or "Khác")


def _pct(a, b):
    return round(100.0 * a / b, 1) if b else None


def _quantile(values, q):
    v = sorted(values)
    if not v:
        return None
    return v[min(len(v) - 1, int(q * len(v)))]


def _day(value):
    return str(value or "")[:10]


def aggregate(rows, people, start, end):
    """rows: [{user, department, purpose, model, ok, latency_ms, total_tokens, credits,
    cost_source, images, creation}]; people: {user: {name, department}} = nhan su TRONG PHAM VI
    nguoi xem (dung de tinh 'chua dung'). -> dict cho trang."""
    people = people or {}
    person, feat, dept, daily = {}, {}, {}, {}
    sys_calls = 0
    tot = {"calls": 0, "ok": 0, "credits": 0.0, "tokens": 0, "images": 0,
           "estimated": 0, "unpriced": 0}
    for r in rows or []:
        u = r.get("user") or ""
        ok = 1 if r.get("ok") else 0
        cr = float(r.get("credits") or 0)
        lat = int(r.get("latency_ms") or 0)
        day = _day(r.get("creation"))
        purpose = r.get("purpose") or "?"
        tot["calls"] += 1
        tot["ok"] += ok
        tot["credits"] += cr
        tot["tokens"] += int(r.get("total_tokens") or 0)
        tot["images"] += int(r.get("images") or 0)
        src = r.get("cost_source") or ""
        if src == "estimate":
            tot["estimated"] += 1
        elif src != "kie":
            tot["unpriced"] += 1

        f = feat.setdefault(purpose, {"purpose": purpose, "label": feature_label(purpose),
                                      "calls": 0, "ok": 0, "users": set(), "lat": [],
                                      "credits": 0.0, "system": 0})
        f["calls"] += 1
        f["ok"] += ok
        f["credits"] += cr
        if ok and lat:
            f["lat"].append(lat)

        d = daily.setdefault(day, {"date": day, "calls": 0, "users": set()})
        d["calls"] += 1

        if u in SYSTEM_USERS or purpose in AUTO_PURPOSES:
            sys_calls += 1
            f["system"] += 1
            continue
        f["users"].add(u)
        d["users"].add(u)
        info = people.get(u) or {}
        dep = info.get("department") or r.get("department") or "Chưa gắn phòng"
        p = person.setdefault(u, {"user": u, "name": info.get("name") or u, "department": dep,
                                  "calls": 0, "ok": 0, "days": set(), "features": {},
                                  "credits": 0.0, "last": ""})
        p["calls"] += 1
        p["ok"] += ok
        p["credits"] += cr
        p["days"].add(day)
        p["features"][purpose] = p["features"].get(purpose, 0) + 1
        p["last"] = max(p["last"], str(r.get("creation") or ""))
        g = dept.setdefault(dep, {"department": dep, "calls": 0, "users": set(), "credits": 0.0})
        g["calls"] += 1
        g["credits"] += cr
        g["users"].add(u)

    for u, info in people.items():
        dep = info.get("department") or "Chưa gắn phòng"
        dept.setdefault(dep, {"department": dep, "calls": 0, "users": set(), "credits": 0.0})
    headcount = {}
    for info in people.values():
        dep = info.get("department") or "Chưa gắn phòng"
        headcount[dep] = headcount.get(dep, 0) + 1

    by_person = sorted(({
        "user": p["user"], "name": p["name"], "department": p["department"],
        "calls": p["calls"], "days": len(p["days"]), "ok_rate": _pct(p["ok"], p["calls"]),
        "credits": round(p["credits"], 2), "usd": round(p["credits"] * USD_PER_CREDIT, 2),
        "last": p["last"][:16],
        "features": [{"purpose": k, "label": feature_label(k), "calls": v}
                     for k, v in sorted(p["features"].items(), key=lambda kv: -kv[1])],
    } for p in person.values()), key=lambda x: (-x["calls"], x["name"]))

    by_feature = sorted(({
        "purpose": f["purpose"], "label": f["label"], "calls": f["calls"],
        "users": len(f["users"]), "system_calls": f["system"],
        "ok_rate": _pct(f["ok"], f["calls"]), "error_calls": f["calls"] - f["ok"],
        "p50_ms": _quantile(f["lat"], 0.5), "p90_ms": _quantile(f["lat"], 0.9),
        "credits": round(f["credits"], 2), "usd": round(f["credits"] * USD_PER_CREDIT, 2),
    } for f in feat.values()), key=lambda x: -x["calls"])

    by_department = sorted(({
        "department": g["department"], "headcount": headcount.get(g["department"], 0),
        "active": len(g["users"]), "calls": g["calls"],
        "adoption_pct": _pct(len(g["users"]), headcount.get(g["department"], 0)),
        "credits": round(g["credits"], 2), "usd": round(g["credits"] * USD_PER_CREDIT, 2),
    } for g in dept.values()), key=lambda x: (-x["calls"], x["department"]))

    series = []
    try:
        d0 = datetime.date.fromisoformat(str(start)[:10])
        d1 = datetime.date.fromisoformat(str(end)[:10])
        while d0 <= d1:
            k = d0.isoformat()
            x = daily.get(k) or {"calls": 0, "users": set()}
            series.append({"date": k, "calls": x["calls"], "users": len(x["users"])})
            d0 += datetime.timedelta(days=1)
    except ValueError:
        series = [{"date": k, "calls": v["calls"], "users": len(v["users"])}
                  for k, v in sorted(daily.items())]

    used = set(person)
    never = sorted(({"user": u, "name": i.get("name") or u,
                     "department": i.get("department") or "Chưa gắn phòng"}
                    for u, i in people.items() if u not in used),
                   key=lambda x: (x["department"], x["name"]))
    in_scope_active = len([u for u in used if u in people]) if people else len(used)
    return {
        "totals": {
            "calls": tot["calls"], "user_calls": tot["calls"] - sys_calls, "system_calls": sys_calls,
            "active_users": len(used), "headcount": len(people),
            "adoption_pct": _pct(in_scope_active, len(people)),
            "ok_rate": _pct(tot["ok"], tot["calls"]), "tokens": tot["tokens"],
            "images": tot["images"], "credits": round(tot["credits"], 2),
            "usd": round(tot["credits"] * USD_PER_CREDIT, 2),
            "cost_estimated_calls": tot["estimated"], "cost_unpriced_calls": tot["unpriced"],
        },
        "by_feature": by_feature, "by_person": by_person, "by_department": by_department,
        "daily": series, "never": never,
    }


def funnel(logs, statuses):
    """PURE. AI dien ho: goi y -> nhap tao -> da gui. logs: [{outcome, business_doc}],
    statuses: {business_doc: approval_status}. 'Da gui' = phieu khong con o Draft."""
    suggested = sum(1 for l in logs or [] if l.get("outcome") == "ok")
    drafts = [l["business_doc"] for l in logs or [] if l.get("business_doc")]
    sent = sum(1 for b in drafts if (statuses or {}).get(b) not in (None, "", "Draft"))
    return {"suggested": suggested, "drafts": len(drafts), "sent": sent,
            "sent_pct": _pct(sent, len(drafts))}
