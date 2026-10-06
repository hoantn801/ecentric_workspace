# Copyright (c) 2026, eCentric and contributors
"""AI Video hang loat - nghiep vu. ERP la noi nam trang thai (du an, SKU, lo xuat);
worker (n8n + ecv6.js tren laptop) chi lam viec nang va tra trang thai file.

Moi ham tra dict thuan de controllers/api.py boc envelope. tick() la trai tim: doc
worker mot lan cho ca du an, roi goi domain.flow.decide_item cho tung SKU. Trang goi
tick moi 15s khi dang mo; scheduler goi 10 phut/lan cho du an dang chay (chay dem)."""
import json
import os

import frappe

from ecentric_workspace.ai_tools.features.ai_video.domain import flow
from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client as wc

P, I, E = "EC AI Video Project", "EC AI Video Item", "EC AI Video Export"
ROLES = ("EC AI Content", "EC AI Video Admin", "System Manager")
#: Sua prompt dung chung + prompt theo nhom SP: chi quan tri (05/10/2026).
ADMIN_ROLES = ("EC AI Video Admin", "System Manager")
ITEM_FIELDS = ("sku", "product_name", "product_type", "product_category", "width_cm", "height_cm",
               "depth_cm", "size_pct", "pack_count", "notes", "product_image", "real_hold_image",
               "audio_seconds", "audio_file", "batch")
PROJECT_SETTINGS = ("title", "brand", "status", "anchor_source", "talk_count", "gate_motion", "gate_hold_a",
                    "night_mode", "audio_seconds", "mix_mode", "mix_variants", "notes", "host_image")


# ------------------------------------------------------------------ helpers ---

def check_role():
    if not set(ROLES) & set(frappe.get_roles(frappe.session.user)):
        raise frappe.PermissionError("Cần quyền EC AI Content.")


def is_admin():
    return bool(set(ADMIN_ROLES) & set(frappe.get_roles(frappe.session.user)))


def check_admin():
    if not is_admin():
        raise frappe.PermissionError("Chỉ quản trị AI Video (role EC AI Video Admin) được sửa prompt.")


def _j(s, d=None):
    try:
        return json.loads(s) if s else (d if d is not None else {})
    except ValueError:
        return d if d is not None else {}


def _pdict(doc):
    d = doc.as_dict()
    d["state"] = _j(doc.state_json)
    return d


def _idict(doc):
    d = doc.as_dict()
    d["state"] = _j(doc.state_json)
    return d


def _save_state(doc, state, **fields):
    for k, v in fields.items():
        doc.set(k, v)
    doc.state_json = json.dumps(state, ensure_ascii=False)
    doc.save(ignore_permissions=True)


def _file_bytes(file_url):
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        raise frappe.ValidationError("Không tìm thấy file %s" % file_url)
    return frappe.get_doc("File", name).get_content()


FILE_FIELDS = ("host_image", "product_image", "real_hold_image", "audio_file")
#: Anh phu cac mat (canh, sau, nap, anh cam that): toi da 4, gui kem anh chinh dien cho AI.
MAX_EXTRA = 4


def _check_files(d):
    """Chi cho gan file do CHINH nguoi dung tai len (hoac System Manager): tranh mot link
    File rieng tu bat ky bi gui sang worker."""
    sm = "System Manager" in frappe.get_roles(frappe.session.user)
    urls = [(k, d.get(k)) for k in FILE_FIELDS] + [("extra_images", u) for u in (d.get("extra_images") or [])]
    for k, url in urls:
        if not url:
            continue
        owner = frappe.db.get_value("File", {"file_url": url}, "owner")
        if owner is None or (owner != frappe.session.user and not sm):
            raise frappe.ValidationError("File không hợp lệ hoặc không phải của bạn: %s" % url)


def _ext(file_url, default=".png"):
    e = os.path.splitext(file_url or "")[1].lower()
    return e if e in (".png", ".jpg", ".jpeg", ".webp", ".mp3", ".wav", ".m4a") else default


