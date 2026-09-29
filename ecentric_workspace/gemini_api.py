"""
ecentric_workspace/api/gemini.py — Path A method for AI scoring binary handling.

Why this file exists:
  Frappe Server Script (RestrictedPython sandbox) cannot:
    - import requests
    - access response.content (raw bytes) — Frappe's make_get_request always JSON-parses
      or returns response.text (str, lossy for binary)
    - access exception attributes via getattr

  Path A: this module runs in normal Python (no sandbox), bypasses all those limits.
  Server Scripts call methods here via frappe.call("ecentric_workspace.api.gemini.<method>", ...).

Use cases:
  1. submit_weekly_update: upload Weekly Report file (PDF/PPT/XLSX/DOC) to Gemini Files API.
     For Office formats, converts to PDF via Microsoft Graph ?format=pdf endpoint.
  2. (Future) wtu_regenerate_ai: re-upload Office files after Gemini URI 48h TTL expiry.

Module path used by Server Script:
  frappe.call("ecentric_workspace.api.gemini.upload_from_sp_url", ...)

Place file at:
  ecentric_workspace/api/gemini.py
  (i.e., inside the `api` subdirectory of the app, next to existing api modules)
"""

import json

import frappe
import requests
import time
from urllib.parse import quote, unquote


# SharePoint site ID (BoxMe Operation site, hosting Weekly Reports folder)
SITE_ID = "boxmeglobal.sharepoint.com,c8988716-77c2-43e2-ad13-f420fdaeacee,3c357dd3-d1f7-4928-94d3-bca1ea0104a9"

# Office file extensions supported by Graph ?format=pdf conversion
# Source: https://learn.microsoft.com/en-us/graph/api/driveitem-get-content-format
OFFICE_EXTS = {
    "pptx", "ppt", "pps", "ppsx", "pot", "potx", "potm", "ppsm", "pptm",
    "docx", "doc", "rtf", "odt",
    "xlsx", "xls", "ods", "csv",
    "odp",
}

# Limits
DOWNLOAD_TIMEOUT = 60  # seconds for Graph download
UPLOAD_TIMEOUT = 60    # seconds for Gemini upload
WAIT_ACTIVE_MAX = 20   # max seconds polling Gemini for state=ACTIVE
WAIT_ACTIVE_INTERVAL = 2  # poll interval


# ─────────────────────────────────────────────────────────────────────────────
# Helpers (private — name prefix _ to discourage external use)
# ─────────────────────────────────────────────────────────────────────────────

def _extract_rel_path(sp_web_url, dept_clean):
    """Parse SP webUrl → 'Weekly Reports/<dept>/<filename>' relative path.

    Delegates to weekly_report.sharepoint, which is now the single place that
    knows the URL shapes. This function used to carry its own copy handling two
    of the three shapes, and missed the org share link that
    auto_convert_slides_org rewrites every deck into within 30 minutes. Result:
    re-uploading a deck to Gemini failed for every converted record, which on
    15/09 was the entire AI re-score backlog. Two copies of one rule, one of
    them a version behind.

    Note the deliberate behaviour change: the old copy fell back to a folder
    literally named "Unknown" when dept_clean was empty, which produced a valid
    path pointing at nothing and a 404 from Graph. Returning "" instead gives
    the caller a real reason.

    Returns: relative path (NOT URL-encoded — caller encodes), or "" if not parseable.
    """
    from ecentric_workspace.weekly_report import sharepoint

    return sharepoint.rel_path_from_web_url(sp_web_url or "", dept_clean or "")


def _file_extension(filename):
    """Lowercase extension without dot."""
    if "." not in filename:
        return ""
    return filename.rsplit(".", 1)[1].lower()


def _ascii_safe_header(s):
    """Make string ASCII-safe for HTTP header (RFC 7230).

    Transliterates common Unicode punctuation; replaces anything else > 0x7F with underscore.
    Used for X-Goog-Upload-File-Name to avoid latin-1 encoding crash on em dash, Vietnamese, etc.
    """
    translit = {
        "—": "-", "–": "-",
        "‘": "'", "’": "'",
        "“": '"', "”": '"',
        "…": "...",
    }
    out_chars = []
    for ch in s:
        if ch in translit:
            out_chars.append(translit[ch])
            continue
        cp = ord(ch)
        if cp < 128 and ch not in ("\r", "\n", "\t"):
            out_chars.append(ch)
        else:
            out_chars.append("_")
    return "".join(out_chars) or "file"


