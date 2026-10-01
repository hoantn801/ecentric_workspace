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
    "mixing": "Đang trộn video", "done": "Xong",
}
DIRS = ("left", "right", "below")
QC_STAGES = ("pick", "qc_motion", "qc_hold_a")
RUNNING_STAGES = ("holds", "master", "motion", "hold_a", "hold_b", "mixing")


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


def hold_fields(item, brand):
    """Truong form n8n v5.9 cho buoc tao anh cam."""
    def num(v):
        return ("%g" % v) if v not in (None, "", 0) else ""
    return {
        "sku": item.get("sku") or "", "product_name": item.get("product_name") or "",
        "brand_name": brand or "", "product_type": item.get("product_type") or "",
        "product_width_cm": num(item.get("width_cm")), "product_height_cm": num(item.get("height_cm")),
        "product_depth_cm": num(item.get("depth_cm")), "size_adjust_pct": num(item.get("size_pct")),
        "pack_count": item.get("pack_count") or "", "product_notes": item.get("notes") or "",
        "product_category": item.get("product_category") or "", "lipsync": "0",
    }


def mix_step(item, project, st, voice=None):
    return {"op": "mix", "mode": project.get("mix_mode") or "mix", "n": int(project.get("mix_variants") or 5),
            "duration_s": float(item.get("audio_seconds") or project.get("audio_seconds") or 72),
            "brand": project.get("brand"), "batch_id": item.get("batch") or "lo", "sku": item.get("sku"),
            "host": project.get("host_key"), "jobs": [st.get("job")], "voice": voice}


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
        if project.get("gate_motion") and not night:
            go("qc_motion", "waiting")
        else:
            go("hold_a")
            enqueue("hold_a", units_step(dirs=[], holds=1, hold_start=1))
    elif stage == "hold_a" and ts == "done":
        if project.get("gate_hold_a") and not night:
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


def regen_units(stage, dirs=None):
    """Clip nao can xoa de gen lai o mot chot chan -> (ten unit, buoc chay lai)."""
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
