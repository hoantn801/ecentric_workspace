# Copyright (c) 2026, eCentric and contributors
"""Tron hang loat theo voice (FAQ / tra loi cau hoi khi live) - 12/10/2026.

Moi file voice -> 1 video "chi noi" cua host du an: worker chia clip noi cho tung voice (khong lap trong 1 video,
chia deu giua cac video, clip it dung truoc), KHONG tua, giong bat dau dung lead_s (0.5s) va video ket thuc o khung neo.
Xong het thi worker do ti le trung khung (noi bo / cheo) cho ca dot -> hien canh tung video de chon.

Bang tinh (trang): tu % trung muc tieu + do dai cac voice -> so giay canh rieng can co, so clip noi phai gen, chi phi.
Kho clip noi (do dai, giat, ti le dat QC, credit/luot) do worker tra qua faq_stock."""
import hashlib
import json
import re

import frappe

from ecentric_workspace.ai_tools.features.ai_video.application import service as svc
from ecentric_workspace.ai_tools.features.ai_video.domain import flow
from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client as wc

AUDIO_EXT = (".mp3", ".wav", ".m4a")
MAX_VOICES = 100
#: Goi PlenX Ultimate 399.000d / 5.000 credit (12/10/2026) - chi de uoc tinh tren trang.
VND_PER_PX_CREDIT = 80
_HOST = re.compile(r"^[A-Za-z0-9_.-]{1,96}$")


def _inbox(project, batch):
    return "inbox/%s/faq/%s/" % (flow.slug(project, 20), flow.slug(batch, 40))


def _meta(doc):
    m = svc._j(doc.items, None)
    return m if isinstance(m, dict) and m.get("faq") else None


# ------------------------------------------------------------------ host / kho clip ---

def hosts_list():
    hosts = wc.call("hosts_list").get("hosts") or []
    for h in hosts:
        h["thumb"] = svc._thumb(h["anchor"], 240) if h.get("anchor") else None
    return {"hosts": hosts, "can_edit": svc.is_admin()}


def set_host(project, host):
    """Quan tri: du an dung 1 host co san tren may chay video (vd host nen xanh la lam FAQ)."""
    svc.check_admin()
    host = str(host or "").strip()
    pdoc = frappe.get_doc(svc.P, project)
    if host:
        if not _HOST.match(host) or host not in [h.get("host") for h in wc.call("hosts_list").get("hosts") or []]:
            raise frappe.ValidationError("Host không có trên máy chạy video (cần có khung neo).")
        pdoc.host_key = host
    else:
        pdoc.host_key = "H_" + flow.slug(pdoc.name, 12)
    st = svc._j(pdoc.state_json)
    st.pop("host_files", None)
    if host:                                     # 12/10 fix9p: khung neo cua host do thanh anh host du an
        from ecentric_workspace.ai_tools.features.ai_video.application import host as hostmod
        hostmod.adopt_existing(pdoc, st, "ecv6/hosts/%s/anchor.png" % host)
    svc._save_state(pdoc, st)
    return {"host_key": pdoc.host_key}


def stock(project):
    pdoc = frappe.get_doc(svc.P, project)
    r = wc.call("faq_stock", host=pdoc.host_key or svc._host_key(pdoc), talk_off=flow.talk_off(svc._pdict(pdoc)))
    r["vnd_per_credit"] = VND_PER_PX_CREDIT
    r["talk_count"] = int(pdoc.talk_count or 0)
    return r


# ------------------------------------------------------------------ voice + tron ---

def upload_voice(project, url, batch):
    """Tung file voice (trang goi lan luot) -> may chay video; tra duong dan de tron."""
    frappe.get_doc(svc.P, project)
    if not url or not str(url).lower().endswith(AUDIO_EXT):
        raise frappe.ValidationError("Chỉ nhận file voice .mp3 / .wav / .m4a.")
    svc._check_files({"audio_file": url})
    name = str(url).rsplit("/", 1)[-1].rsplit(".", 1)[0]
    ext = svc._ext(url, ".mp3")
    fn = "%s_%s%s" % (flow.slug(name, 50), hashlib.md5(str(url).encode()).hexdigest()[:6], ext)   # ten co dau co the trung khi bo dau
    rel = wc.upload(_inbox(project, batch or svc._today()) + fn, fn, svc._file_bytes(url))
    return {"rel": rel, "name": name}