def scrub(text, *secrets):
    """Xoa khoa va URL mang khoa ra khoi mot thong diep loi.

    MOT cho duy nhat cho luat redact. Bon Server Script Gemini tren site (`gemini_chat`,
    `gemini_score_report`, `gemini_summarize_report`, `gemini_company_summary`) moi cai mang
    mot ban `strip_secrets()` ~40 dong giong het nhau - sua luat o mot cho thi ba cho kia
    van ho. Ham nay khong tro thanh ban thu nam: ca `upload_from_sp_url` lan `generate_json`
    deu goi no.
    """
    out = str(text)
    for secret in secrets:
        if secret:
            out = out.replace(str(secret), "***REDACTED***")
    # Khoa Google AI Studio lo ra ngoai ngu canh URL (vi du trong body loi cua nha cung cap).
    i = out.find("AIza")
    while i >= 0:
        j = i + 4
        while j < len(out) and (out[j].isalnum() or out[j] in "-_"):
            j += 1
        out = out[:i] + "AIza***REDACTED***" + out[j:]
        i = out.find("AIza", i + 4)
    # ?key=... / &key=...
    i = out.find("key=")
    while i >= 0:
        j = i + 4
        while j < len(out) and out[j] not in " &'\"()[]{}\n\r\t,;":
            j += 1
        out = out[:i] + "key=***REDACTED***" + out[j:]
        i = out.find("key=", i + 4)
    return out


def _wait_for_active(file_uri, gemini_api_key, max_wait=WAIT_ACTIVE_MAX):
    """Poll Gemini Files API GET /v1beta/files/<id> until state=ACTIVE or timeout.

    Fixes race condition: file uploaded → URI returned immediately, but Gemini may take
    a few seconds to "process" before generateContent can use it. Calling generateContent
    too early returns 400 "file not ready" (the score 400 we saw earlier).

    Returns: True if ACTIVE, False if FAILED or timeout.
    """
    if not file_uri:
        return False
    headers = {"x-goog-api-key": gemini_api_key}
    elapsed = 0
    while elapsed < max_wait:
        try:
            r = requests.get(file_uri, headers=headers, timeout=10)
            if r.status_code == 200:
                state = r.json().get("state", "")
                if state == "ACTIVE":
                    return True
                if state == "FAILED":
                    return False
                # Otherwise state is PROCESSING — keep polling
        except Exception:
            pass  # transient — keep polling
        time.sleep(WAIT_ACTIVE_INTERVAL)
        elapsed += WAIT_ACTIVE_INTERVAL
    return False  # timeout — return False but caller may still try (Gemini might be ready)


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def fetch_pdf_bytes(sp_web_url, graph_token, dept_clean=""):
    """Tai tep tu SharePoint ve BYTES PDF. Office -> PDF bang Graph ?format=pdf.

    Bóc ra tu `upload_from_sp_url` (2026-09-25) vi duong Kie CAN BYTES: Kie khong
    giai duoc file URI cua Google (URI tro ve generativelanguage.googleapis.com),
    no chi nhan inline base64. Truoc day bytes chi ton tai trong long ham upload
    roi bi vut di ngay sau khi day len Google.

    `upload_from_sp_url` goi chinh ham nay nen hanh vi duong cu KHONG doi.

    -> {"ok", "data" (bytes), "display_name", "converted_from", "size_bytes", "error"}
    """
    out = {"ok": False, "data": None, "display_name": "", "converted_from": "",
           "size_bytes": 0, "error": None}

    rel_path = _extract_rel_path(sp_web_url, dept_clean)
    if not rel_path:
        out["error"] = "Cannot extract rel_path from SP webUrl"
        return out

    filename = rel_path.rsplit("/", 1)[-1]
    ext = _file_extension(filename)
    needs_conversion = ext in OFFICE_EXTS
    out["converted_from"] = ext

    encoded_path = quote(rel_path, safe="/")
    base_url = ("https://graph.microsoft.com/v1.0/sites/" + SITE_ID
                + "/drive/root:/" + encoded_path + ":/content")
    dl_url = base_url + ("?format=pdf" if needs_conversion else "")

    try:
        r = requests.get(dl_url,
                         headers={"Authorization": "Bearer " + graph_token},
                         timeout=DOWNLOAD_TIMEOUT,
                         allow_redirects=True)  # Graph format=pdf tra 302 sang CDN
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        out["error"] = "Graph download failed: " + scrub(str(e), graph_token)[:300]
        return out

    if not pdf_bytes or len(pdf_bytes) < 100:
        out["error"] = "Downloaded content too small (" + str(len(pdf_bytes)) + " bytes)"
        return out
    # Ke ca ?format=pdf ket qua VAN phai la %PDF -- Graph co the "chuyen doi" hong
    # ma van tra 200 kem mot trang HTML loi.
    if not pdf_bytes.startswith(b"%PDF"):
        out["error"] = ("Not a valid PDF (first 8 bytes: " + pdf_bytes[:8].hex()
                        + ") -- Graph conversion may have failed silently")
        return out

    display_name = filename
    if needs_conversion and "." in display_name:
        display_name = display_name.rsplit(".", 1)[0] + ".pdf"

    out["ok"] = True
    out["data"] = pdf_bytes
    out["display_name"] = display_name
    out["size_bytes"] = len(pdf_bytes)
    return out


