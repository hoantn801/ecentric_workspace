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

# webUrl prefixes that mark a direct document-library path.
_DIRECT_PREFIXES = (
    "/sites/operation/Shared%20Documents/",
    "/sites/operation/Shared Documents/",
)


class GraphError(Exception):
    """Raised when Microsoft Graph rejects a deck operation."""


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
    resp.raise_for_status()
    token = (resp.json() or {}).get("access_token")
    if not token:
        raise GraphError("Graph did not return an access token")
    return token


def build_deck_path(week_label, emp_code, dept_clean, filename):
    safe = (filename or "deck.pdf").replace("/", "_").replace("\\", "_").lstrip(".")
    return "{0}/{1}/{2}_{3}_{4}".format(
        DECK_ROOT, dept_clean or "Unknown", week_label, emp_code or "unknown", safe
    )


def _item_url(rel_path):
    # quote() encodes %, space and & in one pass, so it cannot hit the
    # replace-ordering double-encode bug recorded in A46.
    return GRAPH + "/sites/" + SITE_ID + "/drive/root:/" + quote(rel_path, safe="/")


def create_deck_upload_session(rel_path, filename, token):
    resp = requests.post(
        _item_url(rel_path) + ":/createUploadSession",
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json={"item": {"@microsoft.graph.conflictBehavior": "replace", "name": filename}},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    url = (resp.json() or {}).get("uploadUrl")
    if not url:
        raise GraphError("Graph did not return an uploadUrl")
    return url


def rel_path_from_web_url(web_url):
    """Direct-path webUrl -> library-relative path, or "" when not parseable.

    NOTE: gemini_api._extract_rel_path solves the same problem for the Gemini
    path (and also handles _layouts viewer URLs). Second user of this rule --
    per the promote rule it should move to a shared util next time either side
    is touched.
    """
    for prefix in _DIRECT_PREFIXES:
        idx = (web_url or "").find(prefix)
        if idx >= 0:
            tail = web_url[idx + len(prefix):]
            for sep in ("?", "#"):
                if sep in tail:
                    tail = tail.split(sep, 1)[0]
            return unquote(tail)
    return ""


def delete_by_web_url(web_url, token):
    rel_path = rel_path_from_web_url(web_url)
    if not rel_path:
        return False
    resp = requests.delete(
        _item_url(rel_path),
        headers={"Authorization": "Bearer " + token},
        timeout=TIMEOUT,
    )
    # 404 means it is already gone -- same desired end state as 204.
    return resp.status_code in (200, 204, 404)