def mix(project, data):
    d = svc._j(data)
    pdoc = frappe.get_doc(svc.P, project)
    batch = (d.get("batch") or "").strip() or svc._today()
    pre = "ecv6/" + _inbox(project, batch)
    voices = []
    if d.get("mode") == "length":                # 12/10 fix9p: chi noi theo do dai (khong tieng) - N ban x X giay
        n, sec = int(d.get("n") or 0), float(d.get("seconds") or 0)
        if not (1 <= n <= MAX_VOICES) or not (3 <= sec <= 600):
            raise frappe.ValidationError("Số bản 1-%d, độ dài 3-600 giây." % MAX_VOICES)
        d["voices"] = []
        voices = [{"name": "noi_%ds_%02d" % (int(sec), i + 1), "dur": sec} for i in range(n)]
    for v in (d.get("voices") or [])[:MAX_VOICES + 1]:
        rel, name = str((v or {}).get("rel") or ""), str((v or {}).get("name") or "").strip()[:80]
        if not rel.startswith(pre) or ".." in rel or not rel.lower().endswith(AUDIO_EXT):
            raise frappe.ValidationError("Voice không hợp lệ (tải lại file voice cho đợt %s)." % batch)
        voices.append({"rel": rel, "name": name or rel.rsplit("/", 1)[-1].rsplit(".", 1)[0]})
    if not voices:
        raise frappe.ValidationError("Chưa có file voice nào.")
    if len(voices) > MAX_VOICES:
        raise frappe.ValidationError("Tối đa %d voice một lần." % MAX_VOICES)
    lead = max(0.0, min(3.0, float(d.get("lead_s") if d.get("lead_s") not in (None, "") else 0.5)))
    tail = max(0.3, min(5.0, float(d.get("tail_s") if d.get("tail_s") not in (None, "") else 0.8)))
    sku = "FAQ_" + flow.slug(batch, 30)
    meta = {"faq": 1, "voices": [v["name"] for v in voices], "lead_s": lead, "tail_s": tail, "sku": sku,
            "target": d.get("target"), "kind": "length" if d.get("mode") == "length" else "voice",
            "seconds": voices[0].get("dur") if d.get("mode") == "length" else None}
    if d.get("auto_ls") and d.get("mode") != "length":   # 14/10: tron xong tu lipsync (dot co tieng)
        meta["auto_ls"] = 1
    exp = frappe.get_doc({"doctype": svc.E, "project": project, "batch": batch, "items": json.dumps(meta, ensure_ascii=False),
                          "mode": "talk", "variants": len(voices), "duration": 0, "status": "running"})
    exp.insert(ignore_permissions=True)
    step = {"op": "faq", "host": pdoc.host_key or svc._host_key(pdoc), "brand": pdoc.brand, "batch_id": batch, "sku": sku,
            "voices": voices, "lead_s": lead, "tail_s": tail, "talk_off": flow.talk_off(svc._pdict(pdoc))}
    ids = svc._enqueue(project, step, pdoc.night_mode)
    exp.db_set("task_ids", json.dumps(ids))
    return {"export": exp.name, "voices": len(voices)}