def upload_from_sp_url(sp_web_url, graph_token, gemini_api_key,
                       dept_clean="", wait_active=True):
    """Download file from SharePoint, convert Office→PDF if needed, upload to Gemini Files API.

    Server Script usage:
      result = frappe.call(
          "ecentric_workspace.api.gemini.upload_from_sp_url",
          sp_web_url=web_url,
          graph_token=graph_token,
          gemini_api_key=api_key,
          dept_clean=dept_clean,
          wait_active=True
      )
      if result.get("success"):
          new_uris.append({
              "name":       result["name"],
              "uri":        result["uri"],
              "expires_at": result["expires_at"],
              "mime_type":  "application/pdf"
          })

    Args:
      sp_web_url      : SP webUrl from slide_deck (Graph PUT response webUrl).
      graph_token     : Microsoft Graph access token (client_credentials).
      gemini_api_key  : Google AI Studio API key.
      dept_clean      : Department name with " - XX" suffix stripped, used to build path
                        for _layouts URL format. e.g. "Service" not "Service - EC".
      wait_active     : If True, poll Gemini until file state=ACTIVE (recommend for
                        immediate-use scenarios like submit→score).

    Returns dict:
      {
        "success":         True/False,
        "uri":             Gemini file URI (use in generateContent fileData.fileUri),
        "name":            ASCII-safe filename used for Gemini header,
        "display_name":    Original filename (with diacritics) for storage,
        "expires_at":      Gemini URI expiration ISO timestamp (48h from upload),
        "mime_type":       "application/pdf",
        "converted_from":  Original extension ("pdf", "pptx", etc.),
        "size_bytes":      Downloaded/converted PDF size,
        "active":          True if Gemini file state=ACTIVE after wait (only if wait_active=True),
        "error":           Error message if success=False
      }
    """
    result = {"success": False}

    got = fetch_pdf_bytes(sp_web_url, graph_token, dept_clean)
    result["converted_from"] = got.get("converted_from") or ""
    if not got.get("ok"):
        result["error"] = got.get("error")
        if "rel_path" in (got.get("error") or ""):
            result["sp_web_url_head"] = sp_web_url[:120]
        return result
    pdf_bytes = got["data"]
    display_name = got["display_name"]
    result["size_bytes"] = got["size_bytes"]

    # Step 6+7: Upload to Gemini Files API, wait for ACTIVE.
    up = upload_bytes(pdf_bytes, display_name, "application/pdf", gemini_api_key,
                      wait_active=wait_active)
    # `name`/`display_name` duoc dat KE CA khi upload hong — nguoi goi dung chung de bao loi
    # "tep X khong len duoc". Giu dung thu tu cu.
    result["name"] = up.get("name")
    result["display_name"] = up.get("display_name")
    if not up.get("success"):
        result["error"] = up.get("error")
        return result

    result["uri"] = up["uri"]
    result["expires_at"] = up.get("expires_at", "")
    result["mime_type"] = up.get("mime_type")
    result["active"] = up.get("active")
    result["success"] = True
    return result


