# Copyright (c) 2026, eCentric and contributors
"""Chuyen Word (.docx) -> PDF phia server qua Microsoft Graph (PR-J, 24/11/2026).

Vi sao. Tep ky (hop dong / BBNT) sinh tu mau .docx; truoc day nguoi lap phai tai ve, mo Word,
"Luu thanh PDF" roi tai len lai. Frappe Cloud khong co LibreOffice / Word. Graph co san bo chuyen
cua Word Online: tai .docx len mot thu vien SharePoint, doc lai `?format=pdf`, xoa tep tam.
Chu trang 1pt lam moc ky ([[KY_BEN_A]] / [[KY_BEN_B]]) duoc giu nhu khi xuat bang Word.

Token: dung LAI `weekly_report.sharepoint.get_app_token` (app-only client_credentials, bi mat doc
tu Social Login Key "microsoft") - KHONG them bi mat moi.

QUYEN RIENG TU. Tep hop dong KOL / lao dong mang CCCD, STK (PO 17/11: khong dua len thu vien
chung). Vi vay MAC DINH KHONG dung thu vien chung cua site Operation; phai khai site_config
    "ec_docconvert": {"drive_id": "<thu vien han che quyen>", "folder": "_ERP_tam_PDF"}
(hoac "site_id" thay cho "drive_id"). Chi khi khai "allow_default_site": 1 moi dung thu vien mac
dinh cua site Operation (chi nen dung khi thu). Tep tam bi XOA VINH VIEN (permanentDelete - khong
vao thung rac) ngay sau khi chuyen, ke ca khi chuyen hong; xoa hong -> DELETE thuong + Error Log.
KHONG BAO GIO ghi noi dung tep vao log / thong bao loi.
"""
import uuid
from urllib.parse import quote

import frappe

#: Graph: PUT mot lan toi da 4 MB; lon hon dung upload session (khuc la boi so 320 KiB).
SIMPLE_UPLOAD_MAX = 4 * 1024 * 1024
CHUNK = 16 * 327680            # 5 MiB
#: QC PR-J M2: chuyen dong bo trong web request -> gioi han nho + han tong.
MAX_BYTES = 10 * 1024 * 1024
TIMEOUT = 60
#: QC PR-J M1: han TONG cho mot lan chuyen (duoi gunicorn timeout ~120 s).
DEADLINE_SECONDS = 90
#: Tep tam cu hon muc nay trong thu muc tam -> sweep_temp xoa (moi duong hong con lai).
SWEEP_MAX_AGE_MIN = 15
DEFAULT_FOLDER = "_ERP_tam_chuyen_PDF"
CONF_KEY = "ec_docconvert"
TODO_MARKER = "[EC-DOCCONVERT-TEMP]"


class ConvertError(Exception):
    """Loi chuyen doi - thong diep tieng Viet doc duoc, khong chua noi dung tep / token."""


def _http():
    import requests
    return requests


def _sp():
    from ecentric_workspace.weekly_report import sharepoint as wr_sp
    return wr_sp


def _now():
    import time
    return time.monotonic()


def _config():
    conf = frappe.conf.get(CONF_KEY) if hasattr(frappe.conf, "get") else None
    return conf if isinstance(conf, dict) else {}


def is_configured():
    c = _config()
    return bool(c.get("drive_id") or c.get("site_id") or int(c.get("allow_default_site") or 0))


def _base(conf):
    """URL goc cua thu vien (drive) dung lam cho tam. Chua cau hinh -> tu choi (an toan)."""
    graph = _sp().GRAPH
    if conf.get("drive_id"):
        return "%s/drives/%s" % (graph, quote(str(conf["drive_id"]), safe="!-_."))
    if conf.get("site_id"):
        return "%s/sites/%s/drive" % (graph, quote(str(conf["site_id"]), safe=",-_."))
    if int(conf.get("allow_default_site") or 0):
        return "%s/sites/%s/drive" % (graph, _sp().SITE_ID)
    raise ConvertError("Chưa cấu hình thư viện tạm để chuyển PDF (site_config ec_docconvert). "
                       "Liên hệ quản trị hệ thống.")


def _folder(conf):
    return str(conf.get("folder") or DEFAULT_FOLDER).strip().strip("/") or DEFAULT_FOLDER


def _code(resp):
    try:
        return int(getattr(resp, "status_code", 0) or 0)
    except Exception:
        return 0