def _enqueue(project, step, night=False):
    res = wc.call("enqueue", batch_id=project, night=bool(night), steps=[step])
    return res.get("task_ids") or []


def _host_key(pdoc):
    return pdoc.host_key or ("H_" + flow.slug(pdoc.name, 12))


# ------------------------------------------------------------------ project ---

def list_projects():
    rows = frappe.get_all(P, fields=["name", "brand", "title", "status", "host_image", "night_mode", "modified"],
                          order_by="modified desc", limit_page_length=500)
    items = frappe.get_all(I, fields=["project", "stage", "stage_state"], limit_page_length=20000)
    by = {}
    for it in items:
        by.setdefault(it.project, []).append(it)
    for r in rows:
        r["counts"] = flow.project_summary(by.get(r.name, []))
    return {"projects": rows, "worker_configured": wc.configured()}


def create_project(data):
    d = _j(data)
    if not (d.get("brand") or "").strip() or not (d.get("title") or "").strip():
        raise frappe.ValidationError("Cần tên brand và tên dự án.")
    _check_files(d)
    doc = frappe.get_doc(dict({k: d.get(k) for k in PROJECT_SETTINGS if d.get(k) not in (None, "")}, doctype=P))
    doc.insert(ignore_permissions=True)
    return {"name": doc.name}


def update_project(name, data):
    d = _j(data)
    _check_files({k: d[k] for k in FILE_FIELDS if k in d})
    doc = frappe.get_doc(P, name)
    for k in PROJECT_SETTINGS:
        if k in d:
            doc.set(k, d[k])
    doc.save(ignore_permissions=True)
    return {"name": doc.name}


def add_items(project, rows):
    frappe.get_doc(P, project)
    made = []
    for r in _j(rows, []):
        if not (r.get("sku") or "").strip():
            continue
        _check_files(r)
        doc = frappe.get_doc(dict({k: r.get(k) for k in ITEM_FIELDS if r.get(k) not in (None, "")},
                                  doctype=I, project=project, stage="new", stage_state="waiting",
                                  extra_images=json.dumps(list(r.get("extra_images") or [])[:MAX_EXTRA])))
        doc.insert(ignore_permissions=True)
        made.append(doc.name)
    return {"items": made}


def update_item(name, data):
    d = _j(data)
    _check_files(d)
    doc = frappe.get_doc(I, name)
    for k in ITEM_FIELDS:
        if k in d:
            doc.set(k, d[k])
    if "extra_images" in d:
        doc.extra_images = json.dumps(list(d.get("extra_images") or [])[:MAX_EXTRA])
    if "guide_bbox" in d:
        _set_bbox(doc, d.get("guide_bbox"))
    doc.save(ignore_permissions=True)
    return {"name": name}


def _set_bbox(doc, v):
    bb = flow.parse_bbox(v)
    if bb is None:
        raise frappe.ValidationError("Khung sản phẩm không hợp lệ.")
    st = _j(doc.state_json)
    st["guide_bbox"] = bb
    doc.state_json = json.dumps(st, ensure_ascii=False)


def delete_item(name):
    doc = frappe.get_doc(I, name)
    if doc.stage not in ("new", "pick", "ready", "done") and doc.stage_state != "error":
        raise frappe.ValidationError("SKU đang chạy, huỷ trước khi xoá.")
    frappe.delete_doc(I, name, ignore_permissions=True)
    return {"deleted": name}


def _ensure_host(pdoc):
    """Gui anh host len worker (mot lan) + khung neo tu host neu chon nguon host."""
    st = _j(pdoc.state_json)
    if not pdoc.host_image:
        raise frappe.ValidationError("Dự án chưa có ảnh host.")
    if st.get("host_uploaded") != pdoc.host_image:
        rel = wc.upload("inbox/%s/host%s" % (flow.slug(pdoc.name, 20), _ext(pdoc.host_image)),
                        "host" + _ext(pdoc.host_image), _file_bytes(pdoc.host_image))
        st["host_uploaded"], st["host_rel"] = pdoc.host_image, rel
        pdoc.host_key = _host_key(pdoc)
        _save_state(pdoc, st)
    return st


