# Copyright (c) 2026, eCentric and contributors
"""Bo live: chuan hoa du lieu form, dem voice, buoc gui may chay video, de xuat bo motion + uoc tinh chi phi.
Thuan Python (khong DB, khong frappe) - test duoc doc lap."""
import os
import re

from ecentric_workspace.ai_tools.features.ai_live import constants as C


def _audio_list(raw, where):
    out = []
    for a in raw or []:
        if not isinstance(a, dict) or not a.get("file"):
            continue
        f = str(a["file"])
        if os.path.splitext(f)[1].lower() not in C.AUDIO_EXT:
            raise C.AiLiveError("%s: file voice phải là mp3/wav/m4a (%s)" % (where, a.get("name") or f))
        try:
            dur = round(float(a.get("dur") or 0), 2)
        except (TypeError, ValueError):
            dur = 0
        out.append({"file": f, "name": str(a.get("name") or os.path.basename(f))[:140], "dur": max(0, dur),
                    "version": max(1, min(int(a.get("version") or 1), 99))})
    if len(out) > C.MAX_AUDIO_PER_GROUP:
        raise C.AiLiveError("%s: tối đa %d voice mỗi nhóm" % (where, C.MAX_AUDIO_PER_GROUP))
    return out


def normalize_products(rows):
    rows = [r for r in (rows or []) if isinstance(r, dict) and (r.get("id") or r.get("name"))]
    if len(rows) > C.MAX_PRODUCTS:
        raise C.AiLiveError("Tối đa %d sản phẩm mỗi Bộ live." % C.MAX_PRODUCTS)
    out, seen = [], set()
    for i, r in enumerate(rows, 1):
        pid = str(r.get("id") or "sp%02d" % i).strip()
        if not C.PRODUCT_ID_RE.match(pid):
            raise C.AiLiveError(C.KitMsg.BAD_PRODUCT % (i, "mã SP chỉ gồm chữ, số, - _"))
        if pid.lower() in seen:
            raise C.AiLiveError(C.KitMsg.BAD_PRODUCT % (i, "trùng mã SP %s" % pid))
        seen.add(pid.lower())
        plat = r.get("platformIds") or {}
        ids = {k: str(plat.get(k) or "").strip() for k in ("shopee", "tiktok")}
        for k, v in ids.items():
            if not C.PLATFORM_ID_RE.match(v):
                raise C.AiLiveError(C.KitMsg.BAD_PRODUCT % (i, "mã SP %s không hợp lệ" % k))
        p = {"id": pid, "name": str(r.get("name") or pid).strip()[:140], "platformIds": ids,
             "putdown": bool(r.get("putdown")), "pickup": bool(r.get("pickup"))}
        for g in C.PRODUCT_AUDIO_GROUPS:
            p[g] = _audio_list(r.get(g), "SP %s" % pid)
        out.append(p)
    return out


def normalize_faq(rows):
    rows = [r for r in (rows or []) if isinstance(r, dict) and (r.get("topic") or r.get("videos"))]
    if len(rows) > C.MAX_FAQ_TOPICS:
        raise C.AiLiveError("Tối đa %d chủ đề FAQ." % C.MAX_FAQ_TOPICS)
    out = []
    for i, r in enumerate(rows, 1):
        topic = str(r.get("topic") or "").strip()[:80]
        if not topic:
            raise C.AiLiveError(C.KitMsg.BAD_FAQ % (i, "chưa nhập tên chủ đề"))
        out.append({"topic": topic, "scope": str(r.get("scope") or "brand")[:40],
                    "intentId": int(r["intentId"]) if str(r.get("intentId") or "").isdigit() else None,
                    "videos": _audio_list(r.get("videos"), "FAQ %s" % topic)})
    return out


def normalize_generic(d):
    d = d if isinstance(d, dict) else {}
    return {g: _audio_list(d.get(g), "Câu chung %s" % g) for g in C.GENERIC_GROUPS}


def audio_entries(products, faq, generic):
    """Moi voice cua bo live: [(nhan, entry)] theo thu tu co dinh (dung dat ten file gui may chay video)."""
    out = []
    for p in products:
        for g in C.PRODUCT_AUDIO_GROUPS:
            for k, a in enumerate(p.get(g) or [], 1):
                out.append(("%s_%s_%d" % (p["id"], "free" if g == "main_free" else "hold", k), a))
    for i, f in enumerate(faq, 1):
        for k, a in enumerate(f.get("videos") or [], 1):
            out.append(("faq%02d_%d" % (i, k), a))
    for g in C.GENERIC_GROUPS:
        for k, a in enumerate((generic or {}).get(g) or [], 1):
            out.append(("%s_%d" % (g, k), a))
    return out


def summary(products, faq, generic):
    ents = audio_entries(products, faq, generic)
    secs = round(sum(a.get("dur") or 0 for _, a in ents), 1)
    return {"products": len(products), "faq_topics": len(faq), "videos": len(ents), "voice_s": secs,
            "lipsync_usd_fal": round(secs * C.LS_USD_PER_S, 2)}


