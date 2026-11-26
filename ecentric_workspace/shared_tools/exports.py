# Copyright (c) 2026, eCentric and contributors
"""File xuat tu Kalodata: keo tu may 24/7 ve ERP, tai xuong, xoa sau 7 ngay.

Huong keo (ERP hoi may 24/7), khong co endpoint guest nao tren ERP. File gan cho nguoi giu luot
luc xuat (agent tren may ghi email tu lenh /grant). Chi luu tren ERP xong (commit) moi xoa ben may.
"""
import datetime as dt
import re
import time

import frappe
from frappe.utils import add_days, now_datetime

from ecentric_workspace.shared_tools import broker_client as B
from ecentric_workspace.shared_tools import constants as C
from ecentric_workspace.shared_tools import queue_rules as Q
from ecentric_workspace.shared_tools import repository as R
from ecentric_workspace.shared_tools import service as S

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
_NAME_RE = re.compile(r"[^\w.\- ]+", re.UNICODE)
MAX_PER_SYNC = 20


def safe_file_name(name, export_id):
    base = _NAME_RE.sub("_", (name or "").strip())[-120:].strip("._ ")
    return base or ("kalodata_%s.csv" % export_id)


def sync(key, host=None):
    """Keo file moi ve. host: trang thai vua hoi (bo qua neu may bao khong co file cho)."""
    if not B.configured():
        return 0
    if host is not None and not (host.get("ok") and int(host.get("exports_pending") or 0)):
        return 0
    try:
        items = B.exports()
    except B.HostDown:
        return 0
    done = 0
    for meta in items[:MAX_PER_SYNC]:
        eid = str(meta.get("export_id") or "")
        if not _ID_RE.match(eid):
            continue
        try:
            if not R.export_exists(eid):
                if not _pull(key, eid):
                    continue
                done += 1
            B.export_delete(eid)
        except Exception:
            R.rollback()
            frappe.log_error(title="shared_tools export sync %s" % eid)
    if done:
        R.publish_changed(key)
    return done


def _pull(key, eid):
    content, meta = B.export_get(eid)
    user = (meta.get("user") or "").strip()
    if not user or not R.user_exists(user):
        # Xuat khi khong co ai giu luot (khong nen xay ra: agent tu choi) -> giu tren may, bao loi.
        frappe.log_error(title="shared_tools export khong ro nguoi", message="export_id=%s" % eid)
        return False
    # created_at la giay unix; quy ve gio he thong ERP bang do lech so voi bay gio (server co the chay UTC).
    age = max(time.time() - float(meta.get("created_at") or time.time()), 0)
    at = now_datetime() - dt.timedelta(seconds=int(age))
    source = meta.get("source") if meta.get("source") in C.EXPORT_SOURCE_LABELS else "extension"
    values = {"tool": key, "user": user, "entry": R.entry_of_user_at(key, user, at), "export_id": eid,
              "source": source, "file_name": safe_file_name(meta.get("file_name"), eid),
              "exported_at": at, "rows": meta.get("rows"), "columns": meta.get("columns"),
              "pages": meta.get("pages"), "page_title": (meta.get("page_title") or "")[:140],
              "page_url": (meta.get("page_url") or "")[:500]}
    name = R.save_export(values, content)
    R.log(key, C.EV_EXPORT, user=user, entry=values["entry"],
          detail={"export": name, "rows": values["rows"], "source": source})
    R.commit()
    return True


def download(ctx, name):
    """(file_name, bytes) neu ctx la nguoi xuat hoac quan ly; khong thi QueueError."""
    row = R.export_by_name(name)
    if not row:
        raise Q.QueueError("File không còn (đã quá %d ngày)." % C.EXPORT_KEEP_DAYS)
    if row.user != ctx.user and not ctx.is_manager:
        raise Q.QueueError("File này của người khác.")
    S.load_tool(ctx, row.tool)
    content = R.file_content(row.file_url) if row.file_url else None
    if content is None:
        raise Q.QueueError("Không đọc được file trên ERP.")
    if not row.downloaded_at:
        R.mark_downloaded(name, now_datetime())
    R.log(row.tool, C.EV_DOWNLOAD, user=ctx.user, detail={"export": name})
    R.commit()
    return row.file_name, content


def purge():
    n = 0
    for name in R.old_exports(add_days(now_datetime(), -C.EXPORT_KEEP_DAYS)):
        try:
            R.delete_export(name)
            R.commit()
            n += 1
        except Exception:
            R.rollback()
            frappe.log_error(title="shared_tools export purge %s" % name)
    return n
