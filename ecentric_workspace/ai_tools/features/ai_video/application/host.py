# Copyright (c) 2026, eCentric and contributors
"""Buoc 0 cua du an: Host & khung neo (12/10/2026, fix9p).

Khung neo (host ngoi, 2 tay tren ban) lam TRUOC, roi du an chia 2 nhanh: video chi noi / video cam SP.
- anchor_start: tu anh host goc, may chay video gen 4 ung vien PlenX Full (loi thi tu chuyen Kie), giu dung mau nen.
- anchor_pick: chon 1 -> thanh anchor.png cua host; ERP luu luon anh do lam "anh host" cua du an
  (anh goc giu o state host_orig) -> ve khung SP va anh cam SP deu lam tu chinh khung neo => master cung khung hinh.
Du an moi co anchor_flow = "pick": khong tu tao khung neo tu master nua; chua chot khung neo thi chua tao anh cam."""
import re

import frappe

from ecentric_workspace.ai_tools.features.ai_video.application import service as svc
from ecentric_workspace.ai_tools.features.ai_video.domain import flow
from ecentric_workspace.ai_tools.features.ai_video.infrastructure import worker_client as wc

ANCHOR_PX = {"model": "nano-banana-full", "resolution": "2k", "credits": 10}
#: Khung neo tao het tren PlenX Full (da chot); PlenX loi thi worker tu chuyen Kie theo cai dat du phong.
ANCHOR_PROVIDERS = ("plenx", "plenx", "plenx", "plenx")


def anchor_start(project):
    pdoc = frappe.get_doc(svc.P, project)
    st = svc._j(pdoc.state_json)
    src = st.get("host_orig") or pdoc.host_image
    if not src:
        raise frappe.ValidationError("Chưa có ảnh host: vào Cài đặt dự án tải ảnh host (hoặc tạo từ ảnh chân dung).")
    rel = wc.upload("inbox/%s/host_src%s" % (flow.slug(pdoc.name, 20), svc._ext(src)), "host_src" + svc._ext(src), svc._file_bytes(src))
    host = pdoc.host_key or svc._host_key(pdoc)
    steps = [dict({"op": "anchor", "host": host, "host_image": rel, "variant": i + 1, "provider": pv},
                  **({"px": ANCHOR_PX} if pv == "plenx" else {})) for i, pv in enumerate(ANCHOR_PROVIDERS)]
    ids = wc.call("enqueue", batch_id=project, steps=steps).get("task_ids") or []
    st["anchor_flow"] = "pick"
    st["anchor_round"] = {"tasks": ids, "items": [], "picked": None}
    st.pop("anchor_error", None)
    pdoc.host_key = host
    svc._save_state(pdoc, st)
    return {"tasks": len(ids)}


def tick_round(pst, tasks):
    """Goi trong service._tick: cap nhat trang thai ung vien khung neo."""
    rd = pst.get("anchor_round")
    if not rd or not rd.get("tasks"):
        return
    rd["items"] = [{"id": i, "state": (tasks.get(i) or {}).get("state") or "queued", "out": (tasks.get(i) or {}).get("out"),
                    "error": str((tasks.get(i) or {}).get("error") or "")[:160]} for i in rd["tasks"]]


def round_view(pst):
    rd = pst.get("anchor_round") or {}
    items = []
    for k, it in enumerate(rd.get("items") or [{"id": i, "state": "queued"} for i in rd.get("tasks") or []]):
        done = it.get("state") == "done" and it.get("out")
        items.append({"id": it["id"], "state": it.get("state"), "error": it.get("error"), "n": k + 1,
                      "provider": ANCHOR_PROVIDERS[k] if k < len(ANCHOR_PROVIDERS) else "",
                      "thumb": svc._thumb(it["out"], 360) if done else None, "full": wc.sign(it["out"]) if done else None})
    return {"items": items, "picked": rd.get("picked"),
            "done": bool(items) and all(i["state"] in ("done", "failed", "cancelled", "blocked") for i in items)}


def _adopt_anchor(pdoc, st, anchor_rel):
    """Luu khung neo thanh anh host cua du an (ve khung SP + anh cam lam tu khung neo)."""
    url = svc._save_file("anchor_%s.png" % flow.slug(pdoc.name, 20), wc.fetch(anchor_rel))
    if not st.get("host_orig") and pdoc.host_image:
        st["host_orig"] = pdoc.host_image
    pdoc.host_image = url
    st.pop("host_uploaded", None)
    st.pop("host_rel", None)
    return url


def anchor_pick(project, task_id):
    pdoc = frappe.get_doc(svc.P, project)
    st = svc._j(pdoc.state_json)
    rd = st.get("anchor_round") or {}
    it = next((x for x in rd.get("items") or [] if x.get("id") == task_id and x.get("state") == "done" and x.get("out")), None)
    if not it:
        raise frappe.ValidationError("Ảnh này chưa xong hoặc không thuộc lượt tạo khung neo hiện tại.")
    m = re.search(r"anchor_c(\d+)\.png$", it["out"])
    if not m:
        raise frappe.ValidationError("Ảnh ứng viên không hợp lệ.")
    host = pdoc.host_key or svc._host_key(pdoc)
    r = wc.call("anchor_pick", host=host, cand=int(m.group(1)))
    _adopt_anchor(pdoc, st, r.get("anchor") or "ecv6/hosts/%s/anchor.png" % host)
    rd["picked"] = task_id
    st["anchor_round"] = rd
    st.pop("anchor_stale", None)
    st["anchor_flow"] = "pick"
    st.pop("talk_go", None)                      # 12/10 fix9q: chot khung neo khong tu gen clip noi
    hf = st.get("host_files") or {}
    hf["anchor"] = {"path": r.get("anchor") or "ecv6/hosts/%s/anchor.png" % host}
    st["host_files"] = hf
    old_talks = flow.talk_counts(hf)[0]
    svc._save_state(pdoc, st)
    return {"anchor": True, "old_talks": old_talks}


def adopt_existing(pdoc, st, anchor_rel):
    """Dung host co san (set_host): lay khung neo cua host do lam anh host du an."""
    try:
        _adopt_anchor(pdoc, st, anchor_rel)
    except Exception:
        frappe.log_error(title="ai_video adopt anchor")
    st["anchor_flow"] = "pick"
    st.pop("talk_go", None)
    st.pop("anchor_round", None)


def host_view(pst):
    return {"host_orig": pst.get("host_orig"), "anchor_flow": pst.get("anchor_flow") or "", "anchor_stale": bool(pst.get("anchor_stale")),
            "anchor_round": round_view(pst) if pst.get("anchor_round") else None}