# ------------------------------------------------------------------ SKU actions ---

def start_holds(project, names):
    pdoc = frappe.get_doc(P, project)
    pst = _ensure_host(pdoc)
    groups = _group_map()
    started = []
    for n in _j(names, []):
        doc = frappe.get_doc(I, n)
        if doc.project != project or not doc.product_image:
            continue
        if doc.stage not in ("new", "pick") and doc.stage_state != "error":
            continue
        _start_holds_one(pdoc, pst, doc, groups)
        started.append(n)
    return {"started": started}


def _group_map():
    """Trang thai nhom SP tu worker; worker loi thi coi nhu khong co nhom (khong chan viec tao anh)."""
    try:
        return wc.call("groups_get").get("groups") or {}
    except wc.WorkerDown:
        raise
    except Exception:
        return {}


def _start_holds_one(pdoc, pst, doc, groups=None):
    st = _j(doc.state_json)
    rows = [r for r in frappe.get_all(I, filters={"project": pdoc.name, "product_category": doc.product_category},
                                      fields=["name", "stage", "stage_state", "state_json"]) if r.name != doc.name]
    # chi SKU DAU cua nhom "dang thu" moi dung cho duyet: SKU khac cung nhom dang bi chan thi thoi
    others = [r.stage for r in rows] + ["ready" for r in rows if r.stage_state != "error" and _j(r.state_json).get("force_gate")]
    if flow.needs_trial_gate(doc.product_category, groups if groups is not None else _group_map(), others):
        st["force_gate"] = True
    else:
        st.pop("force_gate", None)
    attempt = int(st.get("attempt") or 0) + 1
    job = flow.job_id(pdoc.brand, doc.sku, pdoc.name, attempt)
    prod = wc.upload("inbox/%s/%s_front%s" % (flow.slug(pdoc.name, 20), flow.slug(doc.sku, 40), _ext(doc.product_image)),
                     "front" + _ext(doc.product_image), _file_bytes(doc.product_image))
    extras = []
    refs = list(_j(doc.extra_images, []) or [])
    if doc.real_hold_image:
        refs.append(doc.real_hold_image)
    for i, url in enumerate(refs[:MAX_EXTRA]):
        extras.append(wc.upload("inbox/%s/%s_side%d%s" % (flow.slug(pdoc.name, 20), flow.slug(doc.sku, 40), i + 1, _ext(url)),
                                "side%d%s" % (i + 1, _ext(url)), _file_bytes(url)))
    fields = flow.hold_fields(doc.as_dict(), pdoc.brand)
    if st.get("guide_bbox"):
        fields["guide_bbox"] = st["guide_bbox"]
    step = {"op": "holds", "job_id": job, "fields": fields,
            "files": {"host_video": pst["host_rel"], "product_image": prod}, "extra_images": extras}
    ids = _enqueue(pdoc.name, step, pdoc.night_mode)
    st.update(job=job, attempt=attempt, tasks={"holds": ids}, cands=[], picked=None)
    _save_state(doc, st, job_id=job, stage="holds", stage_state="running", error="", selected_candidate="")


def pick(name, candidate):
    doc = frappe.get_doc(I, name)
    if doc.stage != "pick":
        raise frappe.ValidationError("SKU không ở bước chọn ảnh.")
    pdoc = frappe.get_doc(P, doc.project)
    st = _j(doc.state_json)
    ids = _enqueue(pdoc.name, {"op": "master", "job_id": st["job"], "candidate": candidate}, pdoc.night_mode)
    st.setdefault("tasks", {})["master"] = ids
    _save_state(doc, st, stage="master", stage_state="running", selected_candidate=candidate, error="")
    return {"stage": "master"}


