# Copyright (c) 2026, eCentric and contributors
"""Doc file tu SharePoint qua Microsoft Graph (app-only).

Token: dung lai `weekly_report.sharepoint.get_app_token` (Social Login Key
"microsoft" - cung danh tinh cac Server Script GBS dang dung de tao link).
"""

import base64

import requests

from ecentric_workspace.gbs_attachments import constants as C


class GraphReadError(Exception):
    """Khong doc duoc file tu SharePoint (ly do nam trong message, khong co bi mat)."""


def app_token():
    from ecentric_workspace.weekly_report.sharepoint import get_app_token
    return get_app_token()


def _share_id(url):
    raw = base64.urlsafe_b64encode(url.encode("utf-8")).decode("ascii").rstrip("=")
    return "u!" + raw


def resolve(url, token, http=requests):
    """Link SharePoint (goc hoac an danh) -> {drive_id, item_id, name, size}.

    Thu link da bo '#ten-file' truoc; neu Graph tu choi thi thu nguyen chuoi
    (Server Script v10 tung gui nguyen chuoi va chay duoc).
    """
    from ecentric_workspace.gbs_attachments.domain import strip_fragment
    last = ""
    for candidate in dict.fromkeys([strip_fragment(url), url]):
        r = http.get(C.GRAPH + "/shares/" + _share_id(candidate) + "/driveItem",
                     headers={"Authorization": "Bearer " + token},
                     params={"$select": "id,name,size,parentReference"},
                     timeout=(C.CONNECT_TIMEOUT, 30))
        if r.status_code == 200:
            j = r.json() or {}
            ref = j.get("parentReference") or {}
            if j.get("id") and ref.get("driveId"):
                return {"drive_id": ref["driveId"], "item_id": j["id"],
                        "name": j.get("name") or "", "size": int(j.get("size") or 0)}
        last = "HTTP " + str(r.status_code) + " " + (r.text or "")[:160]
    raise GraphReadError("resolve: " + (last or "khong ro"))


def download(item, token, http=requests):
    """Tai bytes cua driveItem. Graph tra 302 sang URL da ky; requests tu bo header
    Authorization khi doi host nen token khong lot sang may chu luu file."""
    if item.get("size", 0) > C.MAX_FILE_BYTES:
        raise GraphReadError("qua lon: " + str(item["size"] // 1024) + " KB")
    r = http.get(C.GRAPH + "/drives/" + item["drive_id"] + "/items/" + item["item_id"] + "/content",
                 headers={"Authorization": "Bearer " + token},
                 timeout=(C.CONNECT_TIMEOUT, C.READ_TIMEOUT), allow_redirects=True)
    if r.status_code != 200:
        raise GraphReadError("download: HTTP " + str(r.status_code))
    data = r.content or b""
    if not data:
        raise GraphReadError("download: rong")
    if len(data) > C.MAX_FILE_BYTES:
        raise GraphReadError("qua lon: " + str(len(data) // 1024) + " KB")
    return data
