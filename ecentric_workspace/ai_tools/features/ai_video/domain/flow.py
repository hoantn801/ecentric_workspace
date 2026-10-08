# Copyright (c) 2026, eCentric and contributors
"""AI Video hang loat - LUONG THUAN (khong frappe, khong mang). Test o tests/test_ai_video_flow.py.

Mot SKU di qua cac buoc (stage):
  new -> holds (worker tao 2 anh cam) -> pick (NGUOI chon anh / gen lai)
      -> master (n8n refine anh master, dung) -> wait_anchor (cho khung neo cua du an)
      -> motion (3 clip ha SP trai/phai/duoi; lay len = dao nguoc) -> [qc_motion]
      -> hold_a (clip cam 10s, dau = cuoi = master) -> [qc_hold_a]
      -> hold_b (clip cam thu 2) -> ready -> (mixing -> done khi chay dem)
[qc_*] la chot chan: bat thi dung cho nguoi duyet; chay dem thi bo qua.

Du an (mot host): khung neo anchor.png (2 tay tren ban, khong SP) + N clip noi
(talk, dau = cuoi = anchor). Moi clip deu bat dau/ket thuc o anchor hoac master nen
tron thu tu nao cung khong giat.

decide_item() chi DOC trang thai worker va tra ve: cac truong can ghi + cac buoc
worker can enqueue. Goi lai nhieu lan khong sinh viec trung (idempotent) vi moi buoc
chi enqueue khi stage doi."""
import re

STAGE_LABEL = {
    "new": "Mới", "holds": "Đang tạo ảnh cầm", "pick": "Chờ chọn ảnh",
    "master": "Đang làm ảnh master", "wait_anchor": "Chờ khung neo",
    "motion": "Đang tạo clip lấy/hạ SP", "qc_motion": "Chờ duyệt clip lấy/hạ",
    "hold_a": "Đang tạo clip cầm A", "qc_hold_a": "Chờ duyệt clip cầm A",
    "hold_b": "Đang tạo clip cầm B", "ready": "Đủ clip - sẵn sàng trộn",
    "mixing": "Đang trộn video", "done": "Xong", "fix": "Đang gen lại clip",
}
DIRS = ("left", "right", "below")
QC_STAGES = ("pick", "qc_motion", "qc_hold_a")
RUNNING_STAGES = ("holds", "master", "motion", "hold_a", "hold_b", "mixing", "fix")
#: clip SKU nguoi dung bo tick / gen lai rieng (08/10/2026); bo Ha trai = bo ca Lay trai (ban chay nguoc)
UNIT_KEYS = ("putdown_left", "putdown_right", "putdown_below", "hold_01", "hold_02")


def slug(s, n=40):
    s = re.sub(r"[^A-Za-z0-9]+", "_", str(s or "")).strip("_").upper()
    return s[:n] or "X"


def job_id(brand, sku, project, attempt):
    return "%s_%s_%s_R%d" % (slug(brand, 16), slug(sku, 32), slug(project, 8), int(attempt or 1))


def tasks_state(ids, tasks):
    """ids -> 'none' | 'running' | 'done' | 'failed' (+ loi dau tien)."""
    ids = list(ids or [])
    if not ids:
        return "none", None
    sts = [tasks.get(i) for i in ids]
    for t in sts:
        if t and t.get("state") in ("failed", "blocked", "cancelled"):
            return "failed", (t.get("error") or t.get("state"))
    if any(t is None for t in sts):
        return "running", None          # worker chua bao ve (vua enqueue)
    if all(t.get("state") == "done" for t in sts):
        return "done", None
    return "running", None


def weight_note(g):
    """Khoi luong (gram) -> 1 cau tieng Anh cho AI: nang nhe khac nhau thi cach cam khac (07/10/2026).
    Worker cung doc cau nay trong product_notes de them vao prompt clip cam/ha."""
    try:
        g = float(g or 0)
    except (TypeError, ValueError):
        return ""
    if g <= 0:
        return ""
    w = ("%d g" % round(g)) if g < 1000 else ("%.1f kg" % (g / 1000)).replace(".0 kg", " kg")
    if g < 150:
        feel = "very light, held easily between the fingers"
    elif g < 500:
        feel = "light, held comfortably in one hand"
    elif g < 1200:
        feel = "noticeably heavy for its size, held with a firm full-hand grip, it never floats or wobbles"
    elif g < 3000:
        feel = "heavy, supported from below with the hand under the base, wrist slightly braced"
    else:
        feel = "very heavy, both hands under it, held close to the body"
    return "WEIGHT: about %s (%s)." % (w, feel)


