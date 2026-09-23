# Copyright (c) 2026, eCentric and contributors
"""AI Livestream Script - sinh script cho mot SKU. Path A thay cho Server Script `ec_ail_generate`.

VI SAO PHAI RA KHOI SERVER SCRIPT. Sandbox khong nhan `timeout=` (da probe 26/08). Tu 23/09
duong chinh la Kie gemini-3-8-flash, do 20-45 giay mot luot va co luc treo: treo qua gioi han
request cua worker thi luot do CHET, khong kip roi ve Google. O day moi lan goi deu co tran.

Tong tran = KIE_TIMEOUT + GOOGLE_TIMEOUT phai NHO HON gioi han request cua worker (120s),
neu khong nhanh du phong khong bao gio chay toi.

HOP DONG voi trang /ai-content GIU NGUYEN nhu Server Script: nhan {"data": "<json>"}, tra
{"ok", "preset", "result", "model", "provider", "fell_back", "tokens", "generated_at", "by"}
hoac {"ok": False, "error", "detail"}. Trang goi method nay truoc, gap "khong co method" thi
tu roi ve Server Script - nen thu tu deploy khong quan trong.

Mot cong tac cho ca he: `System Settings.ec_llm_provider` (doc qua `gemini_api.provider()`),
giong het AI dien ho.

KHONG TU ROI VE GOOGLE (Vinh chot 23/09). Khac AI dien ho: o day Gemini 2.5 hay tu bia khi tai
lieu thieu (do 23/09: viet "khan giay" thanh bong tay trang, gan gia cua goi khac), con 3.8
dung lai va ghi `notes`. Kie hong thi tra `KIE_LOI` de NGUOI DUNG chon; trang gui
`provider: "google"` khi ho bam "Van viet bang Gemini 2.5". `allow_fallback: true` giu duong
roi tu dong cho ai can.
"""
import json

import frappe
import requests

from ecentric_workspace import gemini_api as llm

ROLES = ("EC AI Content", "System Manager")
#: (connect, read) giay. Tong 105s < 120s cua worker. Kie do 23/09: 9-48 giay mot luot.
KIE_TIMEOUT = (5, 55)
GOOGLE_TIMEOUT = (5, 40)
GOOGLE_DEFAULT_MODEL = "gemini-2.5-flash"
#: Chot 17/09 sau 3x3: Flash, nhiet do 0.4, BAT thinking (tat thinking: so luat bi pha 4 -> 13).
DEFAULT_TEMPERATURE = 0.4
DEFAULT_THINKING = 2048
GOOGLE_MAX_TOKENS = 8000
#: Gemini 3.x qua Kie nghi DAI hon han va thinkingBudget khong giu duoc tran. Do 23/09: 3/9
#: luot bi cat o ~11.300 token tong vi dung tran 8000; nang 16000 van cut mot luot 19.293
#: token. Gemini 3 Flash cho toi 65k dau ra.
KIE_MAX_TOKENS = 32000


# ------------------------------------------------------------------ pure ---

def unescape_prompt(text):
    """Prompt tung luu trong Long Text bi HTML-escape; dong KY TU CAM la dong bi dung."""
    t = text or ""
    if "&amp;" in t or "&lt;" in t or "&gt;" in t:
        t = t.replace("&lt;", "<").replace("&gt;", ">")
        t = t.replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
    return t


def build_payload(task, system_prompt, body, kie=False):
    cfg = {
        "temperature": body.get("temperature", DEFAULT_TEMPERATURE),
        "maxOutputTokens": body.get("max_tokens", KIE_MAX_TOKENS if kie else GOOGLE_MAX_TOKENS),
        "responseMimeType": "application/json",
        "thinkingConfig": {"thinkingBudget": body.get("thinking", DEFAULT_THINKING)},
    }
    return {
        "contents": [{"role": "user", "parts": [{"text": task}]}],
        "systemInstruction": {"parts": [{"text": system_prompt}]},
        "generationConfig": cfg,
    }