def tick_export(pdoc, doc, tasks):
    """Goi tu service._tick_exports cho dot FAQ: gom task con (faq_one), do trung khung khi xong het."""
    meta = _meta(doc)
    if meta.get("lipsync"):
        return _tick_lipsync(pdoc, doc, meta, tasks)
    ids = svc._j(doc.task_ids, []) or []
    grown = False
    for i in list(ids):
        for c in ((tasks.get(i) or {}).get("result") or {}).get("spawned") or []:
            if c not in ids:
                ids.append(c)
                grown = True
    if grown:
        doc.task_ids = json.dumps(ids)
    sts = [tasks.get(i) for i in ids]
    if any(t is None or t.get("state") in ("queued", "running") for t in sts):
        if grown:
            doc.save(ignore_permissions=True)
        return                                    # con task dang chay (hoac worker chua bao ve)
    bad = [t for t in sts if t.get("state") != "done"]
    err = bad and (bad[0].get("error") or bad[0].get("state"))
    plan = next((((t or {}).get("result") or {}) for t in sts if ((t or {}).get("result") or {}).get("dir")), {})
    files, stats = [], {}
    for i in ids:
        r = (tasks.get(i) or {}).get("result") or {}
        files += r.get("files") or []
        if r.get("faq"):
            f = r["faq"]
            stats[f["file"].rsplit("/", 1)[-1]] = {"name": f.get("name"), "dur": f.get("dur"), "tail": f.get("tail"), "stutter": f.get("stutter")}
    meta["stats"] = stats
    if files and not meta.get("dup_task"):
        meta["dup_task"] = (svc._enqueue(pdoc.name, {"op": "dupcheck", "dir": plan.get("dir") or files[0].rsplit("/", 1)[0]}) or [None])[0]
        doc.items = json.dumps(meta, ensure_ascii=False)
        doc.files_json = json.dumps(files)
        doc.status = "running"
        doc.save(ignore_permissions=True)
        return
    dt = tasks.get(meta.get("dup_task")) or {}
    if meta.get("dup_task") and (not dt or dt.get("state") in ("queued", "running")):
        return
    dup = (dt.get("result") or {}).get("dup")
    if dup:
        meta["dup"] = {"self": dup.get("self_pct"), "cross": dup.get("cross_pct"), "thr": dup.get("thr")}
        for row in dup.get("rows") or []:
            stats.setdefault(row["file"], {}).update(self=row.get("self_pct"), cross=row.get("cross_pct"), best=row.get("best"),
                                                     best_pct=row.get("best_pct"))
    sku = meta.get("sku")
    if files and sku:
        try:
            z = wc.call("export", brand=pdoc.brand, batch_id=doc.batch, sku=sku).get("zip")
            if z:
                files.append(z)
        except frappe.ValidationError as e:
            frappe.log_error(title="ai_video faq export", message=str(e))
    made = len([f for f in files if f.endswith(".mp4")])
    st = "done" if not bad else ("error: %s" % str(err or "")[:100] if not made else "done (có lỗi)")
    if made:
        st += " · %d/%d video" % (made, len(meta.get("voices") or []))
    if meta.get("dup"):
        st += " · trùng chéo %s%% · nội bộ %s%%" % (meta["dup"]["cross"], meta["dup"]["self"])
    elif made:
        st += " · chưa đo được trùng khung"
    meta["stats"] = stats
    doc.items = json.dumps(meta, ensure_ascii=False)
    doc.files_json = json.dumps(files)
    doc.status = st[:140]
    doc.save(ignore_permissions=True)
    if meta.get("auto_ls") and made and not meta.get("ls_export"):
        _auto_lipsync(pdoc, doc, meta)


def _auto_lipsync(pdoc, doc, meta):
    """14/10: dot tron theo voice co tick 'Tu lipsync' -> xong la tao dot lipsync ngay (1 lan)."""
    try:
        r = lipsync(pdoc.name, doc.name)
        meta["ls_export"] = r.get("export")
    except frappe.ValidationError as e:
        meta["ls_export"] = "-"
        meta["ls_err"] = str(e)[:200]
        frappe.log_error(title="ai_video auto lipsync", message=str(e))
    doc.items = json.dumps(meta, ensure_ascii=False)
    doc.save(ignore_permissions=True)


# ------------------------------------------------------------------ lipsync (13/10) ---
#: MuseTalk (fal) + hau ky K15 tren may chay video: mo mieng theo do to giong, ghep mieng, lam net CAS, dap van da goc.
LS_MODEL = "musetalk"
#: Uoc TRAN chi phi fal MuseTalk (USD / giay video): do 13/10/2026 7-9 giay GPU / giay video x gia H100 niem yet $4.5/h.
LS_USD_PER_S = 0.012
LS_SUFFIX = "_LS"


