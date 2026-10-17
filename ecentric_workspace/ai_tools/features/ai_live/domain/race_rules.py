# Copyright (c) 2026, eCentric and contributors
"""Dua vit (W20) - luat thuan Python: chuan hoa ket qua app gui, gop trang thai trao giai (ERP sua / app sua),
tham so lenh start_race, giai ma anh PNG, CSV. Khong goi DB."""
import base64
import binascii
import csv
import hashlib
import io
from datetime import datetime

from ecentric_workspace.ai_tools.features.ai_live import constants as C
from ecentric_workspace.ai_tools.features.ai_live.domain import health_rules as R

_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _txt(v, n=C.MAX_RACE_TEXT):
    return " ".join(str(v if v is not None else "").split())[:n]


def _int(v, lo=0, hi=10 ** 6):
    try:
        return max(lo, min(hi, int(float(v))))
    except (TypeError, ValueError):
        return lo


def prize_label(code_or_label):
    """Ma app (chua_trao...) hoac nhan ERP -> nhan ERP; khong nhan ra -> None."""
    v = str(code_or_label or "").strip()
    if v in C.PRIZE_STATUS:
        return C.PRIZE_STATUS[v]
    return v if v in C.PRIZE_STATUS.values() else None


def prize_code(label):
    return next((k for k, v in C.PRIZE_STATUS.items() if v == label), C.PRIZE_DEFAULT)


def outcome_of(status):
    s = str(status or "").strip().lower()
    if s.startswith("cancelled"):
        return "cancelled"
    return s if s in C.RACE_OUTCOMES else "cancelled"


def vn_date(ts):
    return datetime.fromtimestamp(ts, R._VN).strftime("%Y-%m-%d")


def sanitize_race(raw, now):
    """Ket qua 1 cuoc dua tu app -> dict gon. Thieu ma / ma sai -> AiLiveError."""
    if not isinstance(raw, dict):
        raise C.AiLiveError(C.RaceMsg.BAD_RACE % "thiếu khối race")
    rid = str(raw.get("id") or "").strip()
    if not C.RACE_ID_RE.match(rid):
        raise C.AiLiveError(C.RaceMsg.BAD_ID)
    live = str(raw.get("live") or "").strip()
    if not C.LIVE_RE.match(live):
        raise C.AiLiveError(C.RaceMsg.BAD_RACE % "mã live")
    ts = {k: R._epoch(raw.get(k)) for k in ("reg_started_at", "race_started_at", "finished_at")}
    ts = {k: (v if v and 0 < v <= now + 86400 else None) for k, v in ts.items()}
    anchor = ts["finished_at"] or ts["race_started_at"] or ts["reg_started_at"] or now
    tiers = [{"label": _txt(t.get("label"), C.MAX_TIER_LABEL), "count": _int(t.get("count"), 0, C.MAX_RACE_WINNERS),
              "prize": _txt(t.get("prize"), C.MAX_TIER_PRIZE)}
             for t in (raw.get("tiers") if isinstance(raw.get("tiers"), list) else [])[:C.MAX_RACE_TIERS] if isinstance(t, dict)]
    winners, seen = [], set()
    for w in (raw.get("winners") if isinstance(raw.get("winners"), list) else [])[:C.MAX_RACE_WINNERS]:
        if not isinstance(w, dict):
            continue
        rank = _int(w.get("rank"), 0, 100000)
        if rank < 1 or rank in seen:
            continue
        seen.add(rank)
        winners.append({"rank": rank, "tier": _txt(w.get("tier"), C.MAX_TIER_LABEL), "prize": _txt(w.get("prize"), C.MAX_TIER_PRIZE),
                        "name": _txt(w.get("name")), "status": prize_label(w.get("status")) or C.PRIZE_STATUS[C.PRIZE_DEFAULT],
                        "note": str(w.get("note") or "").strip()[:C.MAX_RACE_NOTE]})
    ex = raw.get("excluded") if isinstance(raw.get("excluded"), dict) else {}
    reasons = [{"reason": _txt(r.get("reason"), 80), "n": _int(r.get("n"))}
               for r in (ex.get("reasons") if isinstance(ex.get("reasons"), list) else [])[:20] if isinstance(r, dict)]
    seed = str(raw.get("seed") or "").strip().lower()[:128]
    by = str(raw.get("by") or "").strip()
    return {"id": rid, "live": live, "brand": _txt(raw.get("brand"), 40), "app_session": _txt(raw.get("session"), 80),
            "keyword": _txt(raw.get("keyword"), C.MAX_KEYWORD), "status_raw": _txt(raw.get("status"), 60),
            "outcome": outcome_of(raw.get("status")), "reg_started_ts": ts["reg_started_at"],
            "race_started_ts": ts["race_started_at"], "finished_ts": ts["finished_at"], "race_date": vn_date(anchor),
            "sort_ts": anchor, "tiers": tiers, "winners": sorted(winners, key=lambda w: w["rank"]),
            "entrants": _int(raw.get("entrants")), "registered": _int(raw.get("registered")),
            "excluded_count": _int(ex.get("count")), "excluded_reasons": reasons,
            "seed": seed if all(c in "0123456789abcdef" for c in seed) else "", "audit_id": _txt(raw.get("audit_id"), 64),
            "algo": _txt(raw.get("algo"), 60), "by": by if by in C.RACE_BY else "app", "auto": bool(raw.get("auto"))}


