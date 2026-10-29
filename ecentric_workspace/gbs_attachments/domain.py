# Copyright (c) 2026, eCentric and contributors
"""Logic thuan (khong frappe, khong HTTP) - test duoc khong can bench."""

from urllib.parse import unquote

from ecentric_workspace.gbs_attachments.constants import SHAREPOINT_HOST_MARK


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
    delete, have = [], set()
    for f in boxme_files or []:
        url = f.get("file_url") or ""
        if is_sharepoint_url(url):
            delete.append(f.get("name"))
        elif resync and f.get("owner") == api_user:
            delete.append(f.get("name"))
        else:
            have.add(f.get("file_name") or "")
    upload, keep, seen = [], [], set()
    for n in desired_names:
        if n in seen:
            continue
        seen.add(n)
        (keep if n in have else upload).append(n)
    return {"upload": upload, "delete": [d for d in delete if d], "keep": keep}
