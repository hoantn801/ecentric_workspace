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

NHO MODEL VUA SAP (28/09): Kie treo ~34s roi moi tra 500, va cac ban Gemini sap CUNG LUC.
Khong nho thi MOI lan goi deu phai cho 34s x tung ban Gemini moi toi duoc model con song.
Model hong kieu SAP (5xx, 429, treo, mat ket noi) bi danh dau DOWN_SECONDS; trong thoi gian
do cac lan goi khac bo qua no. Loi do NOI DUNG (JSON hong, thieu khoa) KHONG danh dau - do
la loi cua cau hoi do, khong phai model sap. Neu MOI model dung duoc deu dang bi danh dau
thi van thu het (khong bao gio tu choi chi vi bo nho). `models=` truyen tay (probe, AI
Content chi dung model chinh) thi bo qua bo nho: nguoi goi muon chinh model do.
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
#: giay. Du lau de khong dap vao Kie dang sap, du ngan de model song lai la dung ngay.
DOWN_SECONDS = 300
DOWN_KEY = "ec_ai_down::%s"
_OUTAGE_EXC = ("Timeout", "ReadTimeout", "ConnectTimeout", "ConnectionError", "TimeoutError",
               "ChunkedEncodingError", "ProtocolError", "RemoteDisconnected")


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


def is_outage(err):
    """PURE. Loi nay la model/Kie SAP (thu lai sau) hay loi cua rieng cau hoi nay?"""
    e = str(err or "")
    for prefix in ("HTTP ", "Kie code="):
        if e.startswith(prefix):
            digits = ""
            for ch in e[len(prefix):]:
                if not ch.isdigit():
                    break
                digits += ch
            code = int(digits) if digits else 0
            return code >= 500 or code == 429
    name = e.split(":", 1)[0].strip()
    return name in _OUTAGE_EXC


def _is_down(model):
    try:
        return bool(frappe.cache().get_value(DOWN_KEY % model))
    except Exception:
        return False


def _set_down(model, down):
    try:
        if down:
            frappe.cache().set_value(DOWN_KEY % model, 1, expires_in_sec=DOWN_SECONDS)
        else:
            frappe.cache().delete_value(DOWN_KEY % model)
    except Exception:
        pass


def _usable(model, files):
    d = dialects.dialect_of(model)
    return bool(d) and (not files or bool(dialects.ACCEPTS_FILES.get(d)))


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
    down = set()
    if not models:
        down = {m for m in chain if _usable(m, files) and _is_down(m)}
        if not any(_usable(m, files) and m not in down for m in chain):
            down = set()          # moi model dung duoc deu dang nghi -> van thu het
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
        if model in down:
            attempt["error"] = "vua sap (<%d phut) - bo qua, thu model ke" % (DOWN_SECONDS // 60)
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
            if is_outage(err):
                _set_down(model, True)
            continue
        if _is_down(model):
            _set_down(model, False)       # song lai -> cac lan goi khac dung ngay
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
