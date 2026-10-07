# Copyright (c) 2026, eCentric and contributors
"""PURE. Than request + doc phan hoi cho tung ho model ben Kie.

Kie ban nhieu ho model, MOI HO MOT DINH DANG. Do that ngay 22/09 va 28/09:

    gemini-*  POST /gemini/v1/models/<m>:streamGenerateContent  (dinh dang Google)
              - nhan tep inline base64 (PDF, anh), nhan responseSchema
              - tra SSE, van ban CAT QUA NHIEU CHUNK -> phai noi het roi moi parse
              - LOI BAO BANG HTTP 200 + {"code":500,...} TRONG THAN
    gpt-*     POST /codex/v1/responses  (dinh dang OpenAI Responses)
              - 28/09: van ban OK (13.6s). input_file PDF -> 500, text.format
                json_schema -> 500. Nen: KHONG gui tep, JSON ep bang loi dan.
    gemini-*-openai  POST /<model>/v1/chat/completions  (Gemini qua cong OpenAI cua Kie;
              than gui model KHONG co hau to -openai). Probe 28/09 chieu: luc /gemini/v1
              sap (34s roi 500) thi cong nay van tra loi trong 8-14s VA DOC DUOC PDF
              (image_url + data URI). JSON ep bang loi dan (response_format chua do).
    grok-*    POST /grok/v1/responses   (CUNG dinh dang Responses nhu gpt-* -
              docs.kie.ai/market/grok/grok-4-7). Tai lieu noi nhan tep nhung CHUA DO
              -> tam coi nhu chi van ban, giong gpt-*.

Ho khac (claude-*...) chua do duoc -> khong ho tro, gateway bo qua va ghi ro.
File nay khong import frappe, khong goi mang: test chay khong can bench.
"""
import base64
import json

KIE_BASE = "https://api.kie.ai"
GEMINI = "gemini"
GEMINI_OAI = "gemini_oai"
OAI_SUFFIX = "-openai"
GPT = "gpt"
GROK = "grok"
#: Ho dung dinh dang OpenAI Responses (than + phan hoi giong nhau, chi khac URL).
RESPONSES = (GPT, GROK)

#: Ho nao mang duoc tep. Them ho moi vao day CHI SAU KHI da do that ho do doc duoc tep.
ACCEPTS_FILES = {GEMINI: True, GEMINI_OAI: True, GPT: False, GROK: False}


def dialect_of(model):
    m = str(model or "").strip().lower()
    if m.startswith("gemini-") and m.endswith(OAI_SUFFIX):
        return GEMINI_OAI
    if m.startswith("gemini-"):
        return GEMINI
    if m.startswith("gpt-"):
        return GPT
    if m.startswith("grok-"):
        return GROK
    return None


def url_for(model):
    d = dialect_of(model)
    if d == GEMINI:
        return "%s/gemini/v1/models/%s:streamGenerateContent" % (KIE_BASE, model)
    if d == GEMINI_OAI:
        return "%s/%s/v1/chat/completions" % (KIE_BASE, model)
    if d == GPT:
        return "%s/codex/v1/responses" % KIE_BASE
    if d == GROK:
        return "%s/grok/v1/responses" % KIE_BASE
    return ""


def json_instruction(schema):
    """Loi dan ep JSON cho ho KHONG nhan responseSchema."""
    return ("\n\nTra ve DUY NHAT mot doi tuong JSON hop le, khong markdown, khong giai thich"
            + (", dung schema sau:\n" + json.dumps(schema, ensure_ascii=False) if schema else "."))


def _history_pairs(history):
    """[{'role','text'}] -> [(role_chuan, text)] voi role_chuan in {'user','model'}."""
    out = []
    for h in history or []:
        text = str((h or {}).get("text") or "").strip()
        if not text:
            continue
        role = "user" if (h.get("role") or "user") == "user" else "model"
        out.append((role, text))
    return out


