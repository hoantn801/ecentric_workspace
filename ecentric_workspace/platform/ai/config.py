# Copyright (c) 2026, eCentric and contributors
"""Cau hinh AI - CHO DUY NHAT doc khoa va model.

Ba o tren System Settings, het:
    ec_kie_api_key            khoa Kie (Password)
    ec_llm_model_kie          model chinh, vd gemini-3-8-flash
    ec_llm_model_kie_fallback model du phong, cach nhau dau phay, vd gemini-3-8-flash-openai, grok-4-7

Cong tac tat toan bo AI: site_config `ec_ai_disabled: 1` (khong can deploy).

KHONG con Google. Hoan chot 28/09: mot nguon Kie; model chinh loi thi thu model
khac CUNG ben Kie. `ec_gemini_api_key`, `ec_llm_provider`, `ec_llm_model`,
`ec_llm_model_summarizer`, `ec_llm_model_company_summary` khong con dong nao doc.
"""
import frappe

KEY_FIELD = "ec_kie_api_key"
PRIMARY_FIELD = "ec_llm_model_kie"
FALLBACK_FIELD = "ec_llm_model_kie_fallback"
DISABLED_FLAG = "ec_ai_disabled"

DEFAULT_PRIMARY = "gemini-3-8-flash"
#: Chuoi du phong - Hoan chot 28/09, theo 3 lan probe that (C:\dev\probe_kie_*.ps1):
#:  * Gemini QUA CONG OPENAI cua Kie (gemini-*-openai) dung ngay sau model chinh: luc
#:    /gemini/v1 sap (ca 3.8/3.7/3.6 treo 34s roi 500) cong nay van tra loi 8-14s VA DOC
#:    DUOC PDF -> cham slide / AI dien ho kem tep co du phong that, cung model Gemini.
#:  * BO gemini-3-7/3-6 qua /gemini/v1: ca 2 lan probe deu sap CUNG LUC voi 3.8, moi ban
#:    ton 34s cho vo ich.
#:  * gpt-6-luna: re (~$0.10/$0.50 gia goc), chi van ban. Chua tung thay no song.
#:  * grok-4-7 CUOI: song khi moi thu khac sap (7.1s). Chi van ban (PDF -> 500). $2/$6.
#:  * BO gpt-5-5: dat ($5/$30). Muon dung lai thi go vao o "AI - model du phong".
DEFAULT_FALLBACKS = ("gemini-3-8-flash-openai", "gemini-3-6-flash-openai", "gpt-6-luna",
                     "grok-4-7")


def _single(fieldname):
    return frappe.db.get_single_value("System Settings", fieldname) or ""


def looks_masked(value):
    """PURE. Truong Password doc thuong ra chuoi '*' dung do dai - gui di la 401 vo nghia."""
    v = str(value or "")
    return len(v) > 0 and set(v) == {"*"}


def api_key():
    """Khoa Kie. Doc bang duong Password - xem su co 17/09 trong gemini_api.api_key()."""
    try:
        from frappe.utils.password import get_decrypted_password
        key = get_decrypted_password("System Settings", "System Settings",
                                     KEY_FIELD, raise_exception=False) or ""
    except Exception:
        key = ""
    if not key:
        key = _single(KEY_FIELD)
    return "" if looks_masked(key) else key.strip()


def parse_models(text):
    """PURE. 'gpt-5-5, gemini-3-7-flash' -> ['gpt-5-5', 'gemini-3-7-flash'].

    Chuan hoa ve chu thuong, bo khoang trang, bo trung (giu thu tu). Go 'GPT-5-5 ' hay
    lap lai mot model thi van ra dung mot chuoi sach - khong de mot loi go phim thanh
    mot lan goi 400 luc 2 gio sang.
    """
    out = []
    for raw in str(text or "").replace(";", ",").replace("\n", ",").split(","):
        name = raw.strip().lower()
        if name and name not in out:
            out.append(name)
    return out


def primary_model():
    return (parse_models(_single(PRIMARY_FIELD)) or [DEFAULT_PRIMARY])[0]


def fallback_models():
    configured = _single(FALLBACK_FIELD)
    models = parse_models(configured) if configured else list(DEFAULT_FALLBACKS)
    return [m for m in models if m != primary_model()]


def chain(allow_fallback=True):
    """-> [model chinh, du phong 1, ...]."""
    first = primary_model()
    return [first] + (fallback_models() if allow_fallback else [])


def disabled():
    try:
        return bool(int(frappe.conf.get(DISABLED_FLAG) or 0))
    except Exception:
        return False