def regen_holds(name, data=None):
    """Tao lai 2 anh cam (job moi). data: thong so moi (kich thuoc/ghi chu...) neu co."""
    doc = frappe.get_doc(I, name)
    d = _j(data)
    for k in ("width_cm", "height_cm", "depth_cm", "size_pct", "notes", "product_type", "product_category", "pack_count"):
        if k in d:
            doc.set(k, d[k])
    if "guide_bbox" in d:
        _set_bbox(doc, d.get("guide_bbox"))
        doc.save(ignore_permissions=True)
    pdoc = frappe.get_doc(P, doc.project)
    _start_holds_one(pdoc, _ensure_host(pdoc), doc)
    return {"stage": "holds"}


def approve(name):
    doc = frappe.get_doc(I, name)
    pdoc = frappe.get_doc(P, doc.project)
    stage, step = flow.approve_item(_idict(doc), _pdict(pdoc))
    st = _j(doc.state_json)
    st.setdefault("tasks", {})[stage] = _enqueue(pdoc.name, step, pdoc.night_mode)
    _save_state(doc, st, stage=stage, stage_state="running", error="")
    return {"stage": stage}


def regen_clip(name, dirs=None):
    doc = frappe.get_doc(I, name)
    pdoc = frappe.get_doc(P, doc.project)
    st = _j(doc.state_json)
    units, stage, extra = flow.regen_units(doc.stage, _j(dirs, None))
    wc.call("regen", job_id=st["job"], stage="unit", units=units)
    step = dict({"op": "units", "host": pdoc.host_key, "job_id": st["job"]}, **extra)
    st.setdefault("tasks", {})[stage] = _enqueue(pdoc.name, step, pdoc.night_mode)
    _save_state(doc, st, stage=stage, stage_state="running", error="")
    return {"stage": stage}


def retry(name):
    doc = frappe.get_doc(I, name)
    st = _j(doc.state_json)
    ids = (st.get("tasks") or {}).get(doc.stage) or []
    if not ids:
        raise frappe.ValidationError("Không có việc nào để chạy lại.")
    wc.call("retry", task_ids=ids)
    _save_state(doc, st, stage_state="running", error="")
    return {"stage": doc.stage}


def cancel_project(project):
    wc.call("cancel", batch_id=project)
    for n in frappe.get_all(I, filters={"project": project, "stage": ["in", list(flow.RUNNING_STAGES)]}, pluck="name"):
        frappe.db.set_value(I, n, {"stage_state": "error", "error": "Đã huỷ"})
    return {"ok": True}


# ------------------------------------------------------------------ tick ---

