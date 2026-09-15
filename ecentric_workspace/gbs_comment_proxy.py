"""
ecentric_workspace/gbs_comment_proxy.py — GBS comment image proxy (Path A).

Why this file exists:
  Frappe Server Script (RestrictedPython sandbox) cannot:
    - `import requests`
    - Access `response.content` (raw bytes) — Frappe's `make_get_request` always JSON-parses
      or returns `response.text` (str, UTF-8 lossy — 0x89 PNG magic byte becomes 0xef 0xbf 0xbd)
    - Access `frappe.integrations.utils.get_request_session()` (returns None in sandbox)
  Path A: this module runs in normal Python (no sandbox), full requests library available.

Use cases:
  1. proxy_boxme_file:      browser GET /api/method/....proxy_boxme_file?path=/private/files/xxx.png?fid=abc
                            → server fetches from boxme with auth → streams binary back with correct
                            Content-Type. Used by approval-page timeline to render <img> embedded in
                            boxme comments (Nina's paste-image use case, 2026-07-06).
  2. upload_image_to_boxme: frontend paste image → base64 → this method → POST multipart to boxme's
                            /api/method/upload_file → returns boxme /private/files/xxx URL. Used by
                            approval-page comment box paste handler so eCentric users can send images
                            to boxme.

Access paths (whitelisted, session cookie or API token both work):
  GET  /api/method/ecentric_workspace.gbs_comment_proxy.proxy_boxme_file?path=<encoded_path>
  POST /api/method/ecentric_workspace.gbs_comment_proxy.upload_image_to_boxme  (JSON body)

Auth model:
  - Both methods reject Guest (require eCentric session).
  - Server-side uses GBS Settings.api_key / api_secret to authenticate to boxme.
  - Credentials NEVER leak to client — client only sees the eCentric proxy URL.

Related:
  - gbs_fetch_comments Server Script: on incoming boxme comment, rewrites <img src="/private/files/*">
    → <img src="/api/method/ecentric_workspace.gbs_comment_proxy.proxy_boxme_file?path=...">
  - gbs_post_comment Server Script: allows img HTML in comment content (v6→v7).
  - approval-page main_section: timeline renders comment content as HTML (allowlist img/br/p/span).

Created: 2026-07-06 for GBS comment image sync (Nina paste-image bug + eCentric can't send images).
"""

import base64
import binascii

import frappe
import requests


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

FETCH_TIMEOUT = 30   # seconds when fetching binary file from boxme
UPLOAD_TIMEOUT = 60  # seconds when POSTing multipart to boxme /api/method/upload_file
MAX_UPLOAD_MB = 10   # cap paste-image size to avoid abuse (10 MB)

# Content-Type detection by extension (browsers use this to decide <img> vs download)
_EXT_TO_CTYPE = {
    ".png":  "image/png",
    ".jpg":  "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif":  "image/gif",
    ".webp": "image/webp",
    ".svg":  "image/svg+xml",
    ".bmp":  "image/bmp",
    ".ico":  "image/x-icon",
    ".pdf":  "application/pdf",
}


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_gbs_credentials():
    """Read GBS Settings singleton. Returns (base_url, key, secret). Raises if not configured."""
    gbs = frappe.get_doc("GBS Settings", "GBS Settings")
    base = (gbs.api_base_url or "").rstrip("/")
    key = gbs.api_key or ""
    secret = ""
    try:
        secret = gbs.get_password("api_secret") or ""
    except Exception:
        # Fallback to raw password field on older schemas
        try:
            secret = frappe.utils.password.get_decrypted_password(
                "GBS Settings", "GBS Settings", "api_secret", raise_exception=False
            ) or ""
        except Exception:
            secret = ""
    if not (base and key and secret):
        frappe.throw("GBS Settings not fully configured (api_base_url / api_key / api_secret missing)")
    return base, key, secret


def _detect_content_type(path_or_filename):
    """Return image MIME type based on file extension. Defaults to application/octet-stream."""
    # Strip query string and lowercase
    stem = path_or_filename.split("?", 1)[0].lower()
    for ext, ctype in _EXT_TO_CTYPE.items():
        if stem.endswith(ext):
            return ctype
    return "application/octet-stream"


def _extract_filename(path):
    """Extract filename from a URL path. Falls back to 'file'."""
    stem = path.split("?", 1)[0]
    if "/" in stem:
        stem = stem.rsplit("/", 1)[-1]
    return stem or "file"


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

