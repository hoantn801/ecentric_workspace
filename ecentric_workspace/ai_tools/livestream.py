# Copyright (c) 2026, eCentric and contributors
"""AI Livestream Script - sinh script cho mot SKU. Path A thay cho Server Script `ec_ail_generate`.

28/09: di qua CONG AI CHUNG (`platform/ai/gateway`). Khoa, model chinh, model du phong
deu doc o mot cho (System Settings: ec_kie_api_key / ec_llm_model_kie /
ec_llm_model_kie_fallback). Khong con Google.

HOP DONG voi trang /ai-content GIU NGUYEN: nhan {"data": "<json>"}, tra
{"ok", "preset", "result", "model", "provider", "fell_back", "tokens", "generated_at", "by"}
hoac {"ok": False, "error", "detail"}.

KHONG TU DONG DOI MODEL (Vinh chot 23/09): model khac viet khac - 23/09 Gemini 2.5 tu bia
khi tai lieu thieu, con 3.8 dung lai va ghi `notes`. Model chinh hong thi tra `KIE_LOI` de
NGUOI DUNG chon. Nguoi dung bam "Van viet bang model khac" (trang gui `provider: "google"`
- ten cu cua nut, giu de trang khong phai sua) hoac gui `allow_fallback: true` thi chay
chuoi DU PHONG. Moi script ghi ro model da viet ra no.

Tran thoi gian: tong < 120s cua worker (cong AI tu cat theo ngan sach).
"""
import json

import frappe

from ecentric_workspace.platform.ai import config, gateway

ROLES = ("EC AI Content", "System Manager")
#: Chot 17/09 sau 3x3: nhiet do 0.4, BAT thinking (tat thinking: so luat bi pha 4 -> 13).
DEFAULT_TEMPERATURE = 0.4
DEFAULT_THINKING = 2048
#: Gemini 3.x nghi DAI: 23/09 3/9 luot bi cat o tran 8000; 16000 van cut. Cho 32000.
MAX_TOKENS = 32000
#: giay. Tong phai < 120s cua worker.
BUDGET = 105
ATTEMPT_TIMEOUT = 100


# ------------------------------------------------------------------ pure ---

def unescape_prompt(text):
    """Prompt tung luu trong Long Text bi HTML-escape; dong KY TU CAM la dong bi dung."""
    t = text or ""
    if "&amp;" in t or "&lt;" in t or "&gt;" in t:
        t = t.replace("&lt;", "<").replace("&gt;", ">")
        t = t.replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&")
    return t


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


def wants_fallback(body):
    """PURE. Nguoi dung CHU DONG chon viet bang model du phong?"""
    return bool(body.get("allow_fallback")) or (body.get("provider") or "").strip().lower() == "google"


def tokens_of(usage):
    return (usage or {}).get("totalTokenCount") or (usage or {}).get("total_tokens")


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

    use_fallback = wants_fallback(body)
    models = config.fallback_models() if use_fallback else [config.primary_model()]
    res = gateway.generate(task, system=system_prompt, json_mode=True, models=models,
                           purpose="ai_content", budget=BUDGET, attempt_timeout=ATTEMPT_TIMEOUT,
                           opts={"temperature": body.get("temperature", DEFAULT_TEMPERATURE),
                                 "max_tokens": body.get("max_tokens", MAX_TOKENS),
                                 "thinking": body.get("thinking", DEFAULT_THINKING)})
    if not res["ok"]:
        if res["error"] in ("no_key", "ai_disabled"):
            return _fail("AI_TAT" if res["error"] == "ai_disabled" else "NO_KEY", res["error"])
        if not use_fallback:
            # Model chinh hong: KHONG tu doi model - de nguoi dung chon (xem docstring).
            return {"ok": False, "error": "KIE_LOI", "provider": "kie",
                    "model": models[0], "detail": res["error"][:600]}
        return _fail("GEMINI_CALL_FAILED", res["error"])

    return {"ok": True, "preset": body.get("preset") or "full", "result": res["data"],
            "model": res["model"], "provider": "kie", "fell_back": use_fallback,
            "tokens": tokens_of(res["usage"]),
            "generated_at": str(frappe.utils.now())[:19], "by": user}