def hold_fields(item, brand):
    """Truong form n8n v5.9 cho buoc tao anh cam."""
    def num(v):
        return ("%g" % v) if v not in (None, "", 0) else ""
    return {
        "sku": item.get("sku") or "", "product_name": item.get("product_name") or "",
        "brand_name": brand or "", "product_type": item.get("product_type") or "",
        "product_width_cm": num(item.get("width_cm")), "product_height_cm": num(item.get("height_cm")),
        "product_depth_cm": num(item.get("depth_cm")), "size_adjust_pct": num(item.get("size_pct")),
        "pack_count": item.get("pack_count") or "",
        "product_notes": " ".join(x for x in (weight_note(item.get("weight_g")), item.get("notes") or "") if x)[:400],
        "product_category": item.get("product_category") or "", "lipsync": "0",
    }


#: co audio: video = VOICE_PAD_S giay dau (chua noi) + audio + VOICE_PAD_S giay cuoi (07/10/2026)
VOICE_PAD_S = 2


def mix_step(item, project, st, voice=None):
    """Co audio thi worker tu do do dai audio va cong 2s dau/cuoi (bo qua duration_s),
    tru khi nguoi dung nhap do dai co dinh luc tron (keep_duration)."""
    return {"op": "mix", "mode": project.get("mix_mode") or "mix", "n": int(project.get("mix_variants") or 5),
            "voice_pad_s": VOICE_PAD_S, "keep_duration": bool(item.get("keep_duration")),
            "duration_s": float(item.get("audio_seconds") or project.get("audio_seconds") or 72),
            "brand": project.get("brand"), "batch_id": item.get("out_dir") or project.get("out_dir") or "video",
            "sku": item.get("sku"), "unit_off": unit_off(st),
            "host": project.get("host_key"), "jobs": [st.get("job")], "voice": voice,
            "talk_off": talk_off(project)}


def unit_off(st):
    """Clip SKU bo tick -> 'job:unit' cho worker (08/10/2026)."""
    job = (st or {}).get("job")
    return sorted("%s:%s" % (job, u) for u in (st or {}).get("unit_off") or []) if job else []


def talk_off(project):
    """Clip noi nguoi dung bo tick (khong dung khi tron) - luu o state du an (08/10/2026)."""
    return sorted((project.get("state") or {}).get("talk_off") or [])


def decide_item(item, project, W):
    """item/project: dict (truong doctype + 'state' da parse). W: trang thai worker:
    {"tasks": {id: task}, "jobs": {job_id: job_state}, "anchor_ready": bool}.
    -> {"set": {...}, "steps": [(key, step_dict)], "need_anchor_from": job_id|None}"""
    st = item.get("state") or {}
    stage = item.get("stage") or "new"
    night = bool(project.get("night_mode"))
    out = {"set": {}, "steps": [], "need_anchor_from": None}
    tasks = W.get("tasks") or {}
    job = st.get("job")
    js = (W.get("jobs") or {}).get(job) or {}

    def go(new_stage, state="running", **extra):
        out["set"].update({"stage": new_stage, "stage_state": state, "error": ""})
        out["set"].update(extra)

    def fail(msg):
        out["set"].update({"stage_state": "error", "error": (msg or "Lỗi không rõ")[:500]})

    def enqueue(key, step):
        out["steps"].append((key, step))

    def units_step(**kw):
        s = {"op": "units", "host": project.get("host_key"), "job_id": job}
        s.update(kw)
        return s

    ts, err = tasks_state((st.get("tasks") or {}).get(stage), tasks)
    if stage in RUNNING_STAGES and ts == "failed":
        fail(err)
        return out
    if stage == "holds" and ts == "done":
        cands = [c for c in (js.get("candidates") or []) if c.get("file")]
        if len(cands) >= 1:
            go("pick", "waiting")
        else:
            fail("Worker báo xong nhưng không thấy ảnh cầm nào")
    elif stage == "master" and ts == "done":
        if not js.get("master"):
            fail("Không thấy ảnh master sau khi refine")
        elif W.get("anchor_ready"):
            go("motion")
            enqueue("motion", units_step(dirs=list(DIRS), holds=0))
        else:
            go("wait_anchor", "waiting")
            out["need_anchor_from"] = job
    elif stage == "wait_anchor":
        if W.get("anchor_ready"):
            go("motion")
            enqueue("motion", units_step(dirs=list(DIRS), holds=0))
        else:
            out["need_anchor_from"] = job
    elif stage == "motion" and ts == "done":
        if (project.get("gate_motion") and not night) or st.get("force_gate"):
            go("qc_motion", "waiting")
        else:
            go("hold_a")
            enqueue("hold_a", units_step(dirs=[], holds=1, hold_start=1))
    elif stage == "hold_a" and ts == "done":
        if (project.get("gate_hold_a") and not night) or st.get("force_gate"):
            go("qc_hold_a", "waiting")
        else:
            go("hold_b")
            enqueue("hold_b", units_step(dirs=[], holds=1, hold_start=2))
    elif stage == "hold_b" and ts == "done":
        if night:
            go("mixing")
            enqueue("mixing", mix_step(item, project, st))
        else:
            go("ready", "waiting")
    elif stage == "mixing" and ts == "done":
        go("done", "done")
    elif stage == "fix" and ts == "done":
        go("ready", "waiting")                  # gen lai 1 clip xong -> ve lai du clip
    return out