@frappe.whitelist()
def proxy_boxme_file(path=None):
    """Proxy a boxme /private/files/<file> URL through eCentric auth.

    HTTP flow:
      Browser: <img src="/api/method/ecentric_workspace.gbs_comment_proxy.proxy_boxme_file?path=/private/files/xxx.png?fid=abc">
      Frappe:  routes to this method (session cookie required)
      Server:  GET https://team.boxme.asia/private/files/xxx.png?fid=abc with token auth
      Server:  streams response bytes back with correct Content-Type
      Browser: renders as inline image

    Args:
      path: boxme relative path (must start with '/private/files/'). Query string preserved
            (needed for boxme's per-file access token '?fid=...').

    Auth: requires eCentric session (rejects Guest).

    Returns: None (Frappe sends binary response directly via frappe.local.response).

    Raises: frappe.PermissionError / frappe.ValidationError on unauthorized or malformed input.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw("Unauthorized", frappe.PermissionError)

    if not path:
        frappe.throw("Missing 'path' parameter")

    # Whitelist: only proxy Frappe's private file store. Prevents arbitrary URL fetch abuse.
    if not path.startswith("/private/files/"):
        frappe.throw("Invalid path: must start with /private/files/")

    base, key, secret = _get_gbs_credentials()
    url = base + path
    headers = {
        "Authorization": "token " + key + ":" + secret,
        "Accept": "*/*",
    }

    try:
        r = requests.get(url, headers=headers, timeout=FETCH_TIMEOUT, allow_redirects=True)
        r.raise_for_status()
    except requests.HTTPError as e:
        # Convert boxme's HTTP error to a Frappe error the caller can display
        code = getattr(e.response, "status_code", 0) if e.response is not None else 0
        frappe.throw("boxme fetch failed (HTTP " + str(code) + "): " + str(e)[:200])
    except Exception as e:
        frappe.throw("boxme fetch failed: " + str(e)[:200])

    content_bytes = r.content or b""
    if not content_bytes:
        frappe.throw("boxme returned empty body")

    filename = _extract_filename(path)
    # Prefer server-declared Content-Type, fall back to extension-based detection.
    ctype = r.headers.get("Content-Type", "").split(";", 1)[0].strip() or _detect_content_type(filename)

    # Frappe "binary" response type: sends raw bytes with the given mimetype + inline disposition.
    # Confirmed browser <img> can render this since Content-Type is image/*.
    frappe.local.response.filename = filename
    frappe.local.response.filecontent = content_bytes
    frappe.local.response.type = "binary"
    frappe.local.response.mimetype = ctype
    return


@frappe.whitelist()
def upload_image_to_boxme(base64_data=None, filename=None, doctype=None, docname=None):
    """Upload a paste-image to boxme's File doctype, return the boxme file URL.

    Flow:
      Frontend: user pastes image into approval-page comment box → clipboardData.items[i].getAsBlob()
                → FileReader.readAsDataURL → "data:image/png;base64,AAAA..."
      Frontend: POST /api/method/ecentric_workspace.gbs_comment_proxy.upload_image_to_boxme
                {base64_data, filename?, doctype?, docname?}
      Server:   decode base64 → POST multipart to boxme /api/method/upload_file
      Server:   returns {success, file_url: '/private/files/abcd.png', proxy_url: '/api/method/....?path=...'}
      Frontend: inserts <img src="{proxy_url}"> into comment box (or content on send)
                and stores {file_url} to include as the actual boxme <img src> when the
                comment is posted so boxme users see it inline.

    Args:
      base64_data: 'data:image/png;base64,AAAA...' (data URL) OR raw base64 string.
      filename:    optional. Defaults to 'pasted_image.<ext>'.
      doctype:     optional — associates the boxme File record with a boxme DocType for permissions.
      docname:     optional — the record name (e.g., boxme SAL-ORD-2026-00554).

    Auth: requires eCentric session (rejects Guest).

    Returns:
      {
        "success":   True/False,
        "file_url":  boxme relative path e.g. '/private/files/hAbCdEf.png' (use as <img src> when posting comment),
        "proxy_url": eCentric proxy URL for local preview e.g. '/api/method/....?path=...',
        "filename":  final filename used,
        "size_bytes": upload size,
        "error":     error message if success=False
      }
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw("Unauthorized", frappe.PermissionError)

    if not base64_data:
        frappe.throw("Missing 'base64_data' parameter")

    # Accept data URL prefix "data:image/png;base64,AAAA..." OR raw base64.
    ctype_hint = ""
    if base64_data.startswith("data:"):
        try:
            header, base64_data = base64_data.split(",", 1)
            # header e.g. "data:image/png;base64"
            if ":" in header and ";" in header:
                ctype_hint = header.split(":", 1)[1].split(";", 1)[0].strip()
        except Exception:
            frappe.throw("Malformed data URL")

    # Decode base64 → binary
    try:
        binary = base64.b64decode(base64_data, validate=False)
    except (binascii.Error, ValueError) as e:
        frappe.throw("Invalid base64 payload: " + str(e)[:100])

    size = len(binary)
    if size == 0:
        frappe.throw("Empty binary after decode")
    if size > MAX_UPLOAD_MB * 1024 * 1024:
        frappe.throw("Image too large (" + str(size // 1024) + " KB > " + str(MAX_UPLOAD_MB) + " MB cap)")

    # Determine filename + content type
    if not filename:
        # Extension by ctype hint from data URL
        ext_map = {"image/png": ".png", "image/jpeg": ".jpg", "image/gif": ".gif",
                   "image/webp": ".webp", "image/svg+xml": ".svg"}
        ext = ext_map.get(ctype_hint, ".png")
        filename = "pasted_image" + ext
    ctype = ctype_hint or _detect_content_type(filename)

    # Upload to boxme /api/method/upload_file
    base, key, secret = _get_gbs_credentials()
    url = base + "/api/method/upload_file"
    headers = {
        "Authorization": "token " + key + ":" + secret,
        # No Content-Type here — requests will set correct multipart boundary
    }
    files = {"file": (filename, binary, ctype)}
    # Frappe upload_file accepts these form fields. is_private=1 keeps file behind /private/files/*.
    # optimize=0 preserves original bytes (Frappe otherwise re-compresses images).
    data = {"is_private": "1", "folder": "Home", "optimize": "0"}
    if doctype and docname:
        data["doctype"] = doctype
        data["docname"] = docname

    try:
        r = requests.post(url, headers=headers, files=files, data=data, timeout=UPLOAD_TIMEOUT)
        r.raise_for_status()
        resp_json = r.json()
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", 0) if e.response is not None else 0
        body_head = ""
        try:
            body_head = e.response.text[:200] if e.response is not None else ""
        except Exception:
            pass
        return {"success": False, "error": "boxme upload HTTP " + str(code) + ": " + body_head}
    except Exception as e:
        return {"success": False, "error": "boxme upload failed: " + str(e)[:200]}

    # Frappe's upload_file returns {"message": {"file_url": "...", "file_name": "...", ...}}
    msg = resp_json.get("message") or {}
    file_url = msg.get("file_url") or ""
    if not file_url:
        return {"success": False, "error": "boxme did not return file_url. Resp head: " + str(resp_json)[:200]}

    proxy_url = "/api/method/ecentric_workspace.gbs_comment_proxy.proxy_boxme_file?path=" + file_url

    return {
        "success": True,
        "file_url": file_url,
        "proxy_url": proxy_url,
        "filename": msg.get("file_name") or filename,
        "size_bytes": size,
    }
# ─────────────────────────────────────────────────────────────────────────────
# Boxme docinfo fetch (added 2026-09-15 — incident: site down 10:35–10:47)
#
# Why this exists:
#   Server Script `gbs_fetch_comments` used frappe.make_get_request() to pull
#   comments from boxme. That helper has NO `timeout` parameter (frappe v16
#   integrations/utils.make_request -> session.request(...) without timeout), so
#   when boxme stopped responding on 2026-09-15 each call held a gunicorn worker
#   until the proxy killed it (~129s average, 516s in one 5-minute bucket).
#   Four such calls saturated every worker and the whole site went down.
#
#   This module runs outside the sandbox, so it can pass a real timeout and keep
#   a circuit breaker. Contract with the Server Script: return
#   {"success": True, "boxme_name": str, "docinfo": {...}} or raise.
# ─────────────────────────────────────────────────────────────────────────────

GETDOC_CONNECT_TIMEOUT = 5    # seconds to establish the TCP/TLS connection to boxme
GETDOC_READ_TIMEOUT = 20      # seconds to wait for boxme's response body
BREAKER_KEY = "gbs_docinfo_breaker"
BREAKER_THRESHOLD = 3         # consecutive failures before the breaker opens
BREAKER_COOLDOWN = 60         # seconds the breaker stays open

# Keys of frappe.desk.form.load.getdoc's docinfo that gbs_fetch_comments renders.
DOCINFO_KEYS = ("comments", "workflow_logs", "info_logs")


def _breaker_failures():
    """Consecutive boxme failures recorded in the current cooldown window."""
    try:
        return int(frappe.cache().get_value(BREAKER_KEY) or 0)
    except Exception:
        return 0


def _breaker_record_failure():
    """Count one failure; the key expires on its own after BREAKER_COOLDOWN."""
    fails = _breaker_failures() + 1
    try:
        frappe.cache().set_value(BREAKER_KEY, fails, expires_in_sec=BREAKER_COOLDOWN)
    except Exception:
        pass
    return fails


def _breaker_reset():
    """Boxme answered — forget the failure streak."""
    try:
        frappe.cache().delete_value(BREAKER_KEY)
    except Exception:
        pass


def _boxme_doc_name(doctype, name):
    """Resolve the boxme-side docname for a local GBS record (falls back to `name`)."""
    try:
        local_doc = frappe.get_doc(doctype, name)
        linked = (local_doc.get("gbs_doc_name")
                  or local_doc.get("gbs_id")
                  or local_doc.get("link_id") or "")
    except Exception:
        linked = ""
    return linked or name


@frappe.whitelist()
def fetch_boxme_docinfo(doctype=None, name=None):
    """Fetch a boxme document's docinfo (comments / workflow logs / info logs).

    Replaces the untimed frappe.make_get_request() call inside the
    `gbs_fetch_comments` Server Script. Two protections the sandbox cannot give:

      1. Hard timeout — (connect 5s, read 20s). A hung boxme frees the worker in
         at most ~25s instead of holding it until the proxy timeout.
      2. Circuit breaker — after BREAKER_THRESHOLD consecutive failures every
         further call fails instantly for BREAKER_COOLDOWN seconds, so a boxme
         outage can no longer pile requests up on the workers.

    Args:
      doctype: local DocType, e.g. 'GBS Sales Order'.
      name:    local docname.

    Auth: requires an eCentric session (rejects Guest).

    Returns:
      {"success": True, "boxme_name": str, "boxme_dtype": str, "docinfo": {
          "comments": [...], "workflow_logs": [...], "info_logs": [...]}}

    Raises: frappe.ValidationError when boxme is unreachable, times out, or
      answers with a non-2xx status. The caller's existing try/except turns that
      into {"success": False, "error": ...}, which the timeline already handles.
    """
    if not frappe.session.user or frappe.session.user == "Guest":
        frappe.throw("Unauthorized", frappe.PermissionError)
    if not doctype or not name:
        frappe.throw("Missing 'doctype'/'name' parameter")

    boxme_name = _boxme_doc_name(doctype, name)
    boxme_dtype = doctype[4:] if doctype.startswith("GBS ") else doctype

    if _breaker_failures() >= BREAKER_THRESHOLD:
        frappe.throw(
            "boxme is not responding (circuit breaker open, retrying in up to "
            + str(BREAKER_COOLDOWN) + "s)"
        )

    base, key, secret = _get_gbs_credentials()
    url = base + "/api/method/frappe.desk.form.load.getdoc"
    headers = {"Authorization": "token " + key + ":" + secret, "Accept": "application/json"}
    params = {"doctype": boxme_dtype, "name": boxme_name}

    try:
        r = requests.get(url, params=params, headers=headers,
                         timeout=(GETDOC_CONNECT_TIMEOUT, GETDOC_READ_TIMEOUT))
        r.raise_for_status()
        payload = r.json()
    except requests.Timeout:
        fails = _breaker_record_failure()
        frappe.throw("boxme timed out after " + str(GETDOC_READ_TIMEOUT)
                     + "s (failure " + str(fails) + ")")
    except requests.HTTPError as e:
        code = getattr(e.response, "status_code", 0) if e.response is not None else 0
        fails = _breaker_record_failure()
        frappe.throw("boxme getdoc HTTP " + str(code) + " (failure " + str(fails) + ")")
    except Exception as e:
        fails = _breaker_record_failure()
        frappe.throw("boxme getdoc failed: " + str(e)[:200]
                     + " (failure " + str(fails) + ")")

    _breaker_reset()

    message = payload.get("message") if isinstance(payload, dict) else None
    container = message if isinstance(message, dict) else payload
    raw = container.get("docinfo") if isinstance(container, dict) else {}
    if not isinstance(raw, dict):
        raw = {}

    docinfo = {}
    for docinfo_key in DOCINFO_KEYS:
        value = raw.get(docinfo_key)
        docinfo[docinfo_key] = value if isinstance(value, list) else []

    return {
        "success": True,
        "boxme_name": boxme_name,
        "boxme_dtype": boxme_dtype,
        "docinfo": docinfo,
    }

