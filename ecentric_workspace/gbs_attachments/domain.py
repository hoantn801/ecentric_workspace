# Copyright (c) 2026, eCentric and contributors
"""Logic thuan (khong frappe, khong HTTP) - test duoc khong can bench."""

import re
from urllib.parse import unquote

from ecentric_workspace.gbs_attachments.constants import SHAREPOINT_HOST_MARK

#: Frappe (ca boxme lan EC) doi ten file khi trung ten tren dia: get_file_name() chen
#: 6 ky tu hex (content_hash[-6:]) ngay TRUOC duoi file, khong co dau noi:
#: "Screenshot_1.png" -> "Screenshot_1a1b2c3.png" (N21b, SO 10-26-00001).
_RENAMED = re.compile(r"^(?P<stem>.+?)[0-9a-f]{6}(?P<ext>\.[^./\\]+)?$")


def split_attachment_urls(raw):
    """`attachment_url` la chuoi phan cach dau phay (quy uoc tu 05/2026)."""
    return [u.strip() for u in (raw or "").split(",") if u.strip()]


def strip_fragment(url):
    """Bo '#ten-file' ma gbs_convert_attachments_to_anon gan vao link an danh."""
    return (url or "").split("#", 1)[0]


def fragment_name(url):
    """Ten file nam sau '#', neu co."""
    if "#" not in (url or ""):
        return ""
    return unquote(url.split("#", 1)[1]).strip()


def is_sharepoint_url(url):
    return SHAREPOINT_HOST_MARK in (url or "").lower()


def is_local_file_url(url):
    """File luu ngay tren site EC (/files/..., /private/files/...)."""
    return (url or "").startswith(("/files/", "/private/files/"))


def strip_rename_suffix(name):
    """"X<6 hex>.ext" -> "X.ext"; ten khong co hau to thi tra nguyen."""
    m = _RENAMED.match(name or "")
    if not m:
        return name or ""
    return m.group("stem") + (m.group("ext") or "")


def present(desired_names, existing_names):
    """Ten nao trong desired_names DA CO trong existing_names (tap ten).

    Khop dung ten truoc; con lai moi khop ten da bi Frappe doi ("X<6 hex>.ext" == "X.ext").
    Moi file co san chi duoc tinh cho MOT ten mong muon, de "Report.pdf" va
    "Report202611.pdf" cung duoc day du khi ben kia moi co mot file.
    """
    pool = [n for n in (existing_names or []) if n]
    found = set()
    for n in desired_names:
        if n in found:
            continue
        if n in pool:
            pool.remove(n)
            found.add(n)
    for n in desired_names:
        if n in found:
            continue
        for e in pool:
            if strip_rename_suffix(e) == n:
                pool.remove(e)
                found.add(n)
                break
    return found


def plan(desired_names, boxme_files, resync, api_user):
    """Tinh viec can lam ben boxme cho MOT phieu.

    desired_names: ten file phai co tren boxme (lay tu attachment_url).
    boxme_files:   [{name, file_name, file_url, owner}] dang gan vao phieu ben boxme.
    resync:        True khi phieu vua "Sua & gui lai" -> thay het file do EC day truoc do.
    api_user:      user ma khoa API cua EC dang dung ben boxme.

    Tra ve {"upload": [ten...], "delete": [file_id...], "keep": [ten...]}.
    Khong bao gio xoa file do nguoi boxme tu dinh kem (owner khac api_user),
    tru link SharePoint - loai nay boxme da tuyen bo khong nhan.
    """
    delete, have = [], []
    for f in boxme_files or []:
        url = f.get("file_url") or ""
        if is_sharepoint_url(url):
            delete.append(f.get("name"))
        elif resync and f.get("owner") == api_user:
            delete.append(f.get("name"))
        else:
            have.append(f.get("file_name") or "")
    found = present(desired_names, have)
    upload, keep, seen = [], [], set()
    for n in desired_names:
        if n in seen:
            continue
        seen.add(n)
        (keep if n in found else upload).append(n)
    return {"upload": upload, "delete": [d for d in delete if d], "keep": keep}