def _ls_out(rel):
    d, fn = rel.rsplit("/", 1)
    return "%s%s/%s" % (d, LS_SUFFIX, fn)


def _wid(s):
    """Ten thu muc SKU tren may chay video (giong safeId cua worker): bo dau, ky tu la -> '_'."""
    import unicodedata
    s = unicodedata.normalize("NFD", str(s or ""))
    s = "".join(c for c in s if unicodedata.category(c) != "Mn").replace("\u0111", "d").replace("\u0110", "D")
    s = re.sub(r"[^A-Za-z0-9_.-]+", "_", s).lstrip("._")[:96]
    return s or "x"


def voiced_files(names, files):
    """16/10: dot tron SKU (B4) - video cua SKU co voice (B1 tai mp3) -> lipsync duoc ca doan cam SP.
    -> [{"file": ten.mp4, "rel": duong dan worker, "dur": giay uoc}]"""
    if not isinstance(names, list) or not names:
        return []
    rows = frappe.get_all(svc.I, filters={"name": ["in", [str(n) for n in names][:200]]},
                          fields=["name", "sku", "audio_file", "audio_seconds"])
    dirs = {}
    for r in rows:
        if r.get("audio_file") and r.get("sku"):
            dirs[_wid(r.sku)] = float(r.get("audio_seconds") or 0)
    out = []
    for f in files or []:
        f = str(f).replace("\\", "/")
        if not f.endswith(".mp4") or "/" not in f:
            continue
        d = f.rsplit("/", 2)[-2]
        if d in dirs and not d.endswith(LS_SUFFIX):
            pad = 2 * flow.VOICE_PAD_S if dirs[d] else 0
            out.append({"file": f.rsplit("/", 1)[-1], "rel": f, "dur": round(dirs[d] + pad, 1) if dirs[d] else None})
    return out


def lipsync(project, export, files=None):
    """Lipsync ca dot tron theo voice (hoac vai video): moi video -> 1 task 'lipsync' (musetalk) tren may chay video,
    ket qua nam canh thu muc goc, them duoi _LS. Dot lipsync la 1 dong Ket qua rieng.
    16/10: ca dot tron SKU (B4) co voice - lipsync ca doan noi lan doan cam san pham."""
    pdoc = frappe.get_doc(svc.P, project)
    src = frappe.get_doc(svc.E, export)
    meta = _meta(src)
    if src.project != project or not str(src.status or "").startswith("done"):
        raise frappe.ValidationError("Chỉ lipsync được đợt trộn đã xong.")
    if meta:
        if meta.get("lipsync") or meta.get("kind") == "length":
            raise frappe.ValidationError("Chỉ lipsync được đợt trộn theo voice đã xong.")
        vids = [f for f in (svc._j(src.files_json, []) or []) if str(f).endswith(".mp4")]
    else:
        vids = [x["rel"] for x in voiced_files(svc._j(src.items, None), svc._j(src.files_json, []))]
        if not vids:
            raise frappe.ValidationError("Đợt trộn này không có SKU nào có voice - tải file voice ở bước B1 rồi trộn lại.")
    want = svc._j(files, None) if isinstance(files, str) else files
    if want:
        want = {str(x) for x in want}
        vids = [f for f in vids if f.rsplit("/", 1)[-1] in want]
    vids = [f for f in vids if f.startswith("ecv6/output/") and ".." not in f and "/" in f]
    if not vids:
        raise frappe.ValidationError("Không có video nào để lipsync.")
    if len(vids) > MAX_VOICES:
        raise frappe.ValidationError("Tối đa %d video một lần." % MAX_VOICES)
    for r in frappe.get_all(svc.E, filters={"project": project, "status": "running"}, fields=["items"]):
        m = svc._j(r.get("items"), None)
        if isinstance(m, dict) and m.get("lipsync") and m.get("src") == export:
            raise frappe.ValidationError("Đợt này đang lipsync - chờ xong rồi làm tiếp.")
    names = [f.rsplit("/", 1)[-1] for f in vids]
    skus = sorted({f.rsplit("/", 2)[-2] + LS_SUFFIX for f in vids})
    meta2 = {"faq": 1, "lipsync": 1, "kind": "lipsync", "src": export, "model": LS_MODEL, "voices": names,
             "sku": skus[0], "skus": skus, "hold": 0 if meta else 1}
    exp = frappe.get_doc({"doctype": svc.E, "project": project, "batch": src.batch, "items": json.dumps(meta2, ensure_ascii=False),
                          "mode": "talk", "variants": len(vids), "duration": 0, "status": "running"})
    exp.insert(ignore_permissions=True)
    steps = [{"op": "lipsync", "model": LS_MODEL, "video": f, "out": _ls_out(f)} for f in vids]
    res = wc.call("enqueue", batch_id=project, night=bool(pdoc.night_mode), steps=steps)
    exp.db_set("task_ids", json.dumps(res.get("task_ids") or []))
    return {"export": exp.name, "videos": len(vids)}