def approve_item(item, project):
    """Nguoi duyet o mot chot chan -> buoc tiep theo."""
    st = item.get("state") or {}
    stage = item.get("stage")
    step = {"op": "units", "host": project.get("host_key"), "job_id": st.get("job")}
    if stage == "qc_motion":
        step.update(dirs=[], holds=1, hold_start=1)
        return "hold_a", step
    if stage == "qc_hold_a":
        step.update(dirs=[], holds=1, hold_start=2)
        return "hold_b", step
    raise ValueError("SKU không ở bước chờ duyệt")


def regen_units(stage, dirs=None, unit=None):
    """Clip nao can xoa de gen lai o mot chot chan -> (ten unit, buoc chay lai).
    unit: gen lai DUNG 1 clip khi SKU da du clip (08/10/2026) -> buoc 'fix', xong ve lai ready."""
    if unit:
        if unit not in UNIT_KEYS:
            raise ValueError("Clip không hợp lệ")
        if stage not in ("ready", "done"):
            raise ValueError("Chỉ gen lại từng clip khi SKU đã đủ clip")
        if unit.startswith("putdown_"):
            return [unit], "fix", {"dirs": [unit[8:]], "holds": 0, "keep_dirs": True}
        return [unit], "fix", {"dirs": [], "holds": 1, "hold_start": int(unit[-2:])}
    if stage == "qc_motion":
        d = [x for x in (dirs or DIRS) if x in DIRS] or list(DIRS)
        return ["putdown_" + x for x in d], "motion", {"dirs": d, "holds": 0}
    if stage == "qc_hold_a":
        return ["hold_01"], "hold_a", {"dirs": [], "holds": 1, "hold_start": 1}
    if stage == "ready":
        return ["hold_02"], "hold_b", {"dirs": [], "holds": 1, "hold_start": 2}
    raise ValueError("Bước này không gen lại clip được")


def project_summary(items):
    """Dem SKU theo nhom de ve the/chip."""
    c = {"total": 0, "pick": 0, "qc": 0, "running": 0, "ready": 0, "done": 0, "error": 0}
    for it in items:
        c["total"] += 1
        stg, sst = it.get("stage") or "new", it.get("stage_state") or ""
        if sst == "error":
            c["error"] += 1
        elif stg == "pick":
            c["pick"] += 1
        elif stg in ("qc_motion", "qc_hold_a"):
            c["qc"] += 1
        elif stg == "ready":
            c["ready"] += 1
        elif stg == "done":
            c["done"] += 1
        elif stg in RUNNING_STAGES or stg == "wait_anchor":
            c["running"] += 1
    return c


