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

SUC KHOE (health.py, 28/09): ti le thanh cong 60 phut gan nhat cua tung model < 30% thi
cung bi bo qua nhu model vua sap. Cung luat: `models=` truyen tay thi khong xet.

CHE DO NHANH `fast=True` cho tro chuyen (eC Mate, gemini_chat) - do 28/09: Gemini goc treo
toi 30s o 5/6 lan, luong OpenAI tat suy nghi tra loi 5-7s, Grok luon song nhung 12-25s:
  * chuoi = config.fast_chain(): luong OpenAI truoc, bo Gemini goc khi da co ban OpenAI;
  * GOI SONG SONG `race` model dau (mac dinh 3: hai ban Gemini OpenAI + Grok), lay ben nao
    tra loi DUNG truoc - khong ngoi cho mot model treo het tran roi moi thu model ke;
  * moi model trong dot duoc toi TAIL_TIMEOUT (Grok can 9-25s); dot hong ca thi thu tiep
    tung model con lai.
"""
import concurrent.futures as cf
import time

import frappe
import requests

from ecentric_workspace.platform.ai import config, dialects, health

#: giay. Log AI dien ho 23-24/09: Kie 3.8 + 1 tep mat 15-30s; probe 28/09: Kie treo ~33s
#: roi moi tra 500. Tran cu 30s cat ngang DUNG khoang do - goc cua 538 ReadTimeout 25-28/09.
DEFAULT_ATTEMPT_TIMEOUT = 60
#: Tong cho ca chuoi khi goi tu request web: phai nho hon 120s cua worker.
DEFAULT_BUDGET = 100
#: Con it hon chung nay thi khong bat dau lan thu moi - chac chan bi cat giua chung.
MIN_ATTEMPT_SECONDS = 8
CONNECT_TIMEOUT = 5
#: giay. Tran cho cac model thu SAU dot song song cua che do nhanh (Grok can 12-25s).
TAIL_TIMEOUT = 30
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


def timed_try(model, key, request, timeout):
    """_try_one + do thoi gian. KHONG cham frappe: chay duoc trong luong phu."""
    t0 = time.time()
    text, data, usage, finish, err = _try_one(model, key, request, timeout)
    return {"model": model, "text": text, "data": data, "usage": usage, "finish": finish,
            "error": err, "ms": int((time.time() - t0) * 1000)}


def _race(models, key, request, timeout):
    """Goi song song, tra (ket_qua_thang hoac None, [ket qua da xong], [model chua xong]).

    Luong phu chi goi HTTP; ghi cache/log de luong chinh lam. Khong doi luong thua: no tu
    het han theo tran thoi gian cua chinh no.
    """
    ex = cf.ThreadPoolExecutor(max_workers=len(models))
    futs = {ex.submit(timed_try, m, key, request, timeout): m for m in models}
    winner, done = None, []
    try:
        for f in cf.as_completed(futs, timeout=timeout + CONNECT_TIMEOUT + 1):
            r = f.result()
            done.append(r)
            if not r["error"]:
                winner = r
                break
    except cf.TimeoutError:
        pass
    ex.shutdown(wait=False)
    finished = {r["model"] for r in done}
    return winner, done, [m for m in models if m not in finished]


def generate(prompt, system=None, schema=None, files=None, history=None, json_mode=False,
             purpose="", allow_fallback=True, models=None, attempt_timeout=None,
             budget=None, opts=None, fast=False, race=None):
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
    if models:
        chain = list(models)
    elif fast and allow_fallback:
        chain = config.fast_chain()
    else:
        chain = config.chain(allow_fallback)
    race = max(1, int(race if race is not None else (3 if fast else 1)))
    down = set()
    if not models:
        down = {m for m in chain if _usable(m, files) and (_is_down(m) or health.unhealthy(m))}
        if not any(_usable(m, files) and m not in down for m in chain):
            # Ca Kie dang sap (probe 28/09 chieu: moi model deu hong). Thu DUNG MOT model
            # dung duoc dau tien de biet da song chua - khong bat nguoi dung cho ca chuoi
            # 34s x N roi van nhan loi.
            first = next((m for m in chain if _usable(m, files)), None)
            down = {m for m in down if m != first}
    budget = float(budget or DEFAULT_BUDGET)
    per_try = float(attempt_timeout or DEFAULT_ATTEMPT_TIMEOUT)
    started = time.time()

    attempts = {}
    live = []
    for model in chain:
        attempt = {"model": model, "ok": False, "error": "", "ms": 0}
        out["attempts"].append(attempt)
        attempts[model] = attempt
        dialect = dialects.dialect_of(model)
        if not dialect:
            attempt["error"] = "ho model nay chua ho tro (chi gemini-*, gpt-*, grok-*)"
        elif files and not dialects.ACCEPTS_FILES.get(dialect):
            attempt["error"] = "model khong nhan tep - bo qua, khong gui thieu tep"
        elif model in down:
            attempt["error"] = ("vua sap (<%d phut) hoac ti le thanh cong 60 phut < %d%% - bo qua"
                                % (DOWN_SECONDS // 60, int(health.THRESHOLD * 100)))
        else:
            live.append(model)

    def settle(r):
        a = attempts[r["model"]]
        a["ms"] = r["ms"]
        if r["error"]:
            a["error"] = scrub(r["error"], key)[:600]
            if is_outage(r["error"]):
                _set_down(r["model"], True)
                # Chi loi SAP moi tinh vao suc khoe; JSON hong la loi cua cau hoi nay.
                health.record(r["model"], False, r["ms"])
            return False
        if _is_down(r["model"]):
            _set_down(r["model"], False)  # song lai -> cac lan goi khac dung ngay
        health.record(r["model"], True, r["ms"])
        a["ok"] = True
        out.update({"ok": True, "text": r["text"], "data": r["data"], "model": r["model"],
                    "fell_back": chain.index(r["model"]) > 0, "usage": r["usage"],
                    "finish": r["finish"], "files_in_request": len(files)})
        return True

    wave = live[:race] if race > 1 else []
    if len(wave) > 1:
        remaining = budget - (time.time() - started)
        # Dot song song co Grok (cham 9-25s nhung luon song) lam luoi: cho moi model den
        # TAIL_TIMEOUT. Gemini xong truoc thi tra ngay, khong doi Grok.
        wave_timeout = min(max(per_try, TAIL_TIMEOUT), remaining)
        winner, done, pending = _race(wave, key, request, wave_timeout)
        for r in done:
            if r is not winner:
                settle(r)
        for m in pending:
            attempts[m]["error"] = "huy - model khac tra loi truoc" if winner else \
                "qua %.0fs chua tra loi" % wave_timeout
            if not winner:
                health.record(m, False, int(wave_timeout * 1000))
        if winner:
            settle(winner)
    else:
        wave = []

    for model in live[len(wave):]:
        if out["ok"]:
            break
        remaining = budget - (time.time() - started)
        if remaining < MIN_ATTEMPT_SECONDS:
            attempts[model]["error"] = "het ngan sach thoi gian (%.0fs)" % budget
            break
        cap = max(per_try, TAIL_TIMEOUT) if wave else per_try
        settle(timed_try(model, key, request, min(cap, remaining)))

    # Model khong duoc thu (da co ket qua / het ngan sach) khong nam trong vet - vet chi ke
    # nhung gi da xay ra.
    out["attempts"] = [a for a in out["attempts"] if a["ok"] or a["error"]]
    out["latency_ms"] = int((time.time() - started) * 1000)
    trail = " | ".join("%s: %s" % (a["model"], a["error"] or "ok") for a in out["attempts"])
    # Dot song song: model dau chi CHAM hon (bi huy) khong phai su co -> khong ghi Error Log,
    # neu khong moi cau chat deu de mot dong log.
    real_fault = any(a["error"] and not a["error"].startswith("huy") for a in out["attempts"])
    if out["ok"] and out["fell_back"] and real_fault:
        _log("ec_ai_fallback", "%s -> dung %s. %s" % (purpose or "?", out["model"], trail))
    if not out["ok"]:
        out["error"] = trail or "chuoi model rong"
        _log("ec_ai_failed", "%s: %s" % (purpose or "?", out["error"]))
    return out
