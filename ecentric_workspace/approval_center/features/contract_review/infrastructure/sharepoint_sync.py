# Copyright (c) 2026, eCentric and contributors
"""Dua tep dinh kem cua Contract Review len SharePoint de moi nguoi review ONLINE (14/09, Hoan).

VI SAO. Tep dang nam trong Frappe (`/private/files/...`). Trinh duyet luon TAI .docx ve chu
khong mo - do la rang buoc cua Office (Word Online chi mo duoc tep nam tren SharePoint /
OneDrive), khong phai thieu cau hinh o dau. Muon "bam Mo la mo online" thi tep phai THUC SU
nam tren SharePoint.

QUYEN: Hoan chot cap cho DUNG nhung nguoi trong luong duyet (nguoi gui + cac cap duyet + CC),
KHONG dung link pham vi toan cong ty nhu Weekly Report. Hop dong co gia tri va dieu khoan
thanh toan; noi quyen xem ra ca cong ty la mot quyet dinh khac han, khong phai he qua phu cua
viec "cho mo online".

QUYEN SUA: Hoan chot cho SUA/comment truc tiep. Keo theo mot hau qua phai xu ly o cho khac:
ban tren SharePoint thanh ban song, ban dinh kem trong ERP thanh ban chup. Xem
`application/sharepoint_state.py` - cho do lo viec phat hien tep doi sau khi da co cap duyet.

Token: dung LAI `weekly_report.sharepoint.get_app_token` - app-only client_credentials, doc
client_secret tu Social Login Key, khong hardcode. Khong dung MSAL phia trinh duyet.
"""
import frappe
from frappe import _
from frappe.utils import now_datetime

from ecentric_workspace.weekly_report import sharepoint as wr_sp

#: Thu muc rieng cho ho so hop dong. KHONG dung chung "Weekly Reports".
CONTRACT_ROOT = "Contract Review"
BUSINESS_DT = "EC Contract Review Request"
LINK_DT = "EC SharePoint File Link"
TIMEOUT = 30


class SharePointChuaSan(Exception):
    """Graph chua dung duoc (chua cau hinh / mat mang). Goi ben ngoai TU quyet dinh xu ly."""


def _requests():
    import requests
    return requests


def _graph():
    return wr_sp.GRAPH


def _drive_url(rel_path):
    """URL cua mot duong dan trong thu vien mac dinh cua site."""
    from urllib.parse import quote
    return "%s/sites/%s/drive/root:/%s" % (_graph(), wr_sp.SITE_ID, quote(rel_path))


def duong_dan(business_name, file_name):
    """<CONTRACT_ROOT>/<ma phieu>/<ten tep da lam sach>.

    Moi phieu mot thu muc: doi chieu bang mat tren SharePoint khong phai do ma tep, va hai
    phieu dinh kem trung ten khong de len nhau."""
    return "%s/%s/%s" % (CONTRACT_ROOT, business_name, wr_sp.safe_filename(file_name))


def _noi_dung_tep(file_url):
    """Doc bytes cua tep tu kho Frappe. Khong doc bang duong dan tu chuoi nguoi dung dua
    vao - lay qua ban ghi File de khong the tro ra ngoai thu muc kho."""
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        raise SharePointChuaSan("Khong tim thay ban ghi File cho %s" % file_url)
    return frappe.get_doc("File", name).get_content()


def tai_len(file_url, file_name, business_name, token=None):
    """Dua MOT tep len SharePoint. Tra ve dict(item_id, web_url, last_modified).

    Dung upload session cho moi kich co - don gian hon la re nhanh theo dung luong, va
    hop dong .docx co the vuot nguong 4MB cua PUT truc tiep."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    rel = duong_dan(business_name, file_name)
    noi_dung = _noi_dung_tep(file_url)

    phien = wr_sp.create_deck_upload_session(rel, token)
    tong = len(noi_dung)
    resp = requests.put(
        phien,
        headers={"Content-Length": str(tong),
                 "Content-Range": "bytes 0-%d/%d" % (max(tong - 1, 0), tong)},
        data=noi_dung, timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        raise SharePointChuaSan("Tai len that bai (%s): %s" % (resp.status_code, resp.text[:300]))
    item = resp.json() or {}
    return {"item_id": item.get("id"),
            "web_url": item.get("webUrl"),
            "last_modified": item.get("lastModifiedDateTime")}


def cap_quyen(item_id, emails, token=None, cho_sua=True):
    """Cap quyen cho DUNG nhung email duoc liet ke, khong tao link pham vi rong.

    `sendInvitation=False`: he thong tu dieu phoi thong bao qua kenh san co, khong de Microsoft
    ban them mot email ma khong ai ngo. `requireSignIn=True`: phai dang nhap tai khoan cong ty.
    """
    requests = _requests()
    token = token or wr_sp.get_app_token()
    nguoi = [e for e in dict.fromkeys(emails or []) if e and "@" in e]
    if not nguoi:
        return []
    resp = requests.post(
        "%s/sites/%s/drive/items/%s/invite" % (_graph(), wr_sp.SITE_ID, item_id),
        headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json={"recipients": [{"email": e} for e in nguoi],
              "requireSignIn": True, "sendInvitation": False,
              "roles": ["write" if cho_sua else "read"]},
        timeout=TIMEOUT)
    if resp.status_code not in (200, 201):
        raise SharePointChuaSan("Cap quyen that bai (%s): %s" % (resp.status_code, resp.text[:300]))
    return nguoi


def doc_moc_sua(item_id, token=None):
    """lastModifiedDateTime hien tai cua tep tren SharePoint (chuoi ISO), hoac None."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    resp = requests.get(
        "%s/sites/%s/drive/items/%s?$select=id,webUrl,lastModifiedDateTime" % (
            _graph(), wr_sp.SITE_ID, item_id),
        headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    return (resp.json() or {}).get("lastModifiedDateTime")


def ghi_lien_ket(file_url, business_name, ket_qua, da_cap):
    """Luu/cap nhat ban ghi noi tep Frappe voi tep SharePoint. Idempotent theo file_url."""
    ten = frappe.db.get_value(LINK_DT, {"file_url": file_url}, "name")
    doc = frappe.get_doc(LINK_DT, ten) if ten else frappe.new_doc(LINK_DT)
    doc.file_url = file_url
    doc.business_doctype = BUSINESS_DT
    doc.business_name = business_name
    doc.sp_item_id = ket_qua.get("item_id")
    doc.sp_web_url = ket_qua.get("web_url")
    doc.sp_last_modified = ket_qua.get("last_modified")
    doc.sp_synced_at = now_datetime()
    doc.sp_granted_to = ", ".join(da_cap or [])
    doc.save(ignore_permissions=True)
    return doc.name