def cost_view(costs, items):
    """Chi phi Kie theo $ (worker tinh tu credit da tieu; uoc tinh voi viec cu chua ghi credit).
    SKU: cong moi job cua SKU do (ke ca cac lan lam lai). Clip noi/khung neo dung chung -> chia deu cho cac SKU.
    /video = (chi phi SKU + phan clip noi) / so video da tron cua SKU. Gan ket qua vao tung item (cost_usd, ...)."""
    costs = costs or {}
    jobs = costs.get("job") or {}
    host_usd = round(sum((v or {}).get("usd") or 0 for v in (costs.get("host") or {}).values()), 2)
    est = sum((v or {}).get("est_credits") or 0 for v in list(jobs.values()) + list((costs.get("host") or {}).values()))
    videos = costs.get("videos") or {}
    n = len(items) or 1
    total = host_usd
    upc = float(costs.get("usd_per_credit") or 0.005)
    kinds_all = {}
    for it in items:
        sku = str(it.get("sku") or "")
        jid = str(it.get("job_id") or "")
        pre = jid.rsplit("_", 1)[0] + "_" if "_" in jid else ""
        if pre:   # 08/10: moi lan lam cua dung SKU nay (R1, R2, W4...), ke ca viec chay ngoai ERP; SKU co dau van khop
            mine = [v or {} for k, v in jobs.items() if k == jid or (k.startswith(pre) and re.match(r"^[A-Z]\d+$", k[len(pre):]))]
        else:
            mine = [v or {} for k, v in jobs.items() if sku and "_%s_" % sku in "_%s_" % k]
        usd = round(sum(v.get("usd") or 0 for v in mine), 2)
        it["cost_kinds"] = _kinds(mine, upc, kinds_all)
        share = round(host_usd / n, 2)
        nv = int(videos.get(sku) or 0)
        it["cost_usd"] = usd
        it["cost_share_usd"] = share
        it["videos"] = nv
        it["cost_per_video_usd"] = round((usd + share) / nv, 2) if nv else None
        total += usd
    host_kinds = _kinds(list((costs.get("host") or {}).values()), upc, None)
    return {"total_usd": round(total, 2), "host_usd": host_usd, "estimated": bool(est),
            "usd_per_credit": costs.get("usd_per_credit"), "kinds": {k: round(v, 2) for k, v in kinds_all.items()},
            "host_kinds": host_kinds}


def _item_bags(bags, it):
    """Cac job cua dung SKU nay (R1, R2, W4...), giong cost_view."""
    sku = str(it.get("sku") or "")
    jid = str(it.get("job_id") or "")
    pre = jid.rsplit("_", 1)[0] + "_" if "_" in jid else ""
    if pre:
        return [v or {} for k, v in bags.items() if k == jid or (k.startswith(pre) and re.match(r"^[A-Z]\d+$", k[len(pre):]))]
    return [v or {} for k, v in bags.items() if sku and "_%s_" % sku in "_%s_" % k]


def _union(ivs):
    """Gop cac doan [bat dau, xong] (ms) -> (so giay may chay, bat dau som nhat, xong muon nhat)."""
    a = sorted([float(x[0]), float(x[1])] for x in ivs if x and len(x) == 2 and x[1] > x[0])
    tot, cur = 0.0, None
    for s, e in a:
        if cur and s <= cur[1]:
            cur[1] = max(cur[1], e)
        else:
            if cur:
                tot += cur[1] - cur[0]
            cur = [s, e]
    if cur:
        tot += cur[1] - cur[0]
    return (int(round(tot / 1000)), a[0][0] if a else None, max((e for _, e in a), default=None))


#: loai viec worker -> cot thoi gian (09/10/2026)
TIME_KIND = {"hold_images": "holds", "master": "master", "putdown": "put", "hold": "clip", "mix": "mix", "anchor": "anchor", "talk": "talk"}


def time_view(times, items):
    """Thoi gian may chay (giay) theo buoc cho tung SKU + ca du an. 'secs' = tong thoi gian co it nhat 1 viec cua SKU
    dang chay (viec song song chi tinh 1 lan, khong tinh luc cho duyet); 'wall' = tu luc bat dau den luc xong (ke ca cho)."""
    times = times or {}
    jobs, mixes, hosts = times.get("job") or {}, times.get("mix") or {}, times.get("host") or {}
    all_iv, kinds_all = [], {}
    for it in items:
        bags = _item_bags(jobs, it) + ([mixes[str(it.get("sku"))]] if str(it.get("sku")) in mixes else [])
        iv, kinds = [], {}
        for b in bags:
            iv += b.get("iv") or []
            for k, v in (b.get("kinds") or {}).items():
                col = TIME_KIND.get(k, "other")
                kinds[col] = kinds.get(col, 0) + int(v or 0)
        secs, t0, t1 = _union(iv)
        mx = mixes.get(str(it.get("sku"))) or {}
        it["time_kinds"] = kinds
        it["time_secs"] = secs
        it["time_wall"] = int(round((t1 - t0) / 1000)) if t0 else 0
        it["time_per_video"] = int(round((mx.get("secs") or 0) / mx["videos"])) if mx.get("videos") else None
        all_iv += iv
        for k, v in kinds.items():
            kinds_all[k] = kinds_all.get(k, 0) + v
    hk, hiv = {}, []
    for b in hosts.values():
        hiv += (b or {}).get("iv") or []
        for k, v in ((b or {}).get("kinds") or {}).items():
            col = TIME_KIND.get(k, "other")
            hk[col] = hk.get(col, 0) + int(v or 0)
    secs, t0, t1 = _union(all_iv + hiv)
    return {"secs": secs, "wall": int(round((t1 - t0) / 1000)) if t0 else 0, "kinds": kinds_all,
            "host_kinds": hk, "host_secs": _union(hiv)[0]}


