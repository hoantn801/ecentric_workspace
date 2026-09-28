# Copyright (c) 2026, eCentric and contributors
"""Cau hinh AI - CHO DUY NHAT doc khoa va model.

Ba o tren System Settings, het:
    ec_kie_api_key            khoa Kie (Password)
    ec_llm_model_kie          model chinh, vd gemini-3-8-flash
    ec_llm_model_kie_fallback model du phong, cach nhau dau phay, vd gpt-5-5

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
#: Do 28/09 (C:\dev\probe_kie_fallback.ps1): luc Gemini ben Kie tra 500 ca 3.8 lan 3.7,
#: gpt-5-5 van tra loi van ban trong 13.6s. Claude luc do 429. Nen du phong mac dinh la GPT.
DEFAULT_FALLBACKS = ("gpt-5-5",)


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
