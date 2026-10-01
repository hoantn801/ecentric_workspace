# Copyright (c) 2026, eCentric and contributors
"""Cong AI chung - TAO ANH (them 01/10/2026 cho anh bia Tin noi bo).

Cung MOT nguon voi gateway.generate(): khoa Kie doc tu config.api_key(), cong tac tat
config.disabled() (site_config `ec_ai_disabled`). Tinh nang nao can anh thi goi generate()
o day, khong tu goi Kie.

Model: mac dinh `google/nano-banana` (Kie Market, jobs API). Doi model khong can deploy:
site_config `ec_ai_image_model` (vd "google/nano-banana"). Chua co o tren System Settings
de khong phai them Custom Field - khi chat AI gom ve System Settings thi doc o config.py.

Kie Market la API BAT DONG BO:
    POST /api/v1/jobs/createTask   {model, input:{prompt, output_format, aspect_ratio}} -> data.taskId
    GET  /api/v1/jobs/recordInfo?taskId=...  -> data.state: waiting|queuing|generating|success|fail
         data.resultJson = '{"resultUrls": [...]}' (CHUOI JSON long trong JSON), data.failMsg
Moi task ra 1 anh -> n anh = n task song song. URL ket qua la tep tam cua Kie (het han sau
vai ngay) - nguoi goi PHAI tai ve va luu thanh File cua minh.

BAY cua Kie (project_llm_provider_kie): loi bao bang HTTP 200 + `code` khac 200 trong THAN.
parse_create / parse_record doc `code` truoc, khong tin HTTP status.
"""
import json
import time

import requests

from ecentric_workspace.platform.ai import config

BASE = "https://api.kie.ai/api/v1/jobs"
DEFAULT_MODEL = "google/nano-banana"
SITE_MODEL_KEY = "ec_ai_image_model"
CONNECT_TIMEOUT = 5
READ_TIMEOUT = 30
DONE_STATES = ("success", "fail")


def model():
    try:
        import frappe
        return (frappe.conf.get(SITE_MODEL_KEY) or DEFAULT_MODEL).strip()
    except Exception:
        return DEFAULT_MODEL


def available():
    try:
        return not config.disabled() and bool(config.api_key())
    except Exception:
        return False


# ------------------------------------------------------------------ PURE --------
def build_create(model_name, prompt, aspect_ratio="16:9"):
    return {"model": model_name, "input": {"prompt": prompt, "output_format": "png",
                                           "aspect_ratio": aspect_ratio}}


def _json(raw):
    try:
        return json.loads(raw or "")
    except (ValueError, TypeError):
        return None


def parse_create(status, raw):
    """-> (task_id, error)."""
    j = _json(raw)
    if status != 200 or not isinstance(j, dict):
        return "", "HTTP %s" % status
    if j.get("code") not in (200, "200"):
        return "", "Kie code=%s %s" % (j.get("code"), str(j.get("msg") or "")[:200])
    tid = ((j.get("data") or {}).get("taskId") or "").strip()
    return (tid, "") if tid else ("", "Kie khong tra taskId")


def parse_record(status, raw):
    """-> (state, urls, error). state rong = chua biet (thu lai lan sau)."""
    j = _json(raw)
    if status != 200 or not isinstance(j, dict):
        return "", [], "HTTP %s" % status
    data = j.get("data") or {}
    state = str(data.get("state") or "").lower()
    if state == "fail":
        return state, [], (data.get("failMsg") or data.get("failCode") or "Kie: tao anh that bai")[:300]
    if state != "success":
        return state, [], ""
    res = data.get("resultJson")
    res = _json(res) if isinstance(res, str) else (res or {})
    urls = [u for u in ((res or {}).get("resultUrls") or []) if isinstance(u, str) and u.startswith("http")]
    return state, urls, ("" if urls else "Kie: thanh cong nhung khong co anh")


# ------------------------------------------------------------------ goi that ---
def _headers(key):
    return {"Authorization": "Bearer %s" % key, "Content-Type": "application/json"}


def _create(key, body):
    r = requests.post(BASE + "/createTask", json=body, headers=_headers(key),
                      timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    return parse_create(r.status_code, (r.content or b"").decode("utf-8", "replace"))


def _record(key, task_id):
    r = requests.get(BASE + "/recordInfo", params={"taskId": task_id}, headers=_headers(key),
                     timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
    return parse_record(r.status_code, (r.content or b"").decode("utf-8", "replace"))


def generate(prompt, n=3, aspect_ratio="16:9", timeout=180, poll=3, sleep=time.sleep, clock=time.time):
    """-> {ok, urls, error, model, tasks}. Khong nem. Mot task loi thi van tra anh cua task con lai."""
    out = {"ok": False, "urls": [], "error": "", "model": model(), "tasks": []}
    if config.disabled():
        out["error"] = "ai_disabled"
        return out
    key = config.api_key()
    if not key:
        out["error"] = "no_key"
        return out
    errors = []
    for _ in range(max(1, int(n))):
        try:
            tid, err = _create(key, build_create(out["model"], prompt, aspect_ratio))
        except Exception as exc:
            tid, err = "", "%s: %s" % (type(exc).__name__, exc)
        if tid:
            out["tasks"].append(tid)
        elif err:
            errors.append(config_scrub(err, key))
    pending = list(out["tasks"])
    deadline = clock() + timeout
    while pending and clock() < deadline:
        sleep(poll)
        for tid in list(pending):
            try:
                state, urls, err = _record(key, tid)
            except Exception as exc:
                state, urls, err = "", [], ""
                errors.append(config_scrub("%s: %s" % (type(exc).__name__, exc), key))
            if state in DONE_STATES:
                pending.remove(tid)
                out["urls"].extend(urls)
                if err:
                    errors.append(err)
    if pending:
        errors.append("het %ss ma con %d anh chua xong" % (timeout, len(pending)))
    out["ok"] = bool(out["urls"])
    out["error"] = "; ".join(errors)[:1000]
    return out


def config_scrub(text, key):
    t = str(text or "")
    return t.replace(key, "***") if key else t
