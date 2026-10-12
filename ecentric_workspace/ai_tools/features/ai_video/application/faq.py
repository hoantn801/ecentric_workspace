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
    return ex