def slug(s, n=40):
    return re.sub(r"[^A-Za-z0-9]+", "_", str(s or "")).strip("_")[:n] or "x"


def build_step(kit, products, faq, generic, rels, background_rel=None):
    """Buoc 'build_kit' gui may chay video. rels: {file_url: duong dan tren may chay video}."""
    def a2(a):
        return {"audio": rels[a["file"]], "dur": a.get("dur") or None, "version": a.get("version") or 1, "name": a.get("name")}

    bg_kind = C.BG_EXT.get(os.path.splitext(kit.get("background") or "")[1].lower())
    return {"op": "build_kit", "kit": kit["name"], "brand": kit["brand"], "brand_name": kit.get("brand_name") or kit["brand"],
            "title": kit.get("title") or "", "host": kit["host_key"],
            "voice": {"id": kit.get("voice_id") or "", "provider": kit.get("voice_provider") or ""},
            "mode": kit.get("mode") or "full", "break_sec": int(kit.get("break_sec") or C.DEFAULT_BREAK_SEC),
            "background": background_rel, "background_kind": bg_kind if background_rel else None,
            "bake_bg": bool(kit.get("bake_bg")) and bg_kind == "image",
            "products": [dict({k: p[k] for k in ("id", "name", "platformIds", "putdown", "pickup")},
                              **{g: [a2(a) for a in p.get(g) or []] for g in C.PRODUCT_AUDIO_GROUPS}) for p in products],
            "faq": [{"topic": f["topic"], "scope": f["scope"], "intentId": f["intentId"], "videos": [a2(a) for a in f["videos"]]} for f in faq],
            "generic": {g: [a2(a) for a in (generic or {}).get(g) or []] for g in C.GENERIC_GROUPS},
            "out": "ecv6/kits/%s/%s" % (slug(kit["brand"]), slug(kit["name"]))}


def motion_plan(raw=None):
    """[{dur, n}] tu form; None -> de xuat 20 clip (10x10s, 5x8s, 3x6s, 2x4s)."""
    if raw is None:
        return [{"dur": d, "n": n} for d, n in C.MOTION_PROPOSAL]
    plan = []
    for r in raw if isinstance(raw, list) else []:
        try:
            d, n = int(r.get("dur")), int(r.get("n") or 0)
        except (TypeError, ValueError, AttributeError):
            raise C.AiLiveError(C.KitMsg.BAD_PLAN)
        if d not in C.MOTION_DURS or not 0 <= n <= 20:
            raise C.AiLiveError(C.KitMsg.BAD_PLAN)
        if n:
            plan.append({"dur": d, "n": n})
    total = sum(r["n"] for r in plan)
    if not 1 <= total <= C.MAX_MOTION_CLIPS or len({r["dur"] for r in plan}) != len(plan):
        raise C.AiLiveError(C.KitMsg.BAD_PLAN)
    return plan


def motion_cost(plan):
    secs = sum(r["dur"] * r["n"] for r in plan)
    credits = round(secs * C.PX_CREDIT_PER_S * C.QC_FACTOR)
    return {"clips": sum(r["n"] for r in plan), "seconds": secs, "credits": credits, "vnd": credits * C.VND_PER_PX_CREDIT,
            "formula": "~%d credit/giây × %d giây × %s (gen lại do QC) × %dđ/credit" % (
                C.PX_CREDIT_PER_S, secs, str(C.QC_FACTOR).replace(".", ","), C.VND_PER_PX_CREDIT)}


def image_cost(model, n):
    m = next((x for x in C.IMAGE_MODELS if x[0] == model), None)
    if not m:
        raise C.AiLiveError(C.KitMsg.BAD_MODEL)
    if m[2] is None:
        return {"credits": None, "vnd": None}
    return {"credits": m[2] * n, "vnd": m[2] * n * C.VND_PER_PX_CREDIT}


def tasks_summary(tasks):
    """Dem trang thai task cua may chay video cho 1 lo -> (status Bo live, so lieu)."""
    n = len(tasks)
    cnt = {}
    for t in tasks:
        cnt[t.get("state") or "queued"] = cnt.get(t.get("state") or "queued", 0) + 1
    done = cnt.get("done", 0)
    bad = cnt.get("failed", 0) + cnt.get("blocked", 0) + cnt.get("cancelled", 0)
    errs = [str(t.get("error") or "")[:160] for t in tasks if t.get("state") in ("failed", "blocked") and t.get("error")][:5]
    if not n:
        st = C.KitStatus.BUILDING
    elif done + bad < n:
        st = C.KitStatus.BUILDING
    else:
        st = C.KitStatus.ERROR if bad else C.KitStatus.DONE
    return st, {"total": n, "done": done, "failed": bad, "running": n - done - bad, "errors": errs}
