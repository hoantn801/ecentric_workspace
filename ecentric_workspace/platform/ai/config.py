# Copyright (c) 2026, eCentric and contributors
"""Cau hinh AI - CHO DUY NHAT doc khoa va model.

Bon o tren System Settings, het:
    ec_kie_api_key            khoa Kie (Password)
    ec_anthropic_api_key      khoa Claude / Anthropic (Password) - chi can khi chuoi co claude-*
    ec_llm_model_kie          model chinh, vd gemini-3-8-flash  (hoac claude-haiku-5-5)
    ec_llm_model_kie_fallback model du phong, cach nhau dau phay, vd gemini-3-8-flash-openai, grok-4-7

LINH HOAT DOI NHA CUNG CAP (Hoan 05/11): chuoi model tron Kie + Claude tuy y. Claude lam du
phong = them `claude-haiku-5-5` vao CUOI o du phong; Claude lam chinh = dat no o o model chinh.
Doi co hieu luc ngay, khong can deploy. Model claude-* goi thang Anthropic bang khoa rieng.

Cong tac tat toan bo AI: site_config `ec_ai_disabled: 1` (khong can deploy).

KHONG con Google. Hoan chot 28/09: mot nguon Kie; model chinh loi thi thu model
khac CUNG ben Kie. `ec_gemini_api_key`, `ec_llm_provider`, `ec_llm_model`,
`ec_llm_model_summarizer`, `ec_llm_model_company_summary` khong con dong nao doc.
"""
import json

import frappe

KEY_FIELD = "ec_kie_api_key"
ANTHROPIC_KEY_FIELD = "ec_anthropic_api_key"
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


def _password(field):
    """Doc truong Password bang duong giai ma - xem su co 17/09 trong gemini_api.api_key()."""
    try:
        from frappe.utils.password import get_decrypted_password
        key = get_decrypted_password("System Settings", "System Settings",
                                     field, raise_exception=False) or ""
    except Exception:
        key = ""
    if not key:
        key = _single(field)
    return "" if looks_masked(key) else str(key).strip()


def api_key():
    """Khoa Kie."""
    return _password(KEY_FIELD)


def anthropic_key():
    """Khoa Claude (Anthropic) - chi dung cho model claude-*."""
    return _password(ANTHROPIC_KEY_FIELD)


def keys_for(models):
    """-> {model: khoa} cho moi model trong chuoi. Doc o LUONG CHINH (can DB) roi moi chia
    cho luong phu cua dot song song. Model chua co khoa -> ''."""
    from ecentric_workspace.platform.ai import dialects
    cache, out = {}, {}
    for m in models or []:
        prov = dialects.provider_of(m)
        if prov not in cache:
            cache[prov] = anthropic_key() if prov == "anthropic" else api_key()
        out[m] = cache[prov]
    return out


def all_keys():
    """Moi khoa dang cai - de che khoi chuoi loi."""
    return [k for k in (api_key(), anthropic_key()) if k]


#: Doan khoa dai tu chung nay tro len ma lot vao chuoi loi thi cung bi che (Kie in lai mot
#: phan khoa trong than loi 401). 12 ky tu ngau nhien trung tinh co: xac suat ~0.
MIN_KEY_FRAGMENT = 12


def scrub_key(text, key, min_fragment=MIN_KEY_FRAGMENT):
    """PURE. Che khoa trong chuoi loi truoc khi no di vao Error Log / usage log / trang.

    Ba dang: nguyen van; ban da escape (requests nem InvalidHeader voi repr(gia tri header)
    -> xuong dong thanh "\\n", replace nguyen van truot - do bang requests 2.34 ngay 03/11);
    va doan con >= `min_fragment` ky tu (than loi 401 in lai nua khoa).
    """
    t = str(text or "")
    key = str(key or "")
    if not key or not t:
        return t
    forms = {key, repr(key)[1:-1], json.dumps(key)[1:-1]}
    for form in sorted(forms, key=len, reverse=True):
        if form:
            t = t.replace(form, "***")
    if len(key) > min_fragment:
        for size in range(len(key) - 1, min_fragment - 1, -1):
            for start in range(0, len(key) - size + 1):
                frag = key[start:start + size]
                if frag in t:
                    t = t.replace(frag, "***")
    return t


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


def fast_chain():
    """Chuoi cho tro chuyen: luong OpenAI truoc; Gemini goc bi bo khi da co ban OpenAI.

    Do 28-29/09 (probe_mate_speed.ps1, 2 lan x 2 cau x 2 luot):
      * Gemini goc: treo het tran 30s o 7/10 lan.
      * Gemini qua luong OpenAI, tat suy nghi: 5-12s nhung treo 2/8 lan.
      * Grok: 8/8 lan tra loi, 9-25s.
    Nen Grok dung NGAY SAU cac ban OpenAI: vao dot goi song song lam luoi do - Gemini
    nhanh thi dung Gemini, Gemini treo thi van co Grok. Thu tu con lai giu nhu System Settings.
    """
    full = chain(True)
    # Model chinh KHONG phai Kie (vd Claude): nguoi cai dat chon no lam chinh -> giu dau chuoi.
    lead = [full[0]] if full and full[0].startswith("claude-") else []
    full = full[len(lead):]
    oai = [m for m in full if m.endswith("-openai")]
    if not oai:
        return lead + full
    grok = [m for m in full if m.startswith("grok-")]
    rest = [m for m in full if m not in oai and m not in grok
            and (m + "-openai") not in oai]
    return lead + oai + grok + rest


def disabled():
    try:
        return bool(int(frappe.conf.get(DISABLED_FLAG) or 0))
    except Exception:
        return False