def tick(project):
    """Doc worker 1 lan, cap nhat moi SKU + khung neo/clip noi cua du an."""
    pdoc = frappe.get_doc(P, project)
    items = [frappe.get_doc(I, n) for n in frappe.get_all(I, filters={"project": project}, pluck="name")]
    jobs = sorted({_j(d.state_json).get("job") for d in items if _j(d.state_json).get("job")})
    host = pdoc.host_key or _host_key(pdoc)
    W = wc.call("status", batch_id=project, jobs=jobs, hosts=[host])
    tasks = {t["id"]: t for t in W.get("tasks") or []}
    jstate = {j["job_id"]: j for j in W.get("jobs") or []}
    hfiles = ((W.get("hosts") or [{}])[0] or {}).get("files") or {}
    pst = _j(pdoc.state_json)
    anchor_ready = "anchor" in hfiles
    need_from = None
    ctx = {"tasks": tasks, "jobs": jstate, "anchor_ready": anchor_ready}
    pd = _pdict(pdoc)
    pd["host_key"] = host
    for doc in items:
        d = _idict(doc)
        if d.get("stage_state") == "error":
            continue
        res = flow.decide_item(d, pd, ctx)
        st = d["state"]
        for key, step in res["steps"]:
            st.setdefault("tasks", {})[key] = _enqueue(project, step, pdoc.night_mode)
        if res["set"] or res["steps"]:
            _save_state(doc, st, **res["set"])
        need_from = need_from or res["need_anchor_from"]
    # khung neo + clip noi
    ast, _ = flow.tasks_state((pst.get("anchor") or {}).get("tasks"), tasks)
    if not anchor_ready and ast in ("none", "failed") and not pst.get("anchor_hold"):
        step = None
        if (pdoc.anchor_source or "master") == "host" and pst.get("host_rel"):
            step = {"op": "anchor", "host": host, "host_image": pst["host_rel"]}
        elif need_from:
            step = {"op": "anchor", "host": host, "from_master": True,
                    "host_image": "jobs/%s/prep/selected_master/selected_master_hold.png" % need_from}
        if step and ast != "failed":
            pst["anchor"] = {"tasks": _enqueue(project, step, pdoc.night_mode), "from": need_from}
        elif ast == "failed":
            pst["anchor_error"] = "Tạo khung neo lỗi - bấm Tạo lại khung neo."
    talk_n = len([k for k in hfiles if k.startswith("talk_") and not k.endswith("_rev")])
    want = int(pdoc.talk_count or 0)
    tst, _ = flow.tasks_state((pst.get("talk") or {}).get("tasks"), tasks)
    if anchor_ready and want > talk_n and tst != "running" and not pst.get("talk_hold"):
        pst["talk"] = {"tasks": _enqueue(project, {"op": "talk", "host": host, "fill_to": want}, pdoc.night_mode)}
    # chay dem: lo nao xong het thi nen zip
    if pdoc.night_mode:
        batches = {}
        for doc in items:
            batches.setdefault(doc.batch or "lo", []).append(doc.stage)
        zipped = pst.setdefault("zipped", {})
        for b, stages in batches.items():
            if stages and all(s == "done" for s in stages) and b not in zipped:
                try:
                    zipped[b] = wc.call("export", brand=pdoc.brand, batch_id=b).get("zip")
                except frappe.ValidationError:
                    pass
    _tick_exports(pdoc, tasks)
    pst["host_files"] = hfiles
    pst["breaker"] = W.get("breaker")
    if W.get("costs"):
        pst["costs"] = W.get("costs")
    pst["last_tick"] = str(frappe.utils.now_datetime())
    pdoc.host_key = host
    _save_state(pdoc, pst, anchor_state=("ready" if anchor_ready else ast),
                talk_state="%d/%d" % (talk_n, want))
    return {"ok": True}


def tick_all():
    """Scheduler (10 phut): du an dang chay co viec dang do hoac che do chay dem."""
    if not wc.configured():
        return
    for name in frappe.get_all(P, filters={"status": "Đang chạy"}, pluck="name"):
        busy = frappe.db.exists(I, {"project": name, "stage": ["in", list(flow.RUNNING_STAGES) + ["wait_anchor"]]})
        if not busy and not frappe.db.get_value(P, name, "night_mode"):
            continue
        try:
            tick(name)
            frappe.db.commit()
        except wc.WorkerDown:
            return                       # laptop tat: thu lai lan sau
        except Exception:
            frappe.db.rollback()
            frappe.log_error(title="ai_video tick %s" % name)


# ------------------------------------------------------------------ mix / export ---

