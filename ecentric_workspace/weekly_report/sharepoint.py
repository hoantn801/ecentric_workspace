# Copyright (c) 2026, eCentric and contributors
"""Graph helpers for weekly-report deck files.

A48: binary / outbound HTTP lives in the installed app, never in a Server
Script sandbox. A21: the deck bytes are PUT to SharePoint by the BROWSER via an
upload session -- they never pass through this server, so submit stays ~1-2s.

Public API:
  get_app_token() -> str
      App-only client_credentials token from Social Login Key "microsoft".

  build_deck_path(week_label, emp_code, dept_clean, filename) -> str
      "Weekly Reports/<dept>/<week>_<emp>_<file>" (NOT url-encoded).

  create_deck_upload_session(rel_path, filename, token) -> str
      Graph upload URL for the browser to PUT the file to.

  delete_by_web_url(web_url, token) -> bool
      Removes a deck the user deleted from the form. True when gone.
"""

import frappe
import requests
from frappe.utils import add_days, nowdate
from urllib.parse import quote, unquote


# SharePoint site backing /weekly-update decks. Not a secret -- same identifier
# the legacy submit_weekly_update Server Script used.
SITE_ID = (
    "boxmeglobal.sharepoint.com,c8988716-77c2-43e2-ad13-f420fdaeacee,"
    "3c357dd3-d1f7-4928-94d3-bca1ea0104a9"
)
GRAPH = "https://graph.microsoft.com/v1.0"
DECK_ROOT = "Weekly Reports"
TIMEOUT = 30

# SharePoint's illegal set, plus # and % which break URL path addressing.
ILLEGAL_NAME_CHARS = '"*:<>?/\\|#%'

# webUrl prefixes that mark a direct document-library path.
_DIRECT_PREFIXES = (
    "/sites/operation/Shared%20Documents/",
    "/sites/operation/Shared Documents/",
)


class GraphError(Exception):
    """Raised when Microsoft Graph rejects a deck operation."""


def _check(resp, what):
    """raise_for_status() hides Graph's body, which is where the real reason is
    ("invalidRequest", "itemNotFound", "nameAlreadyExists"...). Keep it."""
    if resp.status_code >= 400:
        raise GraphError(
            "{0} failed: HTTP {1} {2}".format(what, resp.status_code, (resp.text or "")[:400])
        )
    return resp


def get_app_token():
    sso = frappe.get_doc("Social Login Key", "microsoft")
    tenant = (sso.base_url or "").rstrip("/").split("/")[-1]
    resp = requests.post(
        "https://login.microsoftonline.com/" + tenant + "/oauth2/v2.0/token",
        data={
            "grant_type": "client_credentials",
            "client_id": sso.client_id,
            "client_secret": sso.get_password("client_secret", raise_exception=False),
            "scope": "https://graph.microsoft.com/.default",
        },
        timeout=TIMEOUT,
    )
    _check(resp, "token")
    token = (resp.json() or {}).get("access_token")
    if not token:
        raise GraphError("Graph did not return an access token")
    return token


def safe_filename(filename):
    """Strip everything SharePoint refuses in a file name.

    Beyond the documented illegal set, a colon is especially damaging here:
    Graph addresses items as root:/{path}:/{action}, so a ':' inside the path
    breaks the delimiters and the call fails with a 500. A real upload named
    "Bao cao tuan 11:9.pdf" did exactly that. SharePoint also silently rejects
    trailing spaces and dots.
    """
    name = filename or "deck.pdf"
    cleaned = []
    for ch in name:
        cleaned.append("_" if ch in ILLEGAL_NAME_CHARS else ch)
    name = "".join(cleaned).strip().strip(".").strip()
    return name or "deck.pdf"


def build_deck_path(week_label, emp_code, dept_clean, filename):
    return "{0}/{1}/{2}_{3}_{4}".format(
        DECK_ROOT,
        dept_clean or "Unknown",
        week_label,
        emp_code or "unknown",
        safe_filename(filename),
    )


def _item_url(rel_path):
    # quote() encodes %, space and & in one pass, so it cannot hit the
    # replace-ordering double-encode bug recorded in A46.
    return GRAPH + "/sites/" + SITE_ID + "/drive/root:/" + quote(rel_path, safe="/")


def create_deck_upload_session(rel_path, token):
    # Do NOT send item.name: rel_path already ends with the final (prefixed)
    # filename, and a differing item.name makes Graph answer 400 invalidRequest.
    resp = requests.post(
        _item_url(rel_path) + ":/createUploadSession",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
        timeout=TIMEOUT,
    )
    _check(resp, "createUploadSession " + rel_path)
    url = (resp.json() or {}).get("uploadUrl")
    if not url:
        raise GraphError("Graph did not return an uploadUrl")
    return url


def dept_clean(department):
    """"Media - EC" -> "Media". Folder names on SharePoint drop the abbr."""
    dept = department or "Unknown"
    return dept.rsplit(" - ", 1)[0] if " - " in dept else dept


def rel_path_from_web_url(web_url, department=""):
    """webUrl -> library-relative path, or "" when it cannot be trusted.

    Two shapes reach us, and which one you get depends on the FILE TYPE:
      - PDF    -> direct path  .../Shared Documents/Weekly Reports/<dept>/<f>
      - Office -> viewer URL   .../_layouts/15/Doc.aspx?sourcedoc={G}&file=<f>
    The viewer URL carries no folder, so the department must be supplied to
    rebuild the path. Without it we return "" rather than guess -- a wrong path
    would make callers delete or re-share the wrong item.

    NOTE: gemini_api._extract_rel_path implements the same two cases. Third user
    of this rule; consolidate into a shared util next time either is touched.
    """
    url = web_url or ""
    for prefix in _DIRECT_PREFIXES:
        idx = url.find(prefix)
        if idx >= 0:
            tail = url[idx + len(prefix):]
            for sep in ("?", "#"):
                if sep in tail:
                    tail = tail.split(sep, 1)[0]
            return unquote(tail)

    if "_layouts/" in url and "file=" in url:
        folder = dept_clean(department) if department else ""
        if not folder:
            return ""
        tail = url[url.find("file=") + 5:]
        if "&" in tail:
            tail = tail.split("&", 1)[0]
        fname = unquote(tail)
        if fname:
            return "{0}/{1}/{2}".format(DECK_ROOT, folder, fname)
    return ""


def create_org_link(rel_path, token, days=365):
    """Organisation-scope view link: any signed-in tenant account can open it,
    regardless of permissions on the `operation` site. Not public."""
    resp = requests.post(
        _item_url(rel_path) + ":/createLink",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json={
            "type": "view",
            "scope": "organization",
            "expirationDateTime": add_days(nowdate(), days) + "T23:59:59Z",
        },
        timeout=TIMEOUT,
    )
    _check(resp, "createLink " + rel_path)
    link = (resp.json() or {}).get("link") or {}
    url = link.get("webUrl")
    if not url:
        raise GraphError("createLink returned no webUrl for " + rel_path)
    return url


def delete_by_web_url(web_url, token, department=""):
    rel_path = rel_path_from_web_url(web_url, department)
    if not rel_path:
        return False
    resp = requests.delete(
        _item_url(rel_path),
        headers={"Authorization": "Bearer " + token},
        timeout=TIMEOUT,
    )
    # 404 means it is already gone -- same desired end state as 204.
    return resp.status_code in (200, 204, 404)