def _check(resp, what):
    code = _code(resp)
    if code == 0 or code >= 400:
        raise ConvertError("Chuyển PDF thất bại ở bước %s (HTTP %s) - thử lại sau." % (what, code))
    return resp


def _json(resp):
    try:
        return resp.json() or {}
    except Exception:
        return {}


class _Clock(object):
    """Han tong: moi lenh lay timeout = min(TIMEOUT, thoi gian con lai); het -> ConvertError."""

    def __init__(self, seconds):
        self.end = _now() + seconds

    def left(self):
        rest = self.end - _now()
        if rest <= 1:
            raise ConvertError("Chuyển PDF quá lâu (Microsoft 365 phản hồi chậm) - thử lại sau.")
        return min(TIMEOUT, rest)


def _token():
    try:
        return _sp().get_app_token()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "docconvert token")
        raise ConvertError("Không lấy được quyền truy cập Microsoft 365 - thử lại sau.")


def docx_to_pdf(content, filename=None, http=None, token=None, deadline=None):
    """bytes .docx -> bytes PDF. Nem ConvertError (tieng Viet) khi khong chuyen duoc.

    `http` (mac dinh module requests) va `token` de test tiem vao; code that khong truyen.
    Tep tam LUON duoc don: co ma tep -> xoa theo ma; chua co ma (tra loi mat / thieu id) ->
    xoa theo DUONG DAN; phien tai lon hong -> huy phien (DELETE uploadUrl). Con sot (worker bi
    giet) -> sweep_temp."""
    content = bytes(content or b"")
    if not content:
        raise ConvertError("Tệp Word rỗng.")
    if content[:2] != b"PK":
        raise ConvertError("Tệp không phải Word .docx hợp lệ.")
    if len(content) > MAX_BYTES:
        raise ConvertError("Tệp Word quá lớn để chuyển PDF (tối đa 10 MB).")
    conf = _config()
    base = _base(conf)
    clock = _Clock(DEADLINE_SECONDS if deadline is None else deadline)
    http = http or _http()
    if token is None:
        token = _token()
    auth = {"Authorization": "Bearer %s" % token}
    # Ten tep tam ngau nhien: khong lo ten hop dong / ten doi tac len SharePoint.
    path = quote("%s/%s.docx" % (_folder(conf), uuid.uuid4().hex), safe="/")
    item_id, upload_url, touched = None, None, False
    try:
        try:
            if len(content) <= SIMPLE_UPLOAD_MAX:
                touched = True
                resp = _check(http.put("%s/root:/%s:/content" % (base, path), data=content,
                                       headers=dict(auth, **{"Content-Type":
                                                             "application/octet-stream"}),
                                       timeout=clock.left()), "tải lên")
                item_id = _json(resp).get("id")
            else:
                sess = _check(http.post("%s/root:/%s:/createUploadSession" % (base, path),
                                        json={"item": {"@microsoft.graph.conflictBehavior":
                                                       "fail"}},
                                        headers=auth, timeout=clock.left()), "mở phiên tải lên")
                upload_url = _json(sess).get("uploadUrl")
                if not upload_url:
                    raise ConvertError("Chuyển PDF thất bại: không mở được phiên tải lên.")
                touched = True
                total, start, last = len(content), 0, None
                while start < total:
                    end = min(start + CHUNK, total) - 1
                    # uploadUrl da mang quyen - KHONG gui kem Authorization (tai lieu Graph).
                    last = _check(http.put(upload_url, data=content[start:end + 1],
                                           headers={"Content-Range": "bytes %d-%d/%d"
                                                    % (start, end, total)},
                                           timeout=clock.left()), "tải lên")
                    start = end + 1
                item_id = _json(last).get("id") if last is not None else None
                if item_id:
                    upload_url = None             # phien da ket thuc thanh tep
        except ConvertError:
            raise
        except Exception:
            frappe.log_error(frappe.get_traceback(), "docconvert upload")
            raise ConvertError("Chuyển PDF thất bại: không tải được tệp lên Microsoft 365.")
        if not item_id:
            raise ConvertError("Chuyển PDF thất bại: Microsoft 365 không trả mã tệp.")
        try:
            # Graph tra 302 toi URL tai ve da ky san -> requests tu theo (allow_redirects).
            resp = _check(http.get("%s/items/%s/content?format=pdf" % (base, item_id),
                                   headers=auth, timeout=clock.left(), allow_redirects=True),
                          "chuyển đổi")
        except ConvertError:
            raise
        except Exception:
            frappe.log_error(frappe.get_traceback(), "docconvert convert")
            raise ConvertError("Chuyển PDF thất bại: Microsoft 365 không phản hồi - thử lại sau.")
        pdf = bytes(getattr(resp, "content", b"") or b"")
        if len(pdf) > 4 * MAX_BYTES:
            raise ConvertError("Chuyển PDF thất bại: kết quả quá lớn.")
        if pdf[:4] != b"%PDF":
            raise ConvertError("Chuyển PDF thất bại: kết quả trả về không phải PDF.")
        return pdf
    finally:
        if upload_url:
            _cancel_session(http, upload_url)
        if item_id:
            _delete(http, "%s/items/%s" % (base, item_id), auth, item_id)
        elif touched:
            _delete(http, "%s/root:/%s:" % (base, path), auth, path)


