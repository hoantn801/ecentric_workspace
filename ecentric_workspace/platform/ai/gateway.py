# Copyright (c) 2026, eCentric and contributors
"""Cong AI chung: MOI tinh nang AI trong ERP goi `generate()`.

Thu lan luot tung model trong chuoi (config.chain): model chinh, roi du phong. Moi lan
thu co tran thoi gian rieng, ca chuoi co mot ngan sach chung - nguoi goi trong request
web (tran 120s cua worker) va trong job nen (tran cua queue) truyen ngan sach khac nhau.

BA LUAT KHONG DUOC NOI LONG:
  1. Co tep ma khong gui du tep -> KHONG GOI. Model van tra loi tren du lieu thieu, va
     cau tra loi do vao ho so (su co 25/09: 17/100 cho mot bao cao khong slide nao toi
     duoc model). Model khong nhan tep thi bi BO QUA, khong duoc goi voi mot nua.
  2. JSON sai hinh -> tinh la LOI cua lan thu do, thu model ke. Khong tra dict rong.
  3. Moi lan roi sang du phong + moi lan hong ca chuoi deu ghi Error Log. Khong co con
     so do thi khong ai biet model chinh hong bao nhieu.
"""
import time

import frappe
import requests

from ecentric_workspace.platform.ai import config, dialects

#: giay. Log AI dien ho 23-24/09: Kie 3.8 + 1 tep mat 15-30s; probe 28/09: Kie treo ~33s
#: roi moi tra 500. Tran cu 30s cat ngang DUNG khoang do - goc cua 538 ReadTimeout 25-28/09.
DEFAULT_ATTEMPT_TIMEOUT = 60
#: Tong cho ca chuoi khi goi tu request web: phai nho hon 120s cua worker.
DEFAULT_BUDGET = 100
#: Con it hon chung nay thi khong bat dau lan thu moi - chac chan bi cat giua chung.
MIN_ATTEMPT_SECONDS = 8
CONNECT_TIMEOUT = 5


def _post(url, body, key, read_timeout):
    """Tach rieng de test thay the. -> (status, than_utf8)."""
    resp = requests.post(url, json=body, timeout=(CONNECT_TIMEOUT, read_timeout),
                         headers={"Authorization": "Bearer %s" % key,
                                  "Content-Type": "application/json"})
    # SSE cua Kie khong khai charset -> requests doan ISO-8859-1 va tieng Viet vo nat.
    return resp.status_code, (resp.content or b"").decode("utf-8", "replace")


def scrub(text, key):
    t = str(text or "")
    return t.replace(key, "***") if key else t


def _log(title, message):
    try:
        frappe.log_error(title=title, message=str(message)[:2000])
    except Exception:
        pass


def _try_one(model, key, request, timeout):
    """-> (text, data, usage, finish, error). Khong nem."""
    body = dialects.build(model, request["prompt"], request["system"], request["schema"],
                          request["files"], request["history"], request["json_mode"],
                          request["opts"])
    try:
        status, raw = _post(dialects.url_for(model), body, key, timeout)
        text, usage, finish, err = dialects.parse(model, status, raw)
    except Exception as exc:
        return "", None, {}, "", "%s: %s" % (type(exc).__name__, exc)
    if err:
        return "", None, usage, finish, err
    data = None
    if request["schema"] or request["json_mode"]:
        data = dialects.parse_json_object(text)
        if data is None:
            return text, None, usage, finish, ("khong doc duoc JSON (finish=%s, dai=%d, duoi=%r)"
                                               % (finish or "?", len(text), text[-120:]))
        missing = dialects.missing_required(request["schema"], data)
        if missing:
            return text, None, usage, finish, "JSON thieu khoa bat buoc: %s" % ", ".join(missing)
    return text, data, usage, finish, ""


def generate(prompt, system=None, schema=None, files=None, history=None, json_mode=False,
             purpose="", allow_fallback=True, models=None, attempt_timeout=None,
             budget=None, opts=None):
    """-> dict:
        ok, text, data (dict khi co schema/json_mode), model, fell_back, error,
        attempts [{model, ok, error, ms}], latency_ms, files_in_request, usage, finish

    `files` = [{'data': bytes, 'mime_type': str}]. `history` = [{'role': 'user'|'model',
    'text'}]. `purpose` chi de doc log (vd "weekly_score", "formfill").
    """
    out = {"ok": False, "text": "", "data": None, "model": "", "fell_back": False,
           "error": "", "attempts": [], "latency_ms": 0, "files_in_request": 0,
           "usage": {}, "finish": ""}
    if config.disabled():
        out["error"] = "ai_disabled"
        return out
    key = config.api_key()
    if not key:
        out["error"] = "no_key"
        return out
    files = [dict(f) for f in (files or [])]
    if any(not f.get("data") for f in files):
        out["error"] = "co tep khong mang bytes - tu choi goi de khong gui thieu tep"
        return out

    request = {"prompt": prompt, "system": system, "schema": schema, "files": files,
               "history": history, "json_mode": json_mode, "opts": opts}
    chain = list(models) if models else config.chain(allow_fallback)
    budget = float(budget or DEFAULT_BUDGET)
    per_try = float(attempt_timeout or DEFAULT_ATTEMPT_TIMEOUT)
    started = time.time()

    for index, model in enumerate(chain):
        attempt = {"model": model, "ok": False, "error": "", "ms": 0}
        out["attempts"].append(attempt)
        dialect = dialects.dialect_of(model)
        if not dialect:
            attempt["error"] = "ho model nay chua ho tro (chi gemini-*, gpt-*)"
            continue
        if files and not dialects.ACCEPTS_FILES.get(dialect):
            attempt["error"] = "model khong nhan tep - bo qua, khong gui thieu tep"
            continue
        remaining = budget - (time.time() - started)
        if remaining < MIN_ATTEMPT_SECONDS:
            attempt["error"] = "het ngan sach thoi gian (%.0fs)" % budget
            break
        t0 = time.time()
        text, data, usage, finish, err = _try_one(model, key, request, min(per_try, remaining))
        attempt["ms"] = int((time.time() - t0) * 1000)
        if err:
            attempt["error"] = scrub(err, key)[:600]
            continue
        attempt["ok"] = True
        out.update({"ok": True, "text": text, "data": data, "model": model,
                    "fell_back": index > 0, "usage": usage, "finish": finish,
                    "files_in_request": len(files)})
        break

    out["latency_ms"] = int((time.time() - started) * 1000)
    trail = " | ".join("%s: %s" % (a["model"], a["error"] or "ok") for a in out["attempts"])
    if out["ok"] and out["fell_back"]:
        _log("ec_ai_fallback", "%s -> dung %s. %s" % (purpose or "?", out["model"], trail))
    if not out["ok"]:
        out["error"] = trail or "chuoi model rong"
        _log("ec_ai_failed", "%s: %s" % (purpose or "?", out["error"]))
    return out
