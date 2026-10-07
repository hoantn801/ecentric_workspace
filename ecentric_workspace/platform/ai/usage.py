# Copyright (c) 2026, eCentric and contributors
"""Ghi lai MOI luot goi AI - de danh gia ai dung AI, dung gi, ton bao nhieu (Hoan 07/10).

Moi tinh nang AI di qua `gateway.generate()` (chu) va `images.generate()` (anh), nen chi can
ghi o hai cho do la du ca ERP. Mot luot goi = mot dong `EC AI Usage Log`.

KHONG LUU NOI DUNG. Hoan chot 07/10: chi so lieu (ai, luc nao, tinh nang nao, model, thanh
cong/loi, thoi gian, token, credit) - nhan vien dung thoai mai, khong lo bi doc cau hoi.

Chi phi:
  * Kie tra `credits_consumed` (luong OpenAI cua Gemini, 28/09) -> dung so do (cost_source=kie).
  * Khong co -> uoc tinh tu token x bang gia (credit / 1 trieu token) -> cost_source=estimate.
    Bang gia: DEFAULT_PRICES + site_config `ec_ai_prices` {"model": [vao, ra]} (khong can deploy).
  * Khong biet gia -> credits = 0, cost_source rong: trang bao "chua du gia", khong doan.

Ghi log KHONG BAO GIO lam hong luot goi AI: moi loi o day bi nuot.
"""
import json

#: Tai khoan he thong (cron, job khong gan nguoi) - tach rieng, khong tinh vao "nhan su".
SYSTEM_USERS = ("Administrator", "Guest", "")
#: Luot thu nghiem ky thuat - khong phai su dung that.
SKIP_PURPOSES = ("probe_llm_health", "probe_inline_limit")
#: kie.ai/grok-4-7 (29/09): 160 credit ~ $0.8 -> 1 credit = $0.005.
USD_PER_CREDIT = 0.005
#: credit / 1 trieu token (vao, ra). Chi ghi gia DA THAY tren trang Kie; con lai them qua
#: site_config `ec_ai_prices`.
DEFAULT_PRICES = {"grok-4-7": (160.0, 480.0)}
DOCTYPE = "EC AI Usage Log"


def _int(v):
    try:
        return int(v or 0)
    except (TypeError, ValueError):
        return 0


def token_counts(usage):
    """PURE. usage cua 3 ho model -> (vao, ra, tong). Token suy nghi tinh vao 'ra'."""
    u = usage if isinstance(usage, dict) else {}
    if "promptTokenCount" in u or "candidatesTokenCount" in u or "totalTokenCount" in u:
        inp = _int(u.get("promptTokenCount"))
        out = _int(u.get("candidatesTokenCount")) + _int(u.get("thoughtsTokenCount"))
        tot = _int(u.get("totalTokenCount")) or inp + out
        return inp, out, tot
    inp = _int(u.get("prompt_tokens") or u.get("input_tokens"))
    out = _int(u.get("completion_tokens") or u.get("output_tokens"))
    tot = _int(u.get("total_tokens")) or inp + out
    return inp, out, tot


def base_model(model):
    m = str(model or "").strip().lower()
    return m[:-len("-openai")] if m.endswith("-openai") else m


def credits_for(model, usage, inp, out, prices):
    """PURE. -> (credit, nguon) voi nguon 'kie' | 'estimate' | '' (khong biet gia)."""
    u = usage if isinstance(usage, dict) else {}
    if u.get("credits_consumed") not in (None, ""):
        try:
            return round(float(u["credits_consumed"]), 4), "kie"
        except (TypeError, ValueError):
            pass
    p = (prices or {}).get(base_model(model)) or (prices or {}).get(str(model or "").lower())
    if p and (inp or out):
        return round((inp * float(p[0]) + out * float(p[1])) / 1e6, 4), "estimate"
    return 0.0, ""


def prices():
    out = dict(DEFAULT_PRICES)
    try:
        import frappe
        raw = frappe.conf.get("ec_ai_prices")
        extra = json.loads(raw) if isinstance(raw, str) else (raw or {})
        for k, v in (extra or {}).items():
            if isinstance(v, (list, tuple)) and len(v) == 2:
                out[str(k).lower()] = (float(v[0]), float(v[1]))
    except Exception:
        pass
    return out


def build_row(purpose, result, user, department="", price_table=None, images=0):
    """PURE. Ket qua gateway/images -> dict dong log. None neu khong can ghi."""
    if purpose in SKIP_PURPOSES:
        return None
    r = result if isinstance(result, dict) else {}
    usage = r.get("usage") or {}
    inp, out, tot = token_counts(usage)
    credits, source = credits_for(r.get("model"), usage, inp, out, price_table or {})
    err = "" if r.get("ok") else str(r.get("error") or "")[:240]
    return {"user": user or "", "department": department or "", "purpose": purpose or "?",
            "model": r.get("model") or "", "ok": 1 if r.get("ok") else 0,
            "fell_back": 1 if r.get("fell_back") else 0,
            "attempts": len(r.get("attempts") or []) or (1 if r.get("model") else 0),
            "latency_ms": _int(r.get("latency_ms")), "input_tokens": inp, "output_tokens": out,
            "total_tokens": tot, "credits": credits, "cost_source": source,
            "images": _int(images), "error": err}


def record(purpose, result, images=0):
    """Ghi mot dong. Khong nem - log hong khong duoc lam hong luot AI cua nguoi dung."""
    try:
        import frappe
        user = getattr(frappe.session, "user", "") or ""
        dept = ""
        if user not in SYSTEM_USERS:
            dept = frappe.db.get_value("Employee", {"user_id": user, "status": "Active"},
                                       "department") or ""
        row = build_row(purpose, result, user, dept, prices(), images=images)
        if not row:
            return None
        doc = frappe.get_doc(dict(row, doctype=DOCTYPE))
        doc.flags.ignore_permissions = True
        doc.insert(ignore_permissions=True, ignore_links=True)
        return doc.name
    except Exception:
        return None