def mix(project, data):
    """Tron N ban cho cac SKU da du clip, xong thi nen ZIP ca lo."""
    d = _j(data)
    pdoc = frappe.get_doc(P, project)
    names = d.get("items") or []
    mode = d.get("mode") or pdoc.mix_mode or "mix"
    n = max(1, min(20, int(d.get("variants") or pdoc.mix_variants or 5)))
    batch = d.get("batch") or "lo"
    exp = frappe.get_doc({"doctype": E, "project": project, "batch": batch, "items": json.dumps(names),
                          "mode": mode, "variants": n, "duration": float(d.get("duration") or pdoc.audio_seconds or 72),
                          "status": "running"})
    exp.insert(ignore_permissions=True)
    ids = []
    pd = _pdict(pdoc)
    pd.update(mix_mode=mode, mix_variants=n)
    for nm in names:
        doc = frappe.get_doc(I, nm)
        st = _j(doc.state_json)
        if mode != "talk" and doc.stage not in ("ready", "done"):
            continue
        voice = None
        if doc.audio_file:
            voice = wc.upload("inbox/%s/%s_voice%s" % (flow.slug(project, 20), flow.slug(doc.sku, 40), _ext(doc.audio_file, ".mp3")),
                              "voice" + _ext(doc.audio_file, ".mp3"), _file_bytes(doc.audio_file))
        it = doc.as_dict()
        it["batch"] = batch
        if d.get("duration"):
            it["audio_seconds"] = float(d["duration"])
        step = flow.mix_step(it, pd, st, voice)
        step["host"] = pdoc.host_key
        ids += _enqueue(project, step, pdoc.night_mode)
    if mode == "talk" and not names:
        step = {"op": "mix", "mode": "talk", "n": n, "duration_s": exp.duration, "brand": pdoc.brand,
                "batch_id": batch, "sku": "NOI_" + flow.slug(pdoc.title, 20), "host": pdoc.host_key, "jobs": []}
        ids += _enqueue(project, step, pdoc.night_mode)
    if not ids:
        exp.db_set("status", "error: không có SKU nào đủ clip")
        return {"export": exp.name, "tasks": 0}
    exp.db_set("task_ids", json.dumps(ids))
    return {"export": exp.name, "tasks": len(ids)}


def _tick_exports(pdoc, tasks):
    for ex in frappe.get_all(E, filters={"project": pdoc.name, "status": "running"}, fields=["name"]):
        doc = frappe.get_doc(E, ex.name)
        ids = _j(doc.task_ids, [])
        stt, err = flow.tasks_state(ids, tasks)
        if stt == "running":
            continue
        files = []
        for i in ids:
            files += ((tasks.get(i) or {}).get("result") or {}).get("files") or []
        doc.files_json = json.dumps(files)
        if stt == "failed" and not files:
            doc.status = "error: %s" % (err or "")[:120]
        else:
            try:
                doc.zip_path = wc.call("export", brand=pdoc.brand, batch_id=doc.batch).get("zip")
            except frappe.ValidationError as e:
                doc.zip_path = ""
                frappe.log_error(title="ai_video export", message=str(e))
            doc.status = "done" if stt == "done" else "done (có lỗi)"
        doc.save(ignore_permissions=True)


# ------------------------------------------------------------------ read model ---

def _thumb(path, w=540):
    return wc.sign(path, width=w)