def upload_bytes(data, filename, mime_type, gemini_api_key, wait_active=True,
                 timeout=UPLOAD_TIMEOUT):
    """Tai bytes len Gemini Files API. -> dict cung hinh dang voi `upload_from_sp_url`.

    Rut nguyen van tu than `upload_from_sp_url` (Step 6 + Step 7) de duong AI-dien-ho dung
    LAI dung buoc tai len do, thay vi chep lan thu hai. Duong SharePoint van goi vao day nen
    mot cai sua o buoc tai len chay cho ca hai — do la ly do tach, khong phai cho gon.

    KHONG whitelist: ham nay nhan `gemini_api_key` lam tham so (di san tu duong SharePoint,
    xem §9.2 tai lieu thiet ke). Mo ra cho client goi = bien server thanh proxy egress.

    `mime_type` di vao CA `Content-Type` cua lan POST LAN truong mime tra ve — Gemini doc
    kieu tep tu header nay, gui sai la no nhan nhung doc ra rac.
    """
    result = {"success": False, "size_bytes": len(data or b"")}
    header_name = _ascii_safe_header(filename)
    result["name"] = header_name
    result["display_name"] = filename
    try:
        gem_resp = requests.post(
            "https://generativelanguage.googleapis.com/upload/v1beta/files",
            data=data,
            headers={
                "x-goog-api-key": gemini_api_key,
                "X-Goog-Upload-Protocol": "raw",
                "X-Goog-Upload-File-Name": header_name,
                "Content-Type": mime_type,
            },
            timeout=timeout,
        )
        gem_resp.raise_for_status()
        gem_data = gem_resp.json()
        file_info = gem_data.get("file", {})
        uri = file_info.get("uri", "")
        if not uri:
            result["error"] = "Gemini upload OK but no URI in response: " + str(gem_data)[:200]
            return result
        result["uri"] = uri
        result["expires_at"] = file_info.get("expirationTime", "")
        result["mime_type"] = mime_type
    except Exception as e:
        # Redact gemini_api_key from error. Kem than phan hoi - cung ly do nhu `_why`.
        result["error"] = "Gemini upload failed: " + scrub(
            str(e) + _why(locals().get("gem_resp")), gemini_api_key)[:600]
        return result

    # Wait for ACTIVE state (race condition fix)
    if wait_active:
        result["active"] = _wait_for_active(uri, gemini_api_key)
    else:
        result["active"] = None  # not checked

    result["success"] = True
    return result