#: loai viec worker -> cot chi phi tren trang (07/10/2026)
COST_KIND = {"hold_images": "holds", "master": "master", "putdown": "put", "hold": "clip", "anchor": "anchor", "talk": "talk"}


def _kinds(bags, upc, acc):
    """Cong credit theo loai viec cua cac job/host -> $. 'regen' = phan da tieu cho cac lan gen bi QC loai."""
    out = {}
    for b in bags:
        for k, c in (b.get("kinds") or {}).items():
            col = COST_KIND.get(k, "other")
            out[col] = out.get(col, 0) + (c or 0) * upc
        out["regen"] = out.get("regen", 0) + (b.get("regen") or 0) * upc
    out = {k: round(v, 2) for k, v in out.items() if v}
    if acc is not None:
        for k, v in out.items():
            acc[k] = acc.get(k, 0) + v
    return out


def parse_bbox(v):
    """Khung SP nguoi dung ve tren anh host: "x,y,w,h" (ti le 0..1). Sai -> None. "" -> "" (xoa khung)."""
    if v in (None, ""):
        return ""
    try:
        x, y, w, h = [float(p) for p in str(v).replace(";", ",").split(",")]
    except (TypeError, ValueError):
        return None
    if not (0 <= x <= 1 and 0 <= y <= 1 and 0.02 <= w <= 1 and 0.01 <= h <= 1 and x + w <= 1.001 and y + h <= 1.001):
        return None
    return "%.4f,%.4f,%.4f,%.4f" % (x, y, w, h)


# ------------------------------------------------------------------ prompt theo nhom SP ---
#: 12 nhom kieu cam (khop CATS tren trang + thu vien kieu cam trong n8n).
CATEGORIES = ("milk_can", "milk_carton_pack", "oil_bottle", "personal_care_bottle", "cream_tube", "diaper_pack",
              "battery_blister", "small_box", "biscuit_box_large", "soft_pouch", "hair_dryer", "table_appliance")
GROUP_STATUS = ("ok", "try", "none")   # da kiem chung / dang thu / dung mau chung
GROUP_FIELDS = {"status": 20, "hold": 300, "clip": 500, "put": 500, "size_cm": 10, "clip_base": 20}


def clean_group(d):
    """Du lieu quan tri sua cho 1 nhom -> dict sach. Sai -> ValueError (thong bao tieng Viet)."""
    out = {}
    for k, n in GROUP_FIELDS.items():
        if k in (d or {}) and d[k] is not None:
            out[k] = re.sub(r"[`$\\]", "", str(d[k])).strip()[:n]
    if out.get("status") and out["status"] not in GROUP_STATUS:
        raise ValueError("Trạng thái nhóm không hợp lệ.")
    if out.get("clip_base") and out["clip_base"] not in ("two_hand", "one_hand"):
        raise ValueError("Mẫu clip cầm không hợp lệ.")
    if out.get("size_cm") and not re.match(r"^\d{1,3}(\.\d)?$", out["size_cm"]):
        raise ValueError("Cỡ gợi ý phải là số cm (vd 17 hoặc 12.5).")
    return out


def needs_trial_gate(category, groups, other_stages):
    """SKU thuoc nhom 'Dang thu' va chua SKU nao cung nhom ra du clip -> bat chot duyet (do ton tien ca lo)."""
    g = (groups or {}).get(category or "") or {}
    return g.get("status") == "try" and not any(x in ("ready", "done") for x in other_stages or [])