def build(model, prompt, system=None, schema=None, files=None, history=None,
          json_mode=False, opts=None):
    """-> than request (dict). `files` = [{'data': bytes, 'mime_type': str}]."""
    opts = dict(opts or {})
    want_json = bool(schema) or bool(json_mode)
    if dialect_of(model) == GEMINI_OAI:
        return _build_chat(model, prompt, system, schema, files, history, want_json, opts)
    if dialect_of(model) in RESPONSES:
        return _build_gpt(model, prompt, system, schema, history, want_json, opts)
    return _build_gemini(prompt, system, schema, files, history, want_json, opts)


def _build_gemini(prompt, system, schema, files, history, want_json, opts):
    contents = [{"role": r, "parts": [{"text": t}]} for r, t in _history_pairs(history)]
    parts = []
    for f in files or []:
        parts.append({"inlineData": {
            "mimeType": f.get("mime_type") or "application/octet-stream",
            "data": base64.b64encode(f["data"]).decode("ascii")}})
    parts.append({"text": prompt})           # tep TRUOC van ban: khuyen nghi cua Google
    contents.append({"role": "user", "parts": parts})
    cfg = {"temperature": opts.get("temperature", 0 if schema else 0.4)}
    if opts.get("max_tokens"):
        cfg["maxOutputTokens"] = int(opts["max_tokens"])
    if opts.get("thinking") is not None:
        cfg["thinkingConfig"] = {"thinkingBudget": int(opts["thinking"])}
    elif opts.get("effort") == "none":
        # thinkingLevel "minimal" bi Kie tra 500 (probe 28/09); budget 0 thi nhan.
        cfg["thinkingConfig"] = {"thinkingBudget": 0}
    if want_json:
        cfg["responseMimeType"] = "application/json"
    if schema:
        cfg["responseSchema"] = schema
    body = {"contents": contents, "generationConfig": cfg}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    return body


def _build_chat(model, prompt, system, schema, files, history, want_json, opts):
    """OpenAI chat/completions. Tep = image_url + data URI (dang probe 28/09 doc duoc PDF)."""
    messages = []
    if system:
        messages.append({"role": "system", "content": system})
    for role, text in _history_pairs(history):
        messages.append({"role": "user" if role == "user" else "assistant", "content": text})
    text = prompt + (json_instruction(schema) if want_json else "")
    if files:
        content = [{"type": "text", "text": text}]
        for f in files:
            content.append({"type": "image_url", "image_url": {"url": "data:%s;base64,%s" % (
                f.get("mime_type") or "application/octet-stream",
                base64.b64encode(f["data"]).decode("ascii"))}})
    else:
        content = text
    messages.append({"role": "user", "content": content})
    body = {"model": model[:-len(OAI_SUFFIX)], "stream": False, "messages": messages,
            "temperature": opts.get("temperature", 0 if schema else 0.4)}
    if opts.get("max_tokens"):
        body["max_tokens"] = int(opts["max_tokens"])
    if opts.get("effort") in ("none", "low", "medium", "high"):
        # "none" = tat suy nghi: 5-7s thay vi toi 25s (probe 28/09). "minimal" bi Kie tra 524.
        body["reasoning_effort"] = opts["effort"]
    return body


def _build_gpt(model, prompt, system, schema, history, want_json, opts):
    items = []
    if system:
        items.append({"role": "system", "content": [{"type": "input_text", "text": system}]})
    for role, text in _history_pairs(history):
        if role == "user":
            items.append({"role": "user", "content": [{"type": "input_text", "text": text}]})
        else:
            items.append({"role": "assistant", "content": [{"type": "output_text", "text": text}]})
    text = prompt + (json_instruction(schema) if want_json else "")
    items.append({"role": "user", "content": [{"type": "input_text", "text": text}]})
    body = {"model": model, "stream": False, "input": items,
            "reasoning": {"effort": opts.get("effort") if opts.get("effort") in
                          ("low", "medium", "high") else "low"}}
    return body


# ----------------------------------------------------------------- phan hoi ---