def _tick_lipsync(pdoc, doc, meta, tasks):
    ids = svc._j(doc.task_ids, []) or []
    sts = [tasks.get(i) for i in ids]
    stats, files, gpu, bad = {}, [], 0.0, []
    for i, t in zip(ids, sts):
        t = t or {}
        r = t.get("result") or {}
        ls = r.get("lipsync") or {}
        fn = str(t.get("out") or ((r.get("files") or [""])[0])).rsplit("/", 1)[-1]
        if not fn:
            continue
        files += r.get("files") or []
        gpu += float(ls.get("gpu_sec") or 0)
        row = {"name": fn[:-4] if fn.endswith(".mp4") else fn, "state": t.get("state") or "?",
               "dur": (ls.get("out") or {}).get("dur"), "gpu": ls.get("gpu_sec"), "sec": ls.get("sec")}
        if t.get("state") in ("failed", "cancelled"):
            row["err"] = str(t.get("error") or t.get("state"))[:160]
            bad.append(t)
        elif t.get("state") == "running":
            row["prog"] = str(t.get("progress") or "")[:60]
        stats[fn] = row
    meta["stats"] = stats
    meta["gpu_sec"] = round(gpu, 1)
    running = any(t is None or t.get("state") in ("queued", "running") for t in sts)
    if running:
        new = json.dumps(meta, ensure_ascii=False)
        if new != doc.items:
            doc.items = new
            doc.save(ignore_permissions=True)
        return
    for sku in (meta.get("skus") or [meta.get("sku")] if files else []):
        if not sku:
            continue
        try:
            z = wc.call("export", brand=pdoc.brand, batch_id=doc.batch, sku=sku).get("zip")
            if z:
                files.append(z)
        except frappe.ValidationError as e:
            frappe.log_error(title="ai_video lipsync export", message=str(e))
    made = len([f for f in files if f.endswith(".mp4")])
    st = "done" if not bad else ("error: %s" % str(bad[0].get("error") or "")[:100] if not made else "done (có lỗi)")
    st += " · %d/%d video lipsync" % (made, len(ids))
    if gpu:
        st += " · GPU fal %ds" % round(gpu)
    doc.items = json.dumps(meta, ensure_ascii=False)
    doc.files_json = json.dumps(files)
    doc.status = st[:140]
    doc.save(ignore_permissions=True)


def export_view(ex, meta):
    """Them bang tung video (do dai, duoi, giat, trung) cho dot FAQ tren trang."""
    st = meta.get("stats") or {}
    urls = {f["name"]: f["url"] for f in ex.get("files") or []}
    rows = []
    for fn in sorted(set(st) | set(urls)):
        s = st.get(fn) or {}
        rows.append(dict(s, file=fn, url=urls.get(fn)))
    ex["faq"] = {"rows": rows, "dup": meta.get("dup"), "lead_s": meta.get("lead_s"), "voices": len(meta.get("voices") or []),
                 "kind": meta.get("kind") or "voice", "seconds": meta.get("seconds")}
    if meta.get("lipsync"):
        ex["faq"].update(src=meta.get("src"), gpu_sec=meta.get("gpu_sec"), hold=meta.get("hold") or 0)
    else:
        ex["faq"]["ls_usd_per_s"] = LS_USD_PER_S
    return ex