def merge_winners(existing, incoming):
    """Gop trang thai trao giai. Ben nao doi sau cung thi thang:
    - app gui lai trang thai / ghi chu KHAC lan truoc app gui (app_status / app_note) -> lay cua app;
    - con lai giu cua ERP (nguoi dung da sua tren ERP)."""
    old = {w["rank"]: w for w in existing or []}
    out = []
    for w in incoming:
        o = old.get(w["rank"])
        if not o:
            out.append(dict(w, app_status=w["status"], app_note=w["note"]))
            continue
        status = w["status"] if w["status"] != (o.get("app_status") or "") else o["status"]
        note = w["note"] if w["note"] != (o.get("app_note") or "") else (o.get("note") or "")
        out.append(dict(w, status=status, note=note, app_status=w["status"], app_note=w["note"]))
    return out


def counts(winners):
    awarded = sum(1 for w in winners if w["status"] == C.PRIZE_STATUS["da_trao"])
    lost = sum(1 for w in winners if w["status"] == C.PRIZE_STATUS["khong_lien_lac"])
    return {"winners_n": len(winners), "awarded_n": awarded, "unreachable_n": lost}


def decode_png(b64):
    """'data:image/png;base64,...' hoac base64 tron -> (bytes, sha256). Sai -> AiLiveError."""
    s = str(b64 or "").strip()
    if s.startswith("data:"):
        head, _, s = s.partition(",")
        if "image/png" not in head:
            raise C.AiLiveError(C.RaceMsg.BAD_PNG)
    if len(s) > C.MAX_PNG_BYTES * 4 // 3 + 8:
        raise C.AiLiveError(C.RaceMsg.BAD_PNG)
    try:
        data = base64.b64decode(s, validate=False)
    except (binascii.Error, ValueError):
        raise C.AiLiveError(C.RaceMsg.BAD_PNG)
    if len(data) < 64 or len(data) > C.MAX_PNG_BYTES or not data.startswith(_PNG_SIG):
        raise C.AiLiveError(C.RaceMsg.BAD_PNG)
    return data, hashlib.sha256(data).hexdigest()


def start_args(raw):
    """Tham so tuy chon cua lenh start_race (ghi de 1 lan). Chi giu khoa biet truoc, ep khoang."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    kw = " ".join(str(raw.get("keyword") or "").split())
    if kw:
        if len(kw) > C.MAX_KEYWORD:
            raise C.AiLiveError(C.RaceMsg.BAD_ARG % "từ khoá tối đa %d ký tự" % C.MAX_KEYWORD)
        out["keyword"] = kw
    for k, (lo, hi) in C.RACE_ARG_RANGES.items():
        if raw.get(k) not in (None, ""):
            try:
                v = int(raw[k])
            except (TypeError, ValueError):
                raise C.AiLiveError(C.RaceMsg.BAD_ARG % k)
            if not lo <= v <= hi:
                raise C.AiLiveError(C.RaceMsg.BAD_ARG % ("%s phải từ %d đến %d" % (k, lo, hi)))
            out[k] = v
    for k, allowed in (("announceOrder", C.RACE_ANNOUNCE), ("excludeWinners", C.RACE_EXCLUDE)):
        if raw.get(k):
            if raw[k] not in allowed:
                raise C.AiLiveError(C.RaceMsg.BAD_ARG % k)
            out[k] = raw[k]
    tiers = raw.get("tiers")
    if tiers:
        if not isinstance(tiers, list) or len(tiers) > C.MAX_RACE_TIERS:
            raise C.AiLiveError(C.RaceMsg.BAD_ARG % ("tối đa %d giải" % C.MAX_RACE_TIERS))
        clean = []
        for t in tiers:
            label = _txt((t or {}).get("label"), C.MAX_TIER_LABEL) if isinstance(t, dict) else ""
            if not label:
                raise C.AiLiveError(C.RaceMsg.BAD_ARG % "giải chưa có tên")
            clean.append({"label": label, "count": _int(t.get("count"), 0, C.MAX_RACE_WINNERS),
                          "prize": _txt(t.get("prize"), C.MAX_TIER_PRIZE)})
        if not any(t["count"] for t in clean):
            raise C.AiLiveError(C.RaceMsg.BAD_ARG % "cần ít nhất 1 giải có số lượng > 0")
        out["tiers"] = clean
    return out


CSV_HEAD = ("Ngày", "Giờ về đích", "Brand", "Phiên live", "Mã cuộc đua", "Kết quả", "Từ khoá", "Người tham gia",
            "Hạng", "Giải", "Phần quà", "Tên người thắng", "Trạng thái trao giải", "Ghi chú", "Mã kiểm tra")


def to_csv(races):
    """1 dong / nguoi thang (cuoc dua khong co nguoi thang -> 1 dong trong). BOM de Excel doc dung tieng Viet."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\r\n")
    w.writerow(CSV_HEAD)
    for r in races:
        t = r.get("finished_ts") or r.get("race_started_ts") or r.get("reg_started_ts")
        base = [r["race_date"], datetime.fromtimestamp(t, R._VN).strftime("%H:%M:%S") if t else "", r.get("brand") or "",
                r["live"], r["id"], C.RACE_OUTCOMES.get(r.get("outcome"), r.get("outcome") or ""), r.get("keyword") or "",
                r.get("entrants") or 0]
        tail = (r.get("seed") or "")[:16]
        for x in r.get("winners") or [{}]:
            w.writerow([_cell(v) for v in base + [x.get("rank", ""), x.get("tier", ""), x.get("prize", ""), x.get("name", ""),
                                                  x.get("status", ""), x.get("note", ""), tail]])
    return "﻿" + buf.getvalue()


def _cell(v):
    """Chong chen cong thuc khi mo bang Excel (ten khach co the bat dau bang = + - @)."""
    s = str(v if v is not None else "")
    return "'" + s if s[:1] in ("=", "+", "-", "@") else s