def _cancel_session(http, upload_url):
    try:
        http.delete(upload_url, timeout=20)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "docconvert cancel upload session")


def _delete(http, item_url, auth, label):
    """Xoa VINH VIEN tep tam (khong de lai trong thung rac cua site). Best-effort, khong nem.
    `item_url`: .../items/{id} hoac .../root:/{path}: ."""
    try:
        r = http.post("%s/permanentDelete" % item_url, headers=auth, timeout=20)
        if 0 < _code(r) < 400 or _code(r) == 404:
            return True
    except Exception:
        pass
    try:
        r = http.delete(item_url.rstrip(":"), headers=auth, timeout=20)
        if 0 < _code(r) < 400 or _code(r) == 404:
            _alert("tệp tạm %s chỉ xoá vào thùng rác (permanentDelete hỏng) - dọn thùng rác "
                   "thư viện tạm" % label)
            return True
    except Exception:
        pass
    _alert("KHÔNG xoá được tệp tạm %s - xoá tay trong thư viện tạm" % label)
    return False


def _alert(msg):
    """Mot ToDo cho ops (khong trung theo noi dung) + Error Log. Khong nem."""
    try:
        frappe.log_error("docconvert: %s" % msg, "docconvert delete")
        desc = "%s %s" % (TODO_MARKER, msg)
        if frappe.db.exists("ToDo", {"status": "Open", "description": desc}):
            return
        frappe.get_doc({"doctype": "ToDo", "allocated_to": "Administrator",
                        "description": desc, "assigned_by": "Administrator"}).insert(
            ignore_permissions=True)
    except Exception:
        pass


def sweep_temp(max_age_min=SWEEP_MAX_AGE_MIN, http=None, token=None):
    """Xoa moi tep trong thu muc tam cu hon `max_age_min` phut (worker bi giet giua chung, tra
    loi mat...). Chua cau hinh -> khong lam gi. Khong nem. Tra so tep da xoa."""
    try:
        conf = _config()
        if not is_configured():
            return 0
        base = _base(conf)
        http = http or _http()
        if token is None:
            token = _token()
        auth = {"Authorization": "Bearer %s" % token}
        r = http.get("%s/root:/%s:/children?$select=id,name,createdDateTime"
                     % (base, quote(_folder(conf), safe="/")), headers=auth, timeout=30)
        if _code(r) == 404:
            return 0
        _check(r, "liệt kê thư mục tạm")
        import datetime
        # createdDateTime cua Graph la UTC -> so voi gio UTC (khong dung gio site).
        cutoff = datetime.datetime.utcnow() - datetime.timedelta(minutes=int(max_age_min))
        n = 0
        for it in (_json(r).get("value") or []):
            created = str(it.get("createdDateTime") or "").replace("T", " ").rstrip("Z")[:19]
            try:
                old = (datetime.datetime.strptime(created, "%Y-%m-%d %H:%M:%S") < cutoff
                       if created else False)
            except Exception:
                old = False                    # khong doc duoc gio -> khong xoa (luot sau)
            if old and it.get("id") and _delete(http, "%s/items/%s" % (base, it["id"]), auth,
                                                it.get("id")):
                n += 1
        return n
    except Exception:
        frappe.log_error(frappe.get_traceback(), "docconvert sweep_temp")
        return 0