@frappe.whitelist()
def upload_batch(sp_web_urls, graph_token, gemini_api_key, dept_clean=""):
    """Batch version: upload multiple SP URLs in sequence. Returns list of results.

    Used by submit_weekly_update when user attaches multiple slide_deck files.
    Continues on individual failures — returns one result per URL.

    Args:
      sp_web_urls: list of webUrls (or JSON string of list — auto-parsed)
    """
    import json as _json
    if isinstance(sp_web_urls, str):
        try:
            sp_web_urls = _json.loads(sp_web_urls)
        except Exception:
            return {"success": False, "error": "sp_web_urls must be list or JSON list string"}
    if not isinstance(sp_web_urls, list):
        return {"success": False, "error": "sp_web_urls must be list"}

    results = []
    for url in sp_web_urls:
        if not url:
            continue
        r = upload_from_sp_url(
            sp_web_url=url,
            graph_token=graph_token,
            gemini_api_key=gemini_api_key,
            dept_clean=dept_clean,
            wait_active=True,
        )
        results.append(r)
    return {
        "success": True,
        "results": results,
        "ok_count": sum(1 for r in results if r.get("success")),
        "fail_count": sum(1 for r in results if not r.get("success")),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sinh JSON co rang buoc schema (AI dien ho - xem approval_center/shared/integrations)
# ─────────────────────────────────────────────────────────────────────────────

GENERATE_TIMEOUT = 30          # giay
MODEL_SETTING = "ec_llm_model"
DEFAULT_MODEL = "gemini-2.5-flash"
GENERATE_URL = ("https://generativelanguage.googleapis.com/v1beta/models/"
                "%s:generateContent")


def _single(fieldname):
    return frappe.db.get_single_value("System Settings", fieldname) or ""


def _looks_masked(value):
    """PURE. Frappe de lai '*' x do-dai trong cot cua tai lieu cho truong Password."""
    v = str(value or "")
    return len(v) > 0 and set(v) == {"*"}


def api_key():
    """Khoa Gemini tu System Settings. ROT CUOC PHAI DOC BANG DUONG PASSWORD.

    `ec_gemini_api_key` la truong kieu **Password**. Frappe cat bi mat sang bang `__Auth` va
    de lai trong cot cua tai lieu dung mot chuoi dau sao CUNG DO DAI. Nen
    `frappe.db.get_single_value()` tra ve 39 dau sao - dung kieu, dung do dai, va sai hoan
    toan. Gui no di thi Google tra "API key not valid", con dong log cua ta chi thay 400.
    Su co 17/09: ca duong AI-dien-ho chet tu G1 vi dung mot dong nay.

    Neu vi ly do nao do van doc ra mat na thi COI NHU KHONG CO KHOA. Gui mat na di la doi
    lay mot loi 400 vo nghia; noi thang "khoa doc ra la mat na" thi sua duoc trong 5 phut.
    """
    try:
        from frappe.utils.password import get_decrypted_password
        key = get_decrypted_password("System Settings", "System Settings",
                                     "ec_gemini_api_key", raise_exception=False) or ""
    except Exception:
        key = ""
    if not key:
        key = _single("ec_gemini_api_key")
    return "" if _looks_masked(key) else key


def current_model():
    """DUNG CHUNG mot khoa model voi cac Server Script Gemini.

    `gemini_score_report` doc dung dong nay. Neu duong nay khai mot khoa rieng thi hai
    duong se chay tren hai model khac nhau - do la cach su co quota 429 ngay 20/07 bat dau:
    mot duong am tham roi ve 2.5-pro trong khi duong kia van flash, va khong ai thay cho toi
    luc het quota.
    """
    return _single(MODEL_SETTING) or DEFAULT_MODEL


def upload_file_bytes(data, filename, mime_type, wait_active=True, timeout=UPLOAD_TIMEOUT):
    """`upload_bytes` nhung KHOA DOC SERVER-SIDE. Duong AI-dien-ho dung cai nay.

    Ly do co hai cua: `upload_bytes` nhan key lam tham so vi duong SharePoint (viet truoc,
    cho Server Script goi) van truyen key vao. Duong moi khong duoc hoc thoi quen do — no
    khong bao gio thay key, nen khong the lam ro key.
    """
    key = api_key()
    if not key:
        return {"success": False, "error": "no_key", "name": _ascii_safe_header(filename),
                "display_name": filename, "size_bytes": len(data or b"")}
    return upload_bytes(data, filename, mime_type, key,
                        wait_active=wait_active, timeout=timeout)


def _why(resp):
    """Ly do that tu than phan hoi cua Gemini. -> " | <ly do>" hoac "" neu khong co gi.

    Gemini tra {"error": {"message": "...", "status": "..."}} kem moi ma 4xx. Ham nay
    khong bao gio nem: no chay TRONG mot `except`, hong o day la nuot mat ca loi goc.
    """
    if resp is None:
        return ""
    try:
        data = resp.json()
        err = (data or {}).get("error") or {}
        msg = err.get("message") or ""
        status = err.get("status") or ""
        if msg or status:
            return " | Gemini: %s%s" % (msg, (" [%s]" % status) if status else "")
        return " | than: " + json.dumps(data)[:300]
    except Exception:
        pass
    try:
        return " | than: " + (resp.text or "")[:300]
    except Exception:
        return ""


# ═════════════════════════════════════════════════════════════════════════════
# LLM: DI QUA CONG AI CHUNG (platform/ai) - chot 28/09/2026
# ═════════════════════════════════════════════════════════════════════════════
# Truoc 28/09 file nay tu goi Kie roi tu roi ve Google. Gio MOT duong duy nhat:
# `ecentric_workspace.platform.ai.gateway.generate` - mot khoa Kie, model chinh +
# model du phong CUNG ben Kie. Khong con Google, khong con 2.5-pro (Hoan chot).
# Cac ham duoi day giu TEN cu de khong ai goi hong; ruot da doi.

KIE_PROVIDER = "kie"

#: Tran tep gui inline cho Kie.
#:
#: 25/09 dat 7MB bang UOC LUONG ("Kie khuyen ~10MB, base64 phong 33%"), chua do
#: bao gio. 29/09 Kie tu noi ra so that trong mot loi 400:
#:
#:   "The image URL<data:application/pdf;base64,...(truncated,len=5078436)>
#:    Inline data URL is too large. Upload the file and pass an HTTP(S) URL
#:    instead."
#:
#: len=5078436 la do dai BASE64, tuc PDF goc ~3.63 MiB -- tran cu cao GAP DOI
#: gioi han that, nen code cho qua nhung tep ma Kie chac chan tu choi: ban ghi
#: khong co diem, va ly do that thi nam o tan loi 400 cua Kie.
#:
#: TAM dat 3.5 MiB (duoi so quan sat duoc mot chut). Con so DUNG phai do bang
#: `probe_inline_limit()` roi cap nhat o day kem ngay do -- dung suy tiep tu mot
#: quan sat duy nhat, va gioi han co the khac nhau giua cac dialect.
#: [TEMP-WORKAROUND 2026-09-29: so uoc luong tu mot loi 400. Go sau khi do that.]
KIE_INLINE_MAX_BYTES = 3584 * 1024        # 3.5 MiB

#: Nen ma khong an gi thi dung som. Deck toan anh chup thi ha do phan giai an
#: ngay; deck la PDF xuat tu Office (anh da nen san, chu la vector) thi khong an
#: gi het -- 29/09 co ban 10.010.963 byte nen xong con 10.010.868, giam 95 byte,
#: sau khi ngon 25 giay cua worker. Bo cong suc vao mot don bay khong ton tai.
SHRINK_MIN_GAIN = 0.05                    # duoi 5% coi nhu khong an


def provider():
    """Giu cho nguoi goi cu. Tu 28/09 chi con Kie."""
    return KIE_PROVIDER


def kie_api_key():
    from ecentric_workspace.platform.ai import config
    return config.api_key()


def kie_model():
    from ecentric_workspace.platform.ai import config
    return config.primary_model()


# Chat luong anh khi thu nen. Khong ha vo han: slide bi lam mo den muc doc sai
# thi model VAN cham diem -- cham tren thu no khong doc noi, va khong ai biet.
# Tha tu choi con hon. Moi buoc: (ty le canh, chat luong JPEG).
SHRINK_STEPS = ((0.75, 75), (0.6, 65), (0.5, 55))
SHRINK_MIN_SCALE = 0.5          # san cung: khong nho hon mot nua canh
SHRINK_MAX_SECONDS = 25         # nen phai gon trong ngan sach 300s cua rq worker


def shrink_pdf_for_inline(data, max_bytes=KIE_INLINE_MAX_BYTES):
    """Ha do phan giai anh trong PDF cho lot tran inline. -> (bytes|None, ghi_chu).

    Dung pypdf + Pillow, ca hai di kem Frappe -- KHONG them phu thuoc moi vao
    Frappe Cloud (bench khong co PyMuPDF/pikepdf/ghostscript).

    Deck bao cao tuan gan nhu toan anh chup slide, nen ha do phan giai anh la don
    bay gan nhu duy nhat. Tra None khi het buoc, het gio, hoac thieu thu vien --
    nguoi goi PHAI coi do la "khong dung duoc Kie" va di Google voi DU tep, chu
    khong duoc gui mot phan.
    """
    if not data:
        return None, "khong co du lieu"
    if len(data) <= max_bytes:
        return data, ""

    try:
        import io as _io
        from pypdf import PdfReader, PdfWriter
        from PIL import Image
    except Exception as exc:
        return None, "thieu thu vien de nen PDF: %s" % exc

    started = time.time()
    last_size = len(data)

    for scale, quality in SHRINK_STEPS:
        if scale < SHRINK_MIN_SCALE:
            break
        if time.time() - started > SHRINK_MAX_SECONDS:
            return None, "het ngan sach thoi gian khi nen (da thu toi %.2f)" % scale
        try:
            reader = PdfReader(_io.BytesIO(data))
            writer = PdfWriter()
            for page in reader.pages:
                for img in list(getattr(page, "images", []) or []):
                    try:
                        pil = Image.open(_io.BytesIO(img.data))
                        w = max(1, int(pil.width * scale))
                        h = max(1, int(pil.height * scale))
                        pil = pil.convert("RGB").resize((w, h))
                        img.replace(pil, quality=quality)
                    except Exception:
                        # Mot anh hong khong duoc lam hong ca tep.
                        continue
                writer.add_page(page)
            out = _io.BytesIO()
            writer.write(out)
            shrunk = out.getvalue()
        except Exception as exc:
            return None, "nen PDF that bai: %s" % str(exc)[:200]

        if not (shrunk and shrunk.startswith(b"%PDF")):
            return None, "ket qua nen khong phai PDF hop le"
        last_size = len(shrunk)
        if last_size <= max_bytes:
            return shrunk, "da nen %d -> %d byte (ty le %.2f, chat luong %d)" % (
                len(data), last_size, scale, quality)

        # Buoc dau da khong an gi thi cac buoc sau cung the: ha do phan giai chi
        # an tren ANH BITMAP. PDF xuat tu Office co anh da nen san va chu la
        # vector -- khong co gi de ha. Dung ngay, dung ngon them 25 giay cua
        # worker de doi tu 10.010.963 xuong 10.010.868 byte (that, 29/09).
        gain = 1.0 - (float(last_size) / len(data))
        if gain < SHRINK_MIN_GAIN:
            return None, ("nen khong an: %d -> %d byte (giam %.1f%%, duoi nguong"
                          " %.0f%%). PDF nay khong phai anh bitmap nen ha do phan"
                          " giai vo ich -- can nguoi nop xuat lai file nhe hon."
                          % (len(data), last_size, gain * 100, SHRINK_MIN_GAIN * 100))
        # Buoc sau nen lai tu BAN GOC voi ty le manh hon, khong chong len ban vua
        # nen: nen hai lan sinh nhieu (artefact) ma khong nho hon bao nhieu.

    return None, ("van vuot tran sau khi nen het cac buoc: %d byte > %d "
                  "(san chat luong %.2f, ha them se lam AI doc sai slide)"
                  % (last_size, max_bytes, SHRINK_MIN_SCALE))




@frappe.whitelist(methods=["POST"])
def probe_llm_health():
    """Tung model trong chuoi AI co song khong - goi THAT mot cau ngan qua cong chung.

    KHONG BAO GIO tra ve khoa: chi co / khong + do dai.
    """
    frappe.only_for("System Manager")
    from ecentric_workspace.platform.ai import config, gateway
    key = config.api_key()
    out = {"key_present": bool(key), "key_len": len(key or ""), "disabled": config.disabled(),
           "chain": config.chain(), "models": {}}
    schema = {"type": "object", "properties": {"ping": {"type": "string"}}, "required": ["ping"]}
    for model in config.chain():
        res = gateway.generate('Tra ve dung {"ping": "pong"}', schema=schema, models=[model],
                               purpose="probe_llm_health", budget=60, attempt_timeout=55)
        out["models"][model] = {"ok": res["ok"], "ms": res["latency_ms"],
                                "error": res["error"][:400] if not res["ok"] else ""}
    return out


def _synthetic_pdf(target_bytes):
    """Mot PDF hop le, kich thuoc xap xi `target_bytes`. -> bytes|None.

    Dung anh NHIEU NGAU NHIEN: anh co quy luat se bi JPEG nen lai, va kich thuoc
    thu duoc se khong con dinh -- do bang thuoc co dan thi khong phai do.

    KHONG dung deck that de do: do la du lieu bao cao cua nguoi that, va phep do
    nay gui thang len Kie.
    """
    try:
        import io as _io
        import os as _os
        from PIL import Image
    except Exception:
        return None
    # JPEG chat luong 95 tren nhieu ngau nhien: ~1 byte moi pixel, du de uoc
    # luong. Do lai roi chinh mot lan cho sat.
    side = max(64, int((target_bytes) ** 0.5))
    for _ in range(4):
        img = Image.frombytes("RGB", (side, side), _os.urandom(side * side * 3))
        buf = _io.BytesIO()
        img.save(buf, format="PDF", quality=95)
        data = buf.getvalue()
        if abs(len(data) - target_bytes) <= target_bytes * 0.12:
            return data
        ratio = float(target_bytes) / max(1, len(data))
        side = max(64, int(side * (ratio ** 0.5)))
    return data


@frappe.whitelist(methods=["POST"])
def probe_inline_limit(sizes_mb=None, models=None):
    """Kie that su nhan tep inline toi bao nhieu? Do, khong doan.

    Vi sao ton tai: `KIE_INLINE_MAX_BYTES` tung duoc dat 7MB bang uoc luong tu
    tai lieu, va sai gap doi -- Kie tu choi o base64 len=5078436 (~3.63 MiB).
    Mot con so doan trung thi may; doan truot thi ban ghi khong co diem va ly do
    nam tan trong loi 400 cua Kie, khong ai thay.
    Gioi han co the KHAC nhau giua cac dialect (native vs openai), nen do TUNG
    model trong chuoi chu khong do mot lan roi suy ra.

    Thang gia dan, DUNG NGAY o lan dau that bai cua moi model -- de khong day
    hang chuc MB len Kie mot cach vo ich.

    KHONG in khoa. KHONG dung du lieu that.
    """
    frappe.only_for("System Manager")
    from ecentric_workspace.platform.ai import config, dialects, gateway

    ladder = sizes_mb or [2, 3, 3.5, 4, 5, 6, 8]
    if isinstance(ladder, str):
        ladder = [float(x) for x in ladder.replace(",", " ").split()]
    if isinstance(models, str):
        models = [x.strip() for x in models.split(",") if x.strip()]
    if models:
        chain = models
    else:
        # Chi do model NHAN duoc tep. `gpt-6-luna` va `grok-4-7` khong nhan, do
        # chung la day vai MB len roi nhan ve dung mot cau "model khong nhan tep".
        chain = [m for m in config.chain()
                 if dialects.ACCEPTS_FILES.get(dialects.dialect_of(m))]

    schema = {"type": "object", "properties": {"ok": {"type": "string"}},
              "required": ["ok"]}
    out = {"tran_dang_dat_bytes": KIE_INLINE_MAX_BYTES, "models": {}}
    for model in chain:
        rec = {"lon_nhat_nhan_duoc_bytes": 0, "nho_nhat_bi_tu_choi_bytes": None,
               "buoc": []}
        for mb in ladder:
            n = int(mb * 1024 * 1024)
            pdf = _synthetic_pdf(n)
            if not pdf:
                rec["buoc"].append({"mb": mb, "ket_qua": "khong tao duoc PDF thu"})
                break
            res = gateway.generate(
                'Tra ve dung {"ok": "yes"}', schema=schema, models=[model],
                files=[{"data": pdf, "mime_type": "application/pdf"}],
                purpose="probe_inline_limit", budget=120, attempt_timeout=110)
            step = {"mb": mb, "bytes_that": len(pdf), "ok": bool(res["ok"])}
            if not res["ok"]:
                step["loi"] = (res["error"] or "")[:200]
            rec["buoc"].append(step)
            if res["ok"]:
                rec["lon_nhat_nhan_duoc_bytes"] = len(pdf)
            else:
                rec["nho_nhat_bi_tu_choi_bytes"] = len(pdf)
                break        # thang gia dan: hong roi thi to hon cung hong
        out["models"][model] = rec

    oks = [r["lon_nhat_nhan_duoc_bytes"] for r in out["models"].values()
           if r["lon_nhat_nhan_duoc_bytes"]]
    out["nen_dat_tran_bytes"] = min(oks) if oks else 0
    out["ghi_chu"] = ("Lay MIN qua cac model, khong lay MAX: mot tep phai lot"
                      " duoc qua model du phong thi chuoi moi con y nghia.")
    return out


def generate_json(prompt, response_schema, system_instruction=None,
                  timeout=None, model=None, files=None, budget=None, purpose=""):
    """Goi AI, ep tra ve JSON dung `response_schema`. Di qua cong AI chung.

    `files` = [{"data": bytes, "mime_type", ...}] - thieu `data` o bat ky tep nao thi
    KHONG goi (luat 25/09: khong gui thieu tep). `model` (neu co) ep dung mot model.

    -> {"ok", "data", "error", "model", "latency_ms", "provider", "fell_back",
        "files_in_request", "attempts"}
    """
    from ecentric_workspace.platform.ai import gateway
    res = gateway.generate(prompt, system=system_instruction, schema=response_schema,
                           files=files, models=[model] if model else None,
                           attempt_timeout=timeout, budget=budget, purpose=purpose)
    out = {"ok": res["ok"], "data": res["data"], "error": res["error"] or None,
           "model": res["model"] or (res["attempts"][-1]["model"] if res["attempts"] else ""),
           "latency_ms": res["latency_ms"], "provider": KIE_PROVIDER,
           "fell_back": res["fell_back"], "files_in_request": res["files_in_request"],
           "attempts": res["attempts"]}
    if not res["ok"] and res["error"] == "no_key":
        out["error"] = "no_key"
    return out