def get_project(name, do_tick=0):
    if int(do_tick or 0) and wc.configured():
        try:
            tick(name)
            frappe.db.commit()
        except wc.WorkerDown as e:
            frappe.db.rollback()
            down = str(e)
        else:
            down = None
    else:
        down = None
    pdoc = frappe.get_doc(P, name)
    pst = _j(pdoc.state_json)
    hf = pst.get("host_files") or {}
    proj = {k: pdoc.get(k) for k in PROJECT_SETTINGS + ("name", "host_key", "anchor_state", "talk_state")}
    proj["anchor"] = hf.get("anchor") and {"thumb": _thumb(hf["anchor"]["path"]), "full": wc.sign(hf["anchor"]["path"])}
    proj["talks"] = [{"id": k, "url": wc.sign(v["path"])} for k, v in sorted(hf.items()) if k.startswith("talk_")]
    proj["breaker"] = pst.get("breaker")
    proj["last_tick"] = pst.get("last_tick")
    proj["anchor_error"] = pst.get("anchor_error")
    proj["zipped"] = {b: wc.sign(z) for b, z in (pst.get("zipped") or {}).items()}
    items = []
    for n in frappe.get_all(I, filters={"project": name}, order_by="creation asc", pluck="name"):
        doc = frappe.get_doc(I, n)
        st = _j(doc.state_json)
        it = {k: doc.get(k) for k in ITEM_FIELDS + ("name", "job_id", "stage", "stage_state", "error", "selected_candidate")}
        it["stage_label"] = flow.STAGE_LABEL.get(doc.stage or "new", doc.stage)
        it["extra_images"] = _j(doc.extra_images, []) or []
        it["candidates"] = st.get("cands_view") or []
        it["guide_bbox"] = st.get("guide_bbox") or ""
        it["force_gate"] = bool(st.get("force_gate"))
        it["units"] = st.get("units_view") or {}
        items.append(it)
    _attach_worker_views(name, items)
    proj["cost"] = flow.cost_view(pst.get("costs"), items)
    proj["is_admin"] = is_admin()
    exports = frappe.get_all(E, filters={"project": name}, fields=["name", "batch", "mode", "variants", "duration",
                                                                   "status", "zip_path", "files_json", "creation"],
                             order_by="creation desc", limit_page_length=30)
    for ex in exports:
        ex["zip_url"] = wc.sign(ex.zip_path) if ex.zip_path else None
        ex["files"] = [{"name": os.path.basename(f), "url": wc.sign(f)} for f in _j(ex.files_json, [])]
        ex.pop("files_json", None)
    return {"project": proj, "items": items, "exports": exports, "worker_down": down,
            "worker_configured": wc.configured()}


def _attach_worker_views(project, items):
    """Link xem anh cam / master / clip: hoi worker trang thai job (khong luu link vao DB)."""
    jobs = [it["job_id"] for it in items if it.get("job_id")]
    if not jobs or not wc.configured():
        return
    try:
        W = wc.call("status", batch_id="__none__", jobs=jobs)
    except (wc.WorkerDown, frappe.ValidationError):
        return
    js = {j["job_id"]: j for j in W.get("jobs") or []}
    for it in items:
        j = js.get(it.get("job_id")) or {}
        it["candidates"] = [{"id": c["id"], "thumb": _thumb(c["file"]["path"]), "full": wc.sign(c["file"]["path"])}
                            for c in j.get("candidates") or [] if c.get("file")]
        it["ai_reco"] = (j.get("ai_qc") or {}).get("recommended")
        it["master"] = j.get("master") and _thumb(j["master"]["path"])
        it["units"] = {k: wc.sign(v["path"]) for k, v in (j.get("units") or {}).items()
                       if k.startswith(("pickup_", "putdown_", "hold_"))}


def prompts_get():
    return wc.call("prompts_get")


def prompts_set(data):
    check_admin()
    d = _j(data)
    allowed = ("anchor_image", "talk", "putdown", "putdown_dir", "hold_suffix", "hold_generic")
    return wc.call("prompts_set", prompts={k: v for k, v in d.items() if k in allowed})


def worker_ping():
    try:
        r = wc.call("ping")
        return {"up": True, "breaker": r.get("breaker"), "pump": r.get("pump"), "key": r.get("key_present")}
    except wc.WorkerDown as e:
        return {"up": False, "message": str(e)}


def regen_anchor(project):
    pdoc = frappe.get_doc(P, project)
    wc.call("regen", stage="anchor", host=pdoc.host_key, job_id="x")
    pst = _j(pdoc.state_json)
    pst.pop("anchor", None)
    pst.pop("anchor_error", None)
    _save_state(pdoc, pst)
    return {"ok": True}


def regen_talk(project, ids):
    pdoc = frappe.get_doc(P, project)
    wc.call("regen", stage="talk", host=pdoc.host_key, job_id="x", units=[i for i in _j(ids, []) if i.startswith("talk_")])
    return {"ok": True}