def parse_json_text(text):
    """-> object hoac None. Go rao ``` neu model boc JSON trong markdown."""
    t = (text or "").strip()
    if t.startswith("```"):
        nl = t.find("\n")
        if nl > 0:
            t = t[nl + 1:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    try:
        return json.loads(t.strip())
    except Exception:
        return None


def _google_shape(obj):
    text, finish = "", ""
    for cand in (obj.get("candidates") or []):
        for part in ((cand.get("content") or {}).get("parts") or []):
            if not part.get("thought"):
                text += part.get("text") or ""
        finish = cand.get("finishReason") or finish
    return text, finish


def sse_meta(body):
    """-> (usage, finishReason) tu than SSE cua Kie. Van ban lay bang `llm.parse_sse_text`."""
    usage, finish = {}, ""
    for line in (body or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        try:
            chunk = json.loads(line[5:].strip())
        except Exception:
            continue
        if chunk.get("usageMetadata"):
            usage = chunk["usageMetadata"]
        for cand in (chunk.get("candidates") or []):
            finish = cand.get("finishReason") or finish
    return usage, finish


# ------------------------------------------------------------ transport ---

def _call_kie(payload):
    """-> dict(text, usage, finish, err). Khong nem."""
    key = llm.kie_api_key()
    if not key:
        return {"text": "", "usage": {}, "finish": "", "err": "no_kie_key"}
    resp = None
    try:
        resp = requests.post(llm.KIE_URL % llm.kie_model(), json=payload, timeout=KIE_TIMEOUT,
                             headers={"Authorization": "Bearer %s" % key,
                                      "Content-Type": "application/json"})
        resp.raise_for_status()
    except Exception as exc:
        return {"text": "", "usage": {}, "finish": "",
                "err": llm.scrub("kie_http %s: %s" % (type(exc).__name__, exc), key)[:600]}
    # SSE thuong khong khai charset -> requests doan ISO-8859-1, tieng Viet vo.
    resp.encoding = "utf-8"
    body = resp.text
    why = llm.kie_error(body)
    if why:
        return {"text": "", "usage": {}, "finish": "", "err": llm.scrub(why, key)[:600]}
    text = llm.parse_sse_text(body)
    usage, finish = sse_meta(body)
    if not text:
        return {"text": "", "usage": usage, "finish": finish, "err": "kie_khong_co_text"}
    if parse_json_text(text) is None:
        # Kie tra chu nhung JSON cut/hong: KHONG bat nguoi dung chiu BAD_JSON, roi ve Google.
        return {"text": "", "usage": usage, "finish": finish,
                "err": "kie_json_hong finishReason=%s tokens=%s do_dai=%s"
                       % (finish, usage.get("totalTokenCount"), len(text))}
    return {"text": text, "usage": usage, "finish": finish, "err": ""}


def _call_google(payload, model):
    key = llm.api_key()
    if not key:
        return {"text": "", "usage": {}, "finish": "", "err": "no_key"}
    resp = None
    try:
        resp = requests.post(llm.GENERATE_URL % model, json=payload, timeout=GOOGLE_TIMEOUT,
                             headers={"x-goog-api-key": key, "Content-Type": "application/json"})
        resp.raise_for_status()
        obj = resp.json()
    except Exception as exc:
        return {"text": "", "usage": {}, "finish": "",
                "err": llm.scrub("google_http %s: %s" % (type(exc).__name__, exc), key)[:600]}
    text, finish = _google_shape(obj)
    return {"text": text, "usage": obj.get("usageMetadata") or {}, "finish": finish,
            "err": "" if text else "GEMINI_EMPTY"}


# -------------------------------------------------------------- endpoint ---

def _fail(code, detail):
    # KHONG nuot loi: su co 09/09 va 14/09 deu am tham vi except tran nuot het.
    try:
        frappe.log_error(title="ec_ail_generate " + code, message=str(detail)[:2000])
    except Exception:
        pass
    return {"ok": False, "error": code, "detail": str(detail)[:600]}


def _body(data):
    if isinstance(data, dict):
        return data
    try:
        return json.loads(data) if data else {}
    except Exception:
        return {}


@frappe.whitelist(methods=["POST"])
def generate(data=None):
    user = frappe.session.user
    if not user or user == "Guest":
        return _fail("NOT_LOGGED_IN", "Can dang nhap de tao script.")
    if not set(frappe.get_roles(user)) & set(ROLES):
        # Moi luot goi la mot luot dot quota; chi ai co role moi duoc dung.
        return _fail("NO_ROLE", "Tai khoan chua co role 'EC AI Content'.")

    body = _body(data)
    task = body.get("task") or ""
    if not task:
        return _fail("EMPTY_TASK", "Khong nhan duoc de bai.")
    system_prompt = unescape_prompt(
        frappe.db.get_single_value("System Settings", "ec_ail_prompt") or "")
    if not system_prompt:
        return _fail("NO_PROMPT", "System Settings.ec_ail_prompt dang rong.")

    prov = (body.get("provider") or llm.provider() or "google").strip().lower()
    want_kie = prov == llm.KIE_PROVIDER
    g_model = body.get("model") or GOOGLE_DEFAULT_MODEL

    res, used, model, kie_err = None, "", "", ""
    if want_kie:
        res = _call_kie(build_payload(task, system_prompt, body, kie=True))
        if res["err"]:
            kie_err = res["err"]
            if not body.get("allow_fallback"):
                try:
                    frappe.log_error(title="ec_llm_kie_failed_no_fallback",
                                     message=("ec_ail_generate: " + kie_err)[:1000])
                except Exception:
                    pass
                return {"ok": False, "error": "KIE_LOI", "provider": llm.KIE_PROVIDER,
                        "model": llm.kie_model(), "detail": kie_err[:600]}
            llm._log_fallback("ec_ail_generate: " + kie_err)
            res = None
        else:
            used, model = llm.KIE_PROVIDER, llm.kie_model()
    if res is None:
        res = _call_google(build_payload(task, system_prompt, body), g_model)
        used, model = llm.GOOGLE_PROVIDER, g_model
        if res["err"]:
            detail = res["err"] if not kie_err else "Kie: %s | du phong Google: %s" % (kie_err, res["err"])
            return _fail("GEMINI_CALL_FAILED", detail)

    data_out = parse_json_text(res["text"])
    if data_out is None:
        usage = res["usage"] or {}
        return _fail("BAD_JSON", "provider=%s finishReason=%s tokens=%s do_dai=%s | duoi: %s" % (
            used, res["finish"], usage.get("totalTokenCount"), len(res["text"]), res["text"][-200:]))

    return {"ok": True, "preset": body.get("preset") or "full", "result": data_out,
            "model": model, "provider": used, "fell_back": bool(want_kie and used == llm.GOOGLE_PROVIDER),
            "tokens": (res["usage"] or {}).get("totalTokenCount"),
            "generated_at": str(frappe.utils.now())[:19], "by": user}
