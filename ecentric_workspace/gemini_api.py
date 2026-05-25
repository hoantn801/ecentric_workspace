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

    Handles 2 URL formats:
      Direct path : https://...sharepoint.com/sites/operation/Shared Documents/Weekly Reports/<dept>/<file>
      Office viewer: https://...sharepoint.com/sites/operation/_layouts/15/Doc.aspx?sourcedoc={GUID}&file=<file>...

    Returns: relative path string (NOT URL-encoded — caller will encode), or "" if not parseable.
    """
    # Case 1: legacy direct path /Shared Documents/...
    for prefix in ("/sites/operation/Shared%20Documents/", "/sites/operation/Shared Documents/"):
        idx = sp_web_url.find(prefix)
        if idx >= 0:
            tail = sp_web_url[idx + len(prefix):]
            # Strip query/fragment if any
            for sep in ("?", "#"):
                if sep in tail:
                    tail = tail.split(sep, 1)[0]
            return unquote(tail)

    # Case 2: _layouts/Doc.aspx?sourcedoc=...&file=<filename>...
    if "_layouts/" in sp_web_url and "file=" in sp_web_url:
        f_idx = sp_web_url.find("file=")
        f_end = sp_web_url.find("&", f_idx + 5)
        if f_end < 0:
            f_end = len(sp_web_url)
        fname = unquote(sp_web_url[f_idx + 5:f_end])
        return "Weekly Reports/" + (dept_clean or "Unknown") + "/" + fname

    return ""


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

    # Step 1: Extract rel_path from webUrl
    rel_path = _extract_rel_path(sp_web_url, dept_clean)
    if not rel_path:
        result["error"] = "Cannot extract rel_path from SP webUrl"
        result["sp_web_url_head"] = sp_web_url[:120]
        return result

    # Step 2: Detect extension
    filename = rel_path.rsplit("/", 1)[-1]
    ext = _file_extension(filename)
    needs_conversion = ext in OFFICE_EXTS
    result["converted_from"] = ext

    # Step 3: Build Graph download URL
    encoded_path = quote(rel_path, safe="/")
    base_url = (
        "https://graph.microsoft.com/v1.0/sites/" + SITE_ID
        + "/drive/root:/" + encoded_path + ":/content"
    )
    dl_url = base_url + ("?format=pdf" if needs_conversion else "")

    # Step 4: Download (raw bytes — Path A advantage)
    try:
        r = requests.get(
            dl_url,
            headers={"Authorization": "Bearer " + graph_token},
            timeout=DOWNLOAD_TIMEOUT,
            allow_redirects=True,  # Graph format=pdf returns 302 to CDN
        )
        r.raise_for_status()
        pdf_bytes = r.content
    except Exception as e:
        # Redact graph_token from error if present
        err_msg = str(e)[:300]
        if graph_token and graph_token in err_msg:
            err_msg = err_msg.replace(graph_token, "[TOKEN REDACTED]")
        result["error"] = "Graph download failed: " + err_msg
        return result

    if not pdf_bytes or len(pdf_bytes) < 100:
        result["error"] = "Downloaded content too small (" + str(len(pdf_bytes)) + " bytes)"
        return result

    # Verify PDF magic — even for ?format=pdf the result must be %PDF
    if not pdf_bytes.startswith(b"%PDF"):
        result["error"] = (
            "Not a valid PDF (first 8 bytes: "
            + pdf_bytes[:8].hex()
            + ") — Graph conversion may have failed silently"
        )
        return result

    result["size_bytes"] = len(pdf_bytes)

    # Step 5: Prepare Gemini filename — strip Office ext, append .pdf if converted
    display_name = filename
    if needs_conversion and "." in display_name:
        display_name = display_name.rsplit(".", 1)[0] + ".pdf"
    header_name = _ascii_safe_header(display_name)
    result["name"] = header_name
    result["display_name"] = display_name

    # Step 6: Upload to Gemini Files API
    try:
        gem_resp = requests.post(
            "https://generativelanguage.googleapis.com/upload/v1beta/files",
            data=pdf_bytes,
            headers={
                "x-goog-api-key": gemini_api_key,
                "X-Goog-Upload-Protocol": "raw",
                "X-Goog-Upload-File-Name": header_name,
                "Content-Type": "application/pdf",
            },
            timeout=UPLOAD_TIMEOUT,
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
        result["mime_type"] = "application/pdf"
    except Exception as e:
        # Redact gemini_api_key from error
        err_msg = str(e)[:300]
        if gemini_api_key and gemini_api_key in err_msg:
            err_msg = err_msg.replace(gemini_api_key, "[KEY REDACTED]")
        result["error"] = "Gemini upload failed: " + err_msg
        return result

    # Step 7: Wait for ACTIVE state (race condition fix)
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