def kie_error(body):
    """-> ly do neu than bao loi kieu Kie (HTTP 200 + code != 200), "" neu khong."""
    text = (body or "").strip()
    if not text or text.startswith("data:"):
        return "" if text else "than rong"
    try:
        obj = json.loads(text)
    except Exception:
        return ""
    if not isinstance(obj, dict):
        return ""
    if "code" in obj:
        try:
            code = int(obj.get("code"))
        except Exception:
            code = 0
        if code and code != 200:
            return "Kie code=%s: %s" % (code, obj.get("msg") or obj.get("message") or "")
    err = obj.get("error")
    if err:
        if isinstance(err, dict):
            return "Kie loi: %s" % (err.get("message") or err.get("type") or err)
        return "Kie loi: %s" % err
    return ""


def _gemini_parse(body):
    texts, usage, finish = [], {}, ""
    for line in (body or "").splitlines():
        line = line.strip()
        if not line.startswith("data:"):
            continue
        payload = line[5:].strip()
        if not payload or payload == "[DONE]":
            continue
        try:
            chunk = json.loads(payload)
        except Exception:
            continue
        if chunk.get("usageMetadata"):
            usage = dict(chunk["usageMetadata"], **({"credits_consumed": usage["credits_consumed"]}
                                                    if "credits_consumed" in usage else {}))
        if chunk.get("credits_consumed") is not None:
            usage = dict(usage, credits_consumed=chunk["credits_consumed"])
        for cand in chunk.get("candidates") or []:
            finish = cand.get("finishReason") or finish
            for part in (cand.get("content") or {}).get("parts") or []:
                if part.get("text") and not part.get("thought"):
                    texts.append(part["text"])
    return "".join(texts), usage, finish


def _gpt_parse(body):
    try:
        obj = json.loads(body or "")
    except Exception:
        return "", {}, ""
    texts = []
    for item in obj.get("output") or []:
        if item.get("type") != "message":
            continue
        for c in item.get("content") or []:
            if c.get("type") == "output_text" and c.get("text"):
                texts.append(c["text"])
    return "".join(texts), _with_credits(obj), obj.get("status") or ""


def _chat_parse(body):
    try:
        obj = json.loads(body or "")
    except Exception:
        return "", {}, ""
    texts, finish = [], ""
    for ch in obj.get("choices") or []:
        finish = ch.get("finish_reason") or finish
        content = (ch.get("message") or {}).get("content")
        if isinstance(content, str):
            texts.append(content)
        elif isinstance(content, list):
            texts.extend(c.get("text") or "" for c in content if isinstance(c, dict))
    return "".join(texts), _with_credits(obj), finish


def _with_credits(obj):
    """usage + `credits_consumed` cua Kie (nam ngoai usage, o goc than) neu co."""
    usage = dict(obj.get("usage") or {})
    if obj.get("credits_consumed") is not None:
        usage["credits_consumed"] = obj["credits_consumed"]
    return usage


def parse(model, status, body):
    """-> (text, usage, finish, error). Khong nem."""
    why = kie_error(body)
    if status != 200:
        return "", {}, "", "HTTP %s%s" % (status, (": " + why) if why else "")
    if why:
        return "", {}, "", why
    if dialect_of(model) == GEMINI_OAI:
        text, usage, finish = _chat_parse(body)
    elif dialect_of(model) in RESPONSES:
        text, usage, finish = _gpt_parse(body)
    else:
        text, usage, finish = _gemini_parse(body)
    if not text:
        return "", usage, finish, "model tra ve rong (finish=%s)" % (finish or "?")
    return text, usage, finish, ""


def parse_json_object(text):
    """-> dict hoac None. Go rao ``` va chu thua quanh doi tuong JSON."""
    t = (text or "").strip()
    if t.startswith("```"):
        nl = t.find("\n")
        t = t[nl + 1:] if nl > 0 else t[3:]
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    t = t.strip()
    try:
        obj = json.loads(t)
    except Exception:
        start, end = t.find("{"), t.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            obj = json.loads(t[start:end + 1])
        except Exception:
            return None
    return obj if isinstance(obj, dict) else None


def missing_required(schema, data):
    """PURE. Khoa bat buoc cap ngoai cung ma model bo quen (ho GPT khong bi schema ep)."""
    req = (schema or {}).get("required") or []
    return [k for k in req if k not in (data or {})]
