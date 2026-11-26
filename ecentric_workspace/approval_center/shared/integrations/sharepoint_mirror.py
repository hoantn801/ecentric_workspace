# Copyright (c) 2026, eCentric and contributors
"""Soi guong tep dinh kem cua phieu duyet len SharePoint de review ONLINE (14/09, Hoan).

VI SAO CAN. Tep nam trong Frappe (`/private/files/...`) thi trinh duyet luon TAI .docx ve chu
khong mo - do la rang buoc cua Office (Word Online chi mo duoc tep nam tren SharePoint /
OneDrive), khong phai thieu cau hinh o dau. Muon "bam Mo la mo online" thi tep phai THUC SU
nam tren SharePoint.

VI SAO O `shared/` CHU KHONG PHAI TRONG FEATURE. Hai ly do:
  1. Phan hien thi (link + bang canh bao) nam o `shared/requests/query_service.py` - noi dung
     danh sach dinh kem cho CA 28 form. De phan tai len trong mot feature thi mot nua tinh
     nang nam trong nha, mot nua nam ngoai san.
  2. `test_feature_architecture` cam `application/` va `controllers/` cua feature nhac toi
     `infrastructure/` - ke ca trong chuoi. Ma cho tu nhien de goi dong bo lai chinh la
     `application/service.py` luc gui phieu. Dat o `shared/` thi het vuong, va vuong o day la
     kien truc dang noi dung chu khong phai kien truc phien nhieu.

KHONG CO BUOC CAP QUYEN - va do la QUYET DINH, khong phai thieu sot. 14/09 do tren tenant
that: nhom "Operation Members" DA co quyen `write` san tren thu vien cua site `operation`. Cap
quyen cho tung nguoi trong luong duyet khong he thu hep pham vi - no chi them mot lop ACL thu
hai len tren mot lop da mo san, roi bao cao "da cap quyen cho 9 nguoi" nhu the vua bao ve duoc
gi do. Hoan chot: quan quyen o MOT cho (thanh vien site SharePoint). Neu ai do trong luong
duyet mo khong duoc tep, cach sua la them ho vao site. Lich su ham `cap_quyen` cu (gom ca ly do
`/invite` khong dung duoc voi token app-only) nam o git log commit ee6243b.

Token: dung LAI `weekly_report.sharepoint.get_app_token` - app-only client_credentials, doc
client_secret tu Social Login Key, khong hardcode. Khong dung MSAL phia trinh duyet.

THU MUC HAN CHE (26/11/2026, PO Hoan, "huong 2"). Hop dong KOL/KOC mang CCCD/STK creator nen tu
17/11 bi loai khoi thu vien chung (ca phong Operation doc duoc). Nhung Ke toan / nguoi lap can
XEM va SUA bang Word Online. Huong 2: dua TOAN BO hop dong KOL len, nhung vao MOT THU MUC RIENG
(`site_config.ec_sp_kol_folder`, cung thu vien mac dinh cua site) ma IT da ngat ke thua quyen va
chi cap cho mot nhom (Phap che, Ke toan, ...). Van giu tinh than "quan quyen o MOT cho":
  * code KHONG tao thu muc, KHONG cap quyen thu muc - viec cua IT, lam o mot cho;
  * code CHI DOC quyen cua thu muc (`kiem_quyen_thu_muc`) va TU CHOI tai len khi thu muc chua ton
    tai / con quyen ke thua tu thu vien cha / mo cho ca cong ty. Fail-closed: chua cau hinh,
    Graph loi, khong chac -> KHONG tai, tep van tren ERP, phieu van gui binh thuong;
  * cap quyen theo TUNG TEP (createLink scope=users) cho nguoi trong luong van chay nhu cu (bai
    hoc 15/09 ben duoi) - RIENG phieu han che (PO 26/11, quyet dinh sau): CHI nguoi lap + nguoi
    khai trong `NGUOI_THEM_HAN_CHE` (nguoi tao creator). KHONG nguoi duyet, KHONG CC - ho xem ban
    che tren ERP. Ke toan / Phap che co quyen qua NHOM cua thu muc (IT cap, mot cho).
Hop dong LAO DONG van KHONG BAO GIO len SharePoint (`BO_QUA_PHIEU`).
"""
import hashlib
from datetime import timedelta

import frappe
from frappe.utils import now_datetime

from ecentric_workspace.weekly_report import sharepoint as wr_sp

#: DANH SACH CHO PHEP - chi nhung loai phieu o day moi duoc dua dinh kem len SharePoint.
#:
#: Phai la danh sach CHO PHEP chu khong phai danh sach CAM: dinh kem cua phieu nghi viec, phieu
#: luong, phieu ky luat... khong duoc tu dong chay ra mot thu vien ma ca phong Operation doc
#: duoc. Them mot loai phieu vao day la mot quyet dinh ve quyen rieng tu, khong phai mot dong
#: cau hinh.
THU_MUC_THEO_PHIEU = {
    "EC Contract Review Request": "Contract Review",
}

LINK_DT = "EC SharePoint File Link"
#: Ban doi chung (16/10/2026) - ban chup bat bien cua tep tren SharePoint tai moi quyet dinh.
#: Xem `sharepoint_snapshot.py`. Khai o DAY vi chinh module nay la noi phai LOAI chung ra.
SNAP_DT = "EC SharePoint Snapshot"
TIMEOUT = 30
#: Lech vai giay giua moc SharePoint tra ve luc ta tai len va moc doc lai sau do la do lam tron
#: ve giay cua SharePoint, khong phai nguoi sua. Cung gia tri voi `query_service.DUNG_SAI_GIAY`.
DUNG_SAI_GIAY = 5
#: So ten thay the toi da ("HopDong (2).docx" ... "(20)") khi duong dan da co tep. Het ma van
#: trung thi bao loi cho tep do - khong bao gio quay ve ghi de.
SO_TEN_THAY_THE = 20


class SharePointChuaSan(Exception):
    """Graph chua dung duoc (chua cau hinh / mat mang). Goi ben ngoai TU quyet dinh xu ly."""


#: Phieu cu the KHONG BAO GIO duoc dua len SharePoint du loai phieu duoc phep: loai phieu ->
#: (truong, gia tri). Khai bang du lieu, shared khong import nguoc feature.
#:   * Hop dong lao dong mang luong (QC7).  QC 15/11 B-09: nut "Them tep" truoc do bo qua chot nay.
#:   * KOL/KOC: 17/11 (B) tung nam o day; 26/11/2026 ("huong 2") chuyen sang `THU_MUC_HAN_CHE`.
#: Gia tri: mot chuoi HOAC tuple nhieu chuoi.
BO_QUA_PHIEU = {
    "EC Contract Review Request": ("contract_type", ("Labor / Hợp đồng lao động (EC)",)),
}

#: THU MUC HAN CHE (26/11/2026, PO Hoan, "huong 2"): phieu cu the KHONG vao thu muc chung cua loai
#: phieu (`THU_MUC_THEO_PHIEU`) ma vao thu muc rieng do IT dung san va ngat ke thua quyen.
#: loai phieu -> (truong, gia tri | tuple gia tri, khoa site_config chua TEN thu muc).
#: Khoa chua co gia tri -> phieu nay KHONG len SharePoint (giu hanh vi 17/11 - fail-closed).
#: Co gia tri -> chi tai len khi `thu_muc_an_toan` xac nhan thu muc ton tai + quyen rieng.
THU_MUC_HAN_CHE = {
    "EC Contract Review Request": ("contract_type", ("KOL/KOC / Creator (EC)",), "ec_sp_kol_folder"),
}

#: Phieu thu muc han che (PO 26/11, sau "huong 2"): link TUNG TEP (createLink scope=users) CHI cap
#: cho nguoi lap + nguoi khai o day - KHONG cap cho nguoi duyet / CC (ho xem ban che tren ERP; Ke
#: toan / Phap che vao qua nhom cua thu muc). loai phieu -> tuple (truong tren phieu, doctype lien
#: ket, cot chua tai khoan). Khai bang du lieu: shared khong import nguoc feature.
NGUOI_THEM_HAN_CHE = {
    "EC Contract Review Request": (("creator", "Supplier", "owner"),),    # nguoi tao creator
}

#: Ket qua kiem quyen thu muc han che duoc nho 10 phut: moi lan tai len deu hoi, nhung khong goi
#: Graph cho tung tep. IT sua thu muc xong thi toi da 10 phut sau he thong moi dung ket qua moi.
CACHE_AN_TOAN_GIAY = 600
#: Canh bao "IT can cau hinh" toi da MOT lan / gio / thu muc - Error Log khong bi spam moi lan gui.
CANH_BAO_GIAY = 3600
#: Link chia se mo rong hon "nhung nguoi cu the" -> thu muc KHONG an toan du da ngat ke thua.
LINK_SCOPE_RONG = ("anonymous", "organization")
#: Nhom mac dinh cua site SharePoint ("<Site> Members" / "<Site> Visitors") va nhom ca cong ty.
#: Ngat ke thua trong giao dien SharePoint CHEP NGUYEN quyen cha thanh quyen rieng - thu muc het
#: `inheritedFrom` nhung "Operation Members" van doc duoc. IT phai go cac nhom nay sau khi ngat.
#: So khop theo hau to / chuoi con cua ten hien thi (chu thuong). Owners duoc giu (quan tri site).
NHOM_RONG_HAU_TO = (" members", " visitors")
NHOM_RONG_CHUA = ("everyone",)


def duoc_soi_guong(business_doctype):
    return business_doctype in THU_MUC_THEO_PHIEU


def _gia_tri(rule):
    return rule[1] if isinstance(rule[1], (tuple, list, set, frozenset)) else (rule[1],)


def _thu_muc_cau_hinh(khoa):
    """Ten thu muc han che tu site_config, da bo "/" hai dau. Chua cau hinh -> None."""
    try:
        v = str(frappe.conf.get(khoa) or "").strip().strip("/")
    except Exception:
        return None
    return v or None


def phan_loai_phieu(business_doctype, business_name):
    """(loai, thu_muc_goc) cua MOT phieu - MOT cho quyet dinh phieu nay di dau.

    loai:
      * "ngoai"         - loai phieu khong nam trong danh sach cho phep;
      * "bo_qua"        - KHONG BAO GIO len (BO_QUA_PHIEU, vd hop dong lao dong);
      * "chua_cau_hinh" - phieu han che nhung site_config chua co ten thu muc -> khong len;
      * "han_che"       - vao thu muc rieng `thu_muc_goc` (con phai qua `thu_muc_an_toan`);
      * "chung"         - vao thu muc chung cua loai phieu.
    Hoi DB loi -> "bo_qua" + log (fail-closed: thieu ban Word Online con hon lo CCCD / luong)."""
    if not duoc_soi_guong(business_doctype):
        return "ngoai", None
    rule = BO_QUA_PHIEU.get(business_doctype)
    han_che = THU_MUC_HAN_CHE.get(business_doctype)
    gia_tri = {}
    try:
        for t in dict.fromkeys(r[0] for r in (rule, han_che) if r):
            gia_tri[t] = frappe.db.get_value(business_doctype, {"name": business_name}, t)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SharePoint: khong hoi duoc phieu %s co bi loai" % business_name)
        return "bo_qua", None
    if rule and gia_tri.get(rule[0]) in _gia_tri(rule):
        return "bo_qua", None
    if han_che and gia_tri.get(han_che[0]) in _gia_tri(han_che):
        thu_muc = _thu_muc_cau_hinh(han_che[2])
        return ("han_che", thu_muc) if thu_muc else ("chua_cau_hinh", None)
    return "chung", THU_MUC_THEO_PHIEU[business_doctype]


def la_phieu_han_che(business_doctype, business_name):
    """Phieu thuoc dien thu muc han che (da cau hinh hay chua), bi loai, hoac khong hoi duoc -> True."""
    return phan_loai_phieu(business_doctype, business_name)[0] in ("han_che", "chua_cau_hinh", "bo_qua")


def duoc_soi_guong_phieu(business_doctype, business_name, kiem_quyen=True):
    """Phieu nay duoc dua len SharePoint khong. MOT cong cho moi cho goi (gui phieu, them tep,
    ban doi chung, hien link "Mo online", dong bo lai, probe).

    `kiem_quyen=False`: chi xet cau hinh (re, khong goi Graph) - dung o cho chi XEP VIEC hoac hien
    thi. Cho thuc su tai len van chot lai bang `thu_muc_an_toan` (`_chot_truoc_khi_tai`)."""
    loai, thu_muc = phan_loai_phieu(business_doctype, business_name)
    if loai == "chung":
        return True
    if loai != "han_che":
        return False
    if not kiem_quyen:
        return True
    ok, ly_do = thu_muc_an_toan(thu_muc)
    if not ok:
        canh_bao_it(thu_muc, ly_do)
    return ok


def _khoa_cache(tien_to, thu_muc):
    return "%s:%s" % (tien_to, hashlib.sha1((thu_muc or "").encode("utf-8")).hexdigest()[:16])


def thu_muc_an_toan(thu_muc, token=None, bo_cache=False):
    """(ok, ly_do). CHOT AN TOAN cua thu muc han che, nho `CACHE_AN_TOAN_GIAY`.

    CHI DOC. Khong tao thu muc, khong sua quyen (quan quyen o MOT cho - IT)."""
    if not thu_muc:
        return False, "chưa cấu hình thư mục"
    khoa = _khoa_cache("ec_sp_han_che_an_toan", thu_muc)
    if not bo_cache:
        try:
            nho = frappe.cache().get_value(khoa)
        except Exception:
            nho = None
        if nho:
            return bool(nho.get("ok")), nho.get("ly_do") or ""
    ok, ly_do = kiem_quyen_thu_muc(thu_muc, token=token)[:2]
    ghi_nho_an_toan(thu_muc, ok, ly_do)
    return ok, ly_do


def ghi_nho_an_toan(thu_muc, ok, ly_do):
    """Ghi ket qua kiem quyen vao cache `CACHE_AN_TOAN_GIAY` (ham dong bo lai goi sau lan kiem tuoi
    de job nen khong dung lai ket qua cu "chua an toan" truoc khi IT sua)."""
    try:
        frappe.cache().set_value(_khoa_cache("ec_sp_han_che_an_toan", thu_muc),
                                 {"ok": bool(ok), "ly_do": ly_do}, expires_in_sec=CACHE_AN_TOAN_GIAY)
    except Exception:
        pass


def _ten_nguoi_nhan(p):
    """Ten hien thi cua moi nguoi / nhom duoc cap trong mot permission cua Graph."""
    ra = []
    ds = (p.get("grantedToIdentitiesV2") or ([p["grantedToV2"]] if p.get("grantedToV2") else [])
          or p.get("grantedToIdentities") or ([p["grantedTo"]] if p.get("grantedTo") else []))
    for gi in ds:
        for k in ("siteGroup", "group", "user", "siteUser", "application"):
            u = (gi or {}).get(k)
            if u:
                ra.append(u.get("displayName") or u.get("email") or u.get("loginName") or "?")
    return ra


def _nhom_rong(ten):
    t = (ten or "").strip().lower()
    return t.endswith(NHOM_RONG_HAU_TO) or any(c in t for c in NHOM_RONG_CHUA)


def kiem_quyen_thu_muc(thu_muc, token=None):
    """(ok, ly_do, tom_tat_quyen). Goi Graph, KHONG cache (`thu_muc_an_toan` cache ben tren).

    Hai lan GET, chi doc:
      1. `GET /sites/{site}/drive/root:/{thu_muc}` -> 404 = chua ton tai; khong co facet `folder`
         = khong phai thu muc.
      2. `GET /sites/{site}/drive/items/{id}/permissions` -> quyen KE THUA la quyen co thuoc tinh
         `inheritedFrom` (itemReference toi to tien). Khong thoa khi: bat ky quyen nao mang
         `inheritedFrom` (ke ca `{}` - chi can khoa co mat va khac null: fail-closed), danh sach
         rong (khong chung minh duoc gi), link chia se an danh / ca cong ty, hoac nhom chung cua
         site (Members / Visitors / Everyone) con trong quyen rieng.
    Moi loi (token, mang, 403...) -> khong thoa."""
    tom_tat = []
    try:
        requests = _requests()
        token = token or wr_sp.get_app_token()
        hdr = {"Authorization": "Bearer " + token}
        r1 = requests.get(_drive_url(thu_muc), headers=hdr, timeout=TIMEOUT)
        if r1.status_code == 404:
            return False, "thư mục chưa tồn tại", tom_tat
        if r1.status_code != 200:
            return False, "Graph trả %s khi đọc thư mục" % r1.status_code, tom_tat
        item = r1.json() or {}
        if not item.get("folder") or not item.get("id"):
            return False, "đường dẫn tồn tại nhưng không phải thư mục", tom_tat
        r2 = requests.get("%s/sites/%s/drive/items/%s/permissions" % (_graph(), wr_sp.SITE_ID, item["id"]),
                          headers=hdr, timeout=TIMEOUT)
        if r2.status_code != 200:
            return False, "Graph trả %s khi đọc quyền thư mục" % r2.status_code, tom_tat
        quyen = (r2.json() or {}).get("value") or []
    except Exception as e:
        return False, "không gọi được Graph: %s" % str(e)[:200], tom_tat
    ke_thua, rong, nhom = 0, [], []
    for p in quyen:
        ten = _ten_nguoi_nhan(p)
        scope = (p.get("link") or {}).get("scope")
        thua = p.get("inheritedFrom", None) is not None
        tom_tat.append({"vai_tro": ",".join(p.get("roles") or []), "thua_ke": thua,
                        "cho": ", ".join(ten) or scope or "?"})
        if thua:
            ke_thua += 1
        if scope in LINK_SCOPE_RONG:
            rong.append(scope)
        nhom += [t for t in ten if _nhom_rong(t)]
    if not quyen:
        return False, "không đọc được quyền nào của thư mục - không xác minh được", tom_tat
    if ke_thua:
        return False, "còn %d quyền kế thừa từ thư viện cha (chưa ngắt kế thừa)" % ke_thua, tom_tat
    if rong:
        return False, "có link chia sẻ phạm vi %s" % ", ".join(sorted(set(rong))), tom_tat
    if nhom:
        return False, "nhóm chung của site còn quyền: %s" % ", ".join(sorted(set(nhom))), tom_tat
    return True, "", tom_tat


def canh_bao_it(thu_muc, ly_do):
    """Error Log "IT can cau hinh" - toi da MOT lan / `CANH_BAO_GIAY` / thu muc."""
    khoa = _khoa_cache("ec_sp_han_che_canh_bao", thu_muc)
    try:
        if frappe.cache().get_value(khoa):
            return False
        frappe.cache().set_value(khoa, 1, expires_in_sec=CANH_BAO_GIAY)
    except Exception:
        pass
    frappe.log_error(
        "Thư mục KOL chưa ngắt kế thừa quyền / chưa tồn tại — IT cần cấu hình.\n"
        "Thư mục: %s\nLý do: %s\n"
        "Hệ thống KHÔNG tải hợp đồng KOL lên SharePoint cho tới khi thư mục đạt yêu cầu. Phiếu vẫn "
        "gửi bình thường, tệp vẫn nằm trên ERP. (Cảnh báo lặp lại tối đa mỗi giờ một lần.)"
        % (thu_muc or "(chưa cấu hình)", ly_do), "SharePoint: thư mục KOL chưa an toàn")
    return True


def _chot_truoc_khi_tai(business_doctype, business_name, token=None):
    """Thu muc goc de tai len - goi TRUOC MOI lan tai len (`tai_len`). Nem SharePointChuaSan khi
    phieu khong duoc len, hoac thu muc han che chua an toan (khong tai gi)."""
    loai, thu_muc = phan_loai_phieu(business_doctype, business_name)
    if loai == "chung":
        return thu_muc
    if loai != "han_che":
        raise SharePointChuaSan("Phieu %s khong duoc dua len SharePoint (%s)" % (business_name, loai))
    ok, ly_do = thu_muc_an_toan(thu_muc, token=token)
    if not ok:
        canh_bao_it(thu_muc, ly_do)
        raise SharePointChuaSan("Thu muc han che %s chua an toan: %s" % (thu_muc, ly_do))
    return thu_muc


def _requests():
    import requests
    return requests


def _graph():
    return wr_sp.GRAPH


def _drive_url(rel_path):
    """URL cua mot duong dan trong thu vien mac dinh cua site."""
    from urllib.parse import quote
    return "%s/sites/%s/drive/root:/%s" % (_graph(), wr_sp.SITE_ID, quote(rel_path))


def duong_dan(business_doctype, business_name, file_name, goc=None):
    """<thu muc goc>/<ma phieu>/<ten tep da lam sach>.

    Thu muc goc: thu muc chung cua loai phieu, HOAC thu muc han che (`phan_loai_phieu`, 26/11).
    `goc` da tinh san (tu `_chot_truoc_khi_tai`) thi dung luon, khong hoi lai DB.
    Moi phieu mot thu muc: doi chieu bang mat tren SharePoint khong phai do ma tep, va hai
    phieu dinh kem trung ten khong de len nhau."""
    if not goc:
        loai, goc = phan_loai_phieu(business_doctype, business_name)
        if loai not in ("chung", "han_che") or not goc:
            raise SharePointChuaSan("Phieu %s (%s) khong duoc dua len SharePoint (%s)"
                                    % (business_name, business_doctype, loai))
    return "%s/%s/%s" % (goc, business_name, wr_sp.safe_filename(file_name))


def _noi_dung_tep(file_url):
    """Doc bytes cua tep tu kho Frappe. Khong doc bang duong dan tu chuoi nguoi dung dua
    vao - lay qua ban ghi File de khong the tro ra ngoai thu muc kho."""
    name = frappe.db.get_value("File", {"file_url": file_url}, "name")
    if not name:
        raise SharePointChuaSan("Khong tim thay ban ghi File cho %s" % file_url)
    noi_dung = frappe.get_doc("File", name).get_content()
    # File.get_content() cua Frappe tra CHUOI cho tep doc duoc bang UTF-8 (.txt, .csv, ca PDF
    # thuan ASCII). Gui chuoi len Graph: Content-Length dem KY TU chu khong dem byte, va
    # http.client ma hoa latin-1 -> tep tieng Viet hong / nem loi. Frappe vua giai ma UTF-8
    # thanh cong nen ma hoa lai UTF-8 ra dung tung byte goc.
    if isinstance(noi_dung, str):
        noi_dung = noi_dung.encode("utf-8")
    return noi_dung or b""


def bam_noi_dung(noi_dung):
    """SHA-256 cua bytes tep - dau van tay noi dung da tai len (luu o `sp_content_hash`)."""
    return hashlib.sha256(noi_dung or b"").hexdigest()


def ten_thay_the(file_name, lan):
    """Lan 1 -> giu nguyen ten; lan n>=2 -> "HopDong (n).docx". Dung khi duong dan da co tep."""
    if not lan or lan <= 1:
        return file_name
    ten = str(file_name or "")
    if "." in ten:
        goc, duoi = ten.rsplit(".", 1)
        return "%s (%d).%s" % (goc, lan, duoi)
    return "%s (%d)" % (ten, lan)


def _phien_tai_len(rel, token, item_id=None):
    """Mo upload session. Tra ve uploadUrl, hoac None khi duong dan DA CO tep (409).

    HAI che do, va day la cho chan mat du lieu (03/11/2026):
      * `item_id` -> ghi de noi dung CHINH item do (giu id, lich su phien ban, link chia se).
        Chi `dong_bo_phieu` goi, va chi sau khi da chac ban song CHUA ai sua.
      * khong co `item_id` -> TAO MOI theo duong dan voi conflictBehavior=`fail`. Duong dan da
        co tep (ban song nguoi duyet dang sua, tep trung ten khac hoa/thuong...) thi Graph tra
        409 - ben goi doi sang ten thay the. KHONG BAO GIO `replace` theo duong dan: truoc day
        `weekly_report.create_deck_upload_session` (replace) duoc dung o day, nen gui lai phieu
        la tai de ban Frappe len ban song, xoa sach track changes + comment cua nguoi duyet."""
    requests = _requests()
    if item_id:
        url = "%s/sites/%s/drive/items/%s/createUploadSession" % (_graph(), wr_sp.SITE_ID, item_id)
        hanh_vi = "replace"
    else:
        url = _drive_url(rel) + ":/createUploadSession"
        hanh_vi = "fail"
    resp = requests.post(
        url, headers={"Authorization": "Bearer " + token, "Content-Type": "application/json"},
        json={"item": {"@microsoft.graph.conflictBehavior": hanh_vi}}, timeout=TIMEOUT)
    if resp.status_code == 409 and not item_id:
        return None
    if resp.status_code not in (200, 201):
        raise SharePointChuaSan("Mo phien tai len that bai (%s): %s"
                                % (resp.status_code, (resp.text or "")[:300]))
    phien = (resp.json() or {}).get("uploadUrl")
    if not phien:
        raise SharePointChuaSan("Graph khong tra uploadUrl")
    return phien


def tai_len(business_doctype, file_url, file_name, business_name, token=None, item_id=None):
    """Dua MOT tep len SharePoint. Tra ve dict(item_id, web_url, last_modified, content_hash).

    Mac dinh TAO TEP MOI va KHONG BAO GIO ghi de tep dang co o duong dan do: trung thi lan luot
    thu "ten (2)", "ten (3)"... (xem `_phien_tai_len`). `item_id` = ghi de dung item do - chi
    dung khi ben goi da chac ban song chua ai sua (`dong_bo_phieu`).

    Dung upload session cho moi kich co - don gian hon la re nhanh theo dung luong, va
    hop dong .docx co the vuot nguong 4MB cua PUT truc tiep."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    # CHOT AN TOAN truoc MOI lan tai len (26/11, ke ca ghi de theo item_id): Labor -> khong bao gio;
    # thu muc han che chua ton tai / con ke thua quyen -> khong tai, log cho IT.
    goc = _chot_truoc_khi_tai(business_doctype, business_name, token=token)
    noi_dung = _noi_dung_tep(file_url)
    tong = len(noi_dung)
    for lan in ([1] if item_id else range(1, SO_TEN_THAY_THE + 1)):
        rel = None if item_id else duong_dan(business_doctype, business_name,
                                             ten_thay_the(file_name, lan), goc=goc)
        phien = _phien_tai_len(rel, token, item_id=item_id)
        if phien is None:
            continue
        resp = requests.put(
            phien,
            headers={"Content-Length": str(tong),
                     "Content-Range": "bytes 0-%d/%d" % (max(tong - 1, 0), tong)},
            data=noi_dung, timeout=TIMEOUT)
        if resp.status_code == 409 and not item_id:
            # Graph kiem trung ten ca o byte cuoi: ai do vua tao tep cung ten trong luc tai.
            continue
        if resp.status_code not in (200, 201):
            raise SharePointChuaSan("Tai len that bai (%s): %s" % (resp.status_code, resp.text[:300]))
        item = resp.json() or {}
        return {"item_id": item.get("id"),
                "web_url": item.get("webUrl"),
                "last_modified": item.get("lastModifiedDateTime"),
                "content_hash": bam_noi_dung(noi_dung)}
    raise SharePointChuaSan("Thu %d ten cho %s deu da co tep tren SharePoint - khong ghi de"
                            % (SO_TEN_THAY_THE, file_name))


# --------------------------------------------------------------------------- #
# CAP QUYEN THEO NGUOI - da tung bi go 14/09 roi KHOI PHUC 15/09.
#
# 14/09 do thay nhom "Operation Members" co quyen `write` san tren thu vien, nen ket luan
# "moi nguoi da vao duoc roi" va go buoc nay di. Phep do do THIEU mot nua: no tra loi
# "nhom nao co quyen", KHONG tra loi "ai nam trong nhom". 15/09 chi lien.vu - nguoi duyet
# cap 2 cua Contract Review - bam "Mo online" va bi SharePoint chan. Mot phan vi du du de
# bac mot ket luan rut ra tu phep do thieu.
#
# Bai hoc giu lai o day vi no se con lap: mot quyet dinh chi vung chac bang phep do YEU NHAT
# ma no dua vao. Luc do phai noi ro quyet dinh dang treo tren du kien nao, chu khong chi neu
# no nhu mot lua chon.
# --------------------------------------------------------------------------- #


#: Tai khoan dich vu - co trong luong duyet nhung khong phai NGUOI review. Khong cap quyen
#: vao hop dong cho chung: quyen thua la quyen rui ro, va mot dia chi khong phai hom thu that
#: con co the lam Graph tu choi ca lo. Danh sach nay khop theo phan truoc dau @.
TAI_KHOAN_DICH_VU = ("fabric.bot",)


def loc_nguoi_that(emails):
    """Tra ve (giu, bo). Bo tai khoan dich vu. KHONG im lang: ben goi in ra phan bi bo."""
    giu, bo = [], []
    for e in dict.fromkeys(emails or []):
        if not e or "@" not in e:
            continue
        if e.split("@")[0].lower() in TAI_KHOAN_DICH_VU:
            bo.append(e)
        else:
            giu.append(e)
    return giu, bo


def cap_quyen(item_id, emails, token=None, cho_sua=True, pha_thua_ke=False):
    """Cap quyen cho DUNG nhung email duoc liet ke. Tra ve dict(da_cap, bo_qua, link).

    DUONG DI: `createLink` voi scope="users" - KHONG phai `/invite`.

    Vi sao doi: 14/09 do tren tenant that, `/invite` tra ve `noResolvedUsers` - va khong MOT
    ai trong 10 dia chi resolve duoc. Zero nguoi resolve nghia la loi o ngu canh app-only
    (token khong dai dien cho nguoi dung nao nen Graph khong co "nguoi moi" de phan giai danh
    sach), chu khong phai mot dia chi hong lam hong ca lo. Trong khi do `createLink` chay that
    moi tuan qua `weekly_report.create_org_link` voi cung loai token - nen day la duong da co
    bang chung, khong phai phong doan thu hai.

    KHONG BAO GIO tu dong lui ve scope="organization" khi that bai. Cap nham cho ca cong ty
    quyen SUA hop dong con te hon nhieu so voi bao loi va de nguoi that quyet dinh.

    `pha_thua_ke=False` la mac dinh co chu y: dat True se GO quyen thua ke tu thu vien, tuc
    thu hoi quyen cua nhung nguoi dang co. Do la mot thay doi tru tren du lieu song, phai do
    `doc_quyen` truoc va co nguoi chot, khong lam kem theo mot lan tai tep.
    """
    requests = _requests()
    token = token or wr_sp.get_app_token()
    nguoi, bo = loc_nguoi_that(emails)
    if not nguoi:
        return {"da_cap": [], "bo_qua": bo, "link": None}
    than = {"type": "edit" if cho_sua else "view",
            "scope": "users",
            "recipients": [{"email": e} for e in nguoi],
            "sendInvitation": False}
    if pha_thua_ke:
        than["retainInheritedPermissions"] = False
    url = "%s/sites/%s/drive/items/%s/createLink" % (_graph(), wr_sp.SITE_ID, item_id)
    hdr = {"Authorization": "Bearer " + token, "Content-Type": "application/json"}
    resp = requests.post(url, headers=hdr, json=than, timeout=TIMEOUT)
    if resp.status_code in (200, 201):
        link = ((resp.json() or {}).get("link") or {}).get("webUrl")
        return {"da_cap": nguoi, "bo_qua": bo, "link": link}
    if not (_khong_resolve(resp) and len(nguoi) > 1):
        raise SharePointChuaSan("Cap quyen that bai (%s): %s" % (resp.status_code, resp.text[:300]))
    # 20/11/2026 (EC-CTR-2026-00122 + moi phieu cua anh.luu tu 09/10): MOT dia chi Graph khong tim
    # thay tai khoan Microsoft 365 -> `noResolvedUsers` cho CA LO -> khong ai duoc cap, khong ghi
    # lien ket, .docx mat "Mo online". Cap TUNG NGUOI: nguoi resolve duoc van co quyen, nguoi hong
    # vao `bo_qua` + log ten de HR / IT sua tai khoan. Ca lo deu hong thi van nem nhu cu (co the la
    # loi ngu canh token, khong phai mot dia chi - xem ghi chu 14/09 o tren).
    da_cap, hong, link = [], [], None
    for e in nguoi:
        r1 = requests.post(url, headers=hdr, json=dict(than, recipients=[{"email": e}]), timeout=TIMEOUT)
        if r1.status_code in (200, 201):
            da_cap.append(e)
            link = link or ((r1.json() or {}).get("link") or {}).get("webUrl")
        elif _khong_resolve(r1):
            hong.append(e)
        else:
            raise SharePointChuaSan("Cap quyen that bai (%s): %s" % (r1.status_code, r1.text[:300]))
    if hong:
        # 22/11/2026: goi createLink rieng cho nguoi DA CO SAN trong link quyen cua tep cung bi bao
        # noResolvedUsers (lien.vu tren EC-CTR-2026-00122: co ten trong quyen write ma log van ghi
        # "khong cap duoc"). Doi chieu quyen dang co truoc khi ket luan; doc quyen hong -> giu nguyen
        # ket luan cu (khong doan).
        try:
            co_san = _email_dang_co_quyen(item_id, token)
        except Exception:
            co_san = set()
        da_co = [e for e in hong if e.lower() in co_san]
        da_cap += da_co
        hong = [e for e in hong if e.lower() not in co_san]
    if not da_cap:
        raise SharePointChuaSan("Cap quyen that bai: Graph khong resolve duoc ai trong %s" % ", ".join(hong))
    if hong:
        frappe.log_error("Khong cap duoc quyen tep %s cho: %s - Graph bao noResolvedUsers va nguoi nay chua co quyen "
                         "tren tep (email khong khop tai khoan Microsoft 365). Nhung nguoi con lai da duoc cap."
                         % (item_id, ", ".join(hong)), "SharePoint: email khong co tai khoan M365")
    return {"da_cap": da_cap, "bo_qua": bo + hong, "link": link}


def _email_dang_co_quyen(item_id, token):
    """Email (chu thuong) dang co quyen rieng tren tep - doc qua `doc_quyen`. Ten nhom bo qua."""
    ra = set()
    for q in doc_quyen(item_id, token=token) or []:
        for ai in (q.get("cho") or "").split(","):
            ai = ai.strip().lower()
            if "@" in ai:
                ra.add(ai)
    return ra


def _khong_resolve(resp):
    """400 `noResolvedUsers` cua createLink: co dia chi Graph khong phan giai duoc."""
    return resp.status_code == 400 and "noResolvedUsers" in (resp.text or "")


def doc_quyen(item_id, token=None):
    """Liet ke quyen HIEN CO tren mot tep. Chi doc.

    Dung de tra loi mot cau hoi quyet dinh ca thiet ke: nguoi trong cong ty da co quyen vao
    thu vien nay san chua? Neu roi thi buoc cap quyen la thua; neu chua thi phai cap that.
    Doan bang cam tinh thi khong biet duoc."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    resp = requests.get(
        "%s/sites/%s/drive/items/%s/permissions" % (_graph(), wr_sp.SITE_ID, item_id),
        headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
    if resp.status_code != 200:
        raise SharePointChuaSan("Doc quyen that bai (%s): %s" % (resp.status_code, resp.text[:300]))
    ra = []
    for p in (resp.json() or {}).get("value", []):
        ai = []
        for gi in (p.get("grantedToIdentitiesV2") or ([p["grantedToV2"]] if p.get("grantedToV2") else [])):
            u = (gi or {}).get("user") or (gi or {}).get("siteGroup") or (gi or {}).get("group") or {}
            ai.append(u.get("email") or u.get("displayName") or "?")
        ra.append({"vai_tro": ",".join(p.get("roles") or []),
                   "thua_ke": bool(p.get("inheritedFrom")),
                   "cho": ", ".join(ai) or (p.get("link") or {}).get("scope") or "?"})
    return ra


def doc_moc_sua(item_id, token=None):
    """Moc sua gan nhat cua tep tren SharePoint, DA doi ve gio he thong, hoac None.

    Tra ve datetime chu khong phai chuoi ISO: ben goi se dem no di so voi moc duyet trong ERP,
    ma moc duyet la gio he thong. Tra ve chuoi UTC o day thi moi cho goi deu phai nho tu doi -
    va cho nao quen thi lech bay tieng mot cach im lang."""
    requests = _requests()
    token = token or wr_sp.get_app_token()
    resp = requests.get(
        "%s/sites/%s/drive/items/%s?$select=id,webUrl,lastModifiedDateTime" % (
            _graph(), wr_sp.SITE_ID, item_id),
        headers={"Authorization": "Bearer " + token}, timeout=TIMEOUT)
    if resp.status_code != 200:
        return None
    return gio_he_thong((resp.json() or {}).get("lastModifiedDateTime"))


def gio_he_thong(iso):
    """Doi moc thoi gian ISO-8601 UTC cua Graph ("2026-09-14T08:58:18Z") sang gio he thong.

    HAI ly do, ly do thu hai moi la ly do that:
      1. MariaDB khong nhan chu "T" va "Z" trong cot Datetime - do that 14/09 nem
         (1292, "Incorrect datetime value: '2026-09-14T08:58:18Z'").
      2. Quan trong hon: Graph tra ve gio UTC, con moc duyet trong ERP la gio he thong
         (UTC+7). Luu nguyen chuoi UTC thi moi phep so "tep co bi sua sau khi duyet khong"
         deu lech BAY TIENG theo huong co loi cho ke sua - mot ban hop dong bi sua ngay sau
         khi duyet xong van trong nhu duoc sua tu truoc. Do dung la thu ma bang canh bao
         sinh ra de bat, nen sai o day thi tinh nang coi nhu khong ton tai.

    Tra ve datetime KHONG mang tzinfo (Frappe luu gio tran theo mui he thong).
    """
    if not iso:
        return None
    from frappe.utils import convert_utc_to_system_timezone, get_datetime
    txt = str(iso).strip()
    for bo in ("Z", "+00:00"):
        if txt.endswith(bo):
            txt = txt[: -len(bo)]
            break
    txt = txt.replace("T", " ")
    if "." in txt:
        txt = txt.split(".", 1)[0]
    return convert_utc_to_system_timezone(get_datetime(txt)).replace(tzinfo=None)


def ghi_lien_ket(business_doctype, file_url, business_name, ket_qua, da_cap=None, share_url=None):
    """Luu/cap nhat ban ghi noi tep Frappe voi tep SharePoint. Idempotent theo file_url.

    `share_url` (23/09): link ma `cap_quyen` tra ve. Truoc day ham goi chi chuyen `da_cap` xuong
    va VUT link di, nen nut "Mo online" tro vao `sp_web_url` - URL goc cua tep trong thu vien.
    Quyen cap bang createLink(scope=users) gan vao LINK, khong vao URL goc: ai co quyen san trong
    thu vien (nguoi duyet) mo URL goc van duoc, con nguoi gui phieu thi bi SharePoint chan du ten
    ho nam ngay trong `sp_granted_to` (do tren EC-CTR-2026-00019, huong.pham).

    `None` nghia la "lan nay khong co link moi" - GIU link cu, khong xoa. Mot lan cap quyen hong
    khong duoc phep lam mat link dang dung duoc."""
    ten = frappe.db.get_value(LINK_DT, {"file_url": file_url}, "name")
    doc = frappe.get_doc(LINK_DT, ten) if ten else frappe.new_doc(LINK_DT)
    doc.file_url = file_url
    doc.business_doctype = business_doctype
    doc.business_name = business_name
    doc.sp_item_id = ket_qua.get("item_id")
    doc.sp_web_url = ket_qua.get("web_url")
    doc.sp_last_modified = gio_he_thong(ket_qua.get("last_modified"))
    # MOC NEN: chinh lan tai len nay. Tu day tro di, `sp_last_modified` lon hon moc nay
    # nghia la NGUOI sua tren SharePoint - do moi la dieu bang canh bao muon noi.
    doc.sp_uploaded_at = doc.sp_last_modified
    doc.sp_synced_at = now_datetime()
    doc.sp_granted_to = ", ".join(da_cap or [])
    if share_url:
        doc.sp_share_url = share_url
    # Dau van tay noi dung VUA tai len (03/11/2026) - lan gui lai sau so voi no de biet tep
    # trong Frappe co doi that khong. Truoc migrate cot chua co: Document.save bo qua thuoc
    # tinh ngoai meta, khong loi.
    if ket_qua.get("content_hash"):
        doc.sp_content_hash = ket_qua["content_hash"]
    doc.save(ignore_permissions=True)
    return doc.name


def url_mo_online(business_doctype, business_name, file_url, user):
    """URL mo `file_url` cua phieu tren Word Online cho `user`, hoac None (chua co ban SharePoint).

    KHONG kiem quyen nghiep vu - ben goi (vd `kol_access.open_online`) da kiem. Qua CUNG cong theo
    phieu voi luong tai len (`duoc_soi_guong_phieu`, chi xet cau hinh - khong goi Graph khi bam):
    hop dong lao dong / KOL chua cau hinh thu muc -> None du con ban ghi lien ket cu sot lai.
    Ban ghi lien ket phai THUOC CHINH phieu nay (phieu tao lai tu phieu tu choi dung chung
    `file_url` - xem `_lien_ket_cua_phieu`).

    Link nao: `user` nam trong `sp_granted_to` va co `sp_share_url` -> link chia se (quyen tung tep
    gan vao LINK, URL goc bi SharePoint chan voi ho - xem `ghi_lien_ket`). Con lai (Ke toan / Phap
    che vao qua nhom cua thu muc han che) -> `sp_web_url`."""
    if not file_url or not duoc_soi_guong_phieu(business_doctype, business_name, kiem_quyen=False):
        return None
    row = frappe.db.get_value(
        LINK_DT, {"file_url": file_url, "business_doctype": business_doctype,
                  "business_name": business_name},
        ["sp_web_url", "sp_share_url", "sp_granted_to"], as_dict=True)
    if not row or not row.get("sp_web_url"):
        return None
    da_cap = {e.strip().lower() for e in (row.get("sp_granted_to") or "").split(",") if e.strip()}
    if row.get("sp_share_url") and (user or "").strip().lower() in da_cap:
        return row.get("sp_share_url")
    return row.get("sp_web_url")


def nguoi_trong_luong(business_doctype, business_name):
    """Nguoi gui + moi cap duyet cua phieu + CC. KHONG mo cho ca cong ty.

    Phieu thu muc han che / bi loai (KOL, 26/11 - PO chot sau "huong 2"): CHI nguoi lap + nguoi
    khai trong `NGUOI_THEM_HAN_CHE` (`_nguoi_phieu_han_che`) - khong nguoi duyet, khong CC.

    Doc tu `EC Approval Request Approver` - dung bang ma engine THAT SU dung de quyet dinh ai
    duoc duyet, khong tu dung mot danh sach thu hai roi hai ben troi nhau.

    `cc_to` khong phai form nao cung co, nen hoi meta truoc thay vi doc bua roi nuot loi: mot
    truong thieu la chuyen cau hinh, khong phai chuyen phai giau di.
    """
    if la_phieu_han_che(business_doctype, business_name):
        return _nguoi_phieu_han_che(business_doctype, business_name)
    fields = ["requested_by", "approval_request"]
    co_cc = frappe.get_meta(business_doctype).has_field("cc_to")
    if co_cc:
        fields.append("cc_to")
    row = frappe.db.get_value(business_doctype, business_name, fields, as_dict=True) or {}
    ra = [row.get("requested_by")]
    req = row.get("approval_request") or _phieu_duyet_theo_tham_chieu(business_doctype, business_name)
    if req:
        # Dong kieu "Role: X" chi con tinh khi nguoi do VAN giu role X (03/11/2026): dong duyet
        # chot luc gui, role thi song. Nguoi da bi go role (vd roi nhom Finance) khong duoc cap
        # quyen SUA hop dong o lan dong bo / gui lai sau do - cung luat voi nut Duyet
        # (`transitions.row_still_eligible`).
        for r in frappe.get_all("EC Approval Request Approver",
                                filters={"approval_request": req},
                                fields=["approver", "source"]) or []:
            if _dong_con_hieu_luc(r.get("source"), r.get("approver")):
                ra.append(r.get("approver"))
    for e in ((row.get("cc_to") or "") if co_cc else "").replace(";", ",").split(","):
        e = e.strip()
        if e:
            ra.append(e)
    return _tai_khoan_con_dung(ra)


def _nguoi_phieu_han_che(business_doctype, business_name):
    """Nguoi lap + nguoi khai trong `NGUOI_THEM_HAN_CHE` (vd nguoi tao creator, neu co tai khoan).

    Tep phieu han che mang CCCD / STK creator. Nguoi duyet (Truong phong, CEO...) va CC KHONG duoc
    link tung tep: ho xem ban che tren ERP (PO 17/11 + 26/11). Ke toan / Phap che mo qua nhom cua
    thu muc han che. Khop `kol_access.can_download_full` o phan "ai duoc ban du"."""
    them = NGUOI_THEM_HAN_CHE.get(business_doctype) or ()
    fields = ["requested_by"] + [t[0] for t in them]
    row = frappe.db.get_value(business_doctype, business_name, fields, as_dict=True) or {}
    ra = [row.get("requested_by")]
    for truong, dt, cot in them:
        if row.get(truong):
            ra.append(frappe.db.get_value(dt, row.get(truong), cot))
    return _tai_khoan_con_dung(ra)


def _tai_khoan_con_dung(ra):
    """Bo trung, bo rong / khong phai email; bo tai khoan ERP DA KHOA (nghi viec - job 00:30) - khong
    cap quyen sua hop dong nua. Chi bo ai CO trong User va enabled = 0: email ngoai he thong (CC doi
    tac) giu nguyen nhu truoc."""
    ra = [e for e in dict.fromkeys(ra) if e and "@" in e]
    return [e for e in ra if frappe.db.get_value("User", e, "enabled") != 0]


def _dong_con_hieu_luc(source, user):
    from ecentric_workspace.approval_center.shared.workflow.transitions import row_still_eligible
    return row_still_eligible(source, user)


def _phieu_duyet_theo_tham_chieu(business_doctype, business_name):
    """Lui ve tra EC Approval Request theo (reference_doctype, reference_name) khi truong
    `approval_request` tren phieu nghiep vu con trong (09/10/2026, EC-CTR-2026-00036): thieu
    buoc nay thi danh sach cap quyen chi con moi nguoi gui."""
    rows = frappe.get_all("EC Approval Request",
                          filters={"reference_doctype": business_doctype,
                                   "reference_name": business_name},
                          pluck="name", order_by="creation desc", limit_page_length=1)
    return rows[0] if rows else None


def tep_doi_chung(business_doctype, business_name):
    """Ten (docname) cac ban ghi File la BAN DOI CHUNG cua phieu. DAU MOC TUONG MINH.

    Khop theo ten ban ghi File ma `EC SharePoint Snapshot` tro vao - KHONG theo tien to ten tep,
    va KHONG theo `file_url`: Frappe gop tep trung noi dung vao CUNG mot `file_url`
    (`content_hash`), nen mot ban chup chua ai sua co the trung URL voi chinh tep nguoi gui tai
    len. Loai theo URL thi loai luon tep that cua ho khoi SharePoint.

    Moi cho duyet dinh kem cua phieu (soi guong, chep sang phieu moi, man hinh chi tiet) phai
    goi ham nay. Ban doi chung ma bi day nguoc len SharePoint thi no thanh "tep hop dong" moi
    va nguoi duyet sau se sua tren no."""
    ra = set()
    for r in frappe.get_all(SNAP_DT,
                            filters={"business_doctype": business_doctype,
                                     "business_name": business_name},
                            fields=["docx_file", "pdf_file"], limit_page_length=0) or []:
        for f in (r.get("docx_file"), r.get("pdf_file")):
            if f:
                ra.add(f)
    return ra


def _dinh_kem(business_doctype, business_name):
    """Dinh kem cua mot phieu. Tep Office truoc: do la thu nguoi ta can mo bang Word Online.

    KHONG gom ban doi chung (16/10/2026) - xem `tep_doi_chung`."""
    tep = frappe.get_all(
        "File",
        filters={"attached_to_doctype": business_doctype, "attached_to_name": business_name},
        fields=["name", "file_name", "file_url", "creation"], order_by="creation asc")
    loai = tep_doi_chung(business_doctype, business_name)
    if loai:
        tep = [t for t in tep if t.get("name") not in loai]
    # MOT dong cho moi tep vat ly (03/11/2026): mot lan tai len tren form sinh HAI ban ghi File
    # cung `file_url` (xem query_service.dedupe_attachments) -> truoc day moi tep bi day len
    # SharePoint hai lan. Giu ban ghi SOM nhat (order_by creation asc).
    da, gon = set(), []
    for t in tep:
        khoa = t.get("file_url") or ("name:%s" % t.get("name"))
        if khoa in da:
            continue
        da.add(khoa)
        gon.append(t)
    tep = gon
    duoi = (".docx", ".doc", ".xlsx", ".xls", ".pptx", ".ppt")
    office = [t for t in tep if (t.file_name or "").lower().endswith(duoi)]
    khac = [t for t in tep if t not in office]
    return office + khac


def dong_bo_phieu(business_doctype, business_name):
    """Dong bo dinh kem cua mot phieu len SharePoint. Tra ve dict tong ket.

    Goi luc GUI va GUI LAI phieu. Ban tren SharePoint la ban SONG: nguoi duyet sua track
    changes + comment truc tiep tren do (Hoan chot). Truoc 03/11/2026 ham nay tai lai MOI tep
    voi conflictBehavior=replace, nen moi lan gui lai la ban Frappe (cu) de len ban song - xoa
    sach cong cua nguoi duyet. Nay moi tep di qua `_dong_bo_tep`:
      * chua co lien ket CUA PHIEU NAY      -> tai len tep MOI, trung ten thi doi ten, khong de;
      * co lien ket, noi dung Frappe KHONG doi -> KHONG tai, chi lam tuoi quyen (createLink cho
        nguoi trong luong HIEN TAI - nguoi duyet moi them sau lan dau van mo duoc);
      * co lien ket, noi dung DOI, ban song CHUA ai sua -> ghi de DUNG item do (giu lich su);
      * co lien ket, noi dung DOI, ban song DA bi sua (hoac khong doc duoc moc sua) -> tai ban
        moi thanh tep RIENG canh ban song, ban song giu nguyen + ghi log.
    Ban doi chung khong bao gio duoc day len (`_dinh_kem` loai ra).

    KHONG nem ra ngoai vi MOT tep hong: mot tep loi khong duoc keo theo ca phieu khong len duoc
    tep nao. Tra ve danh sach `hong` de ben goi ghi log.
    """
    if not duoc_soi_guong(business_doctype):
        return {"bo_qua": "loai phieu khong nam trong danh sach cho phep",
                "xong": [], "hong": [], "so_tep": 0}
    # PO 17/11: chot ca o day (cong cu probe / patch backfill / dong bo lai goi thang, khong qua
    # service). 26/11: phieu thu muc han che chi qua khi da cau hinh VA thu muc an toan.
    if not duoc_soi_guong_phieu(business_doctype, business_name):
        return {"bo_qua": "phieu nay khong duoc dua len SharePoint (BO_QUA_PHIEU / thu muc han che "
                          "chua cau hinh hoac chua an toan)",
                "xong": [], "hong": [], "so_tep": 0}
    tep = _dinh_kem(business_doctype, business_name)
    if not tep:
        return {"xong": [], "hong": [], "so_tep": 0}
    token = wr_sp.get_app_token()
    nguoi = nguoi_trong_luong(business_doctype, business_name)
    xong, giu, hong = [], [], []
    for t in tep:
        try:
            cach = _dong_bo_tep(business_doctype, business_name, t, nguoi, token)
            (giu if cach == "giu_ban_song" else xong).append(t.file_name)
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             "SharePoint soi guong %s / %s" % (business_name, t.file_name))
            hong.append(t.file_name)
    return {"xong": xong, "giu_ban_song": giu, "hong": hong, "so_tep": len(tep)}


def _lien_ket_cua_phieu(business_doctype, business_name, file_url):
    """Ban ghi lien ket cua `file_url` THUOC CHINH phieu nay, hoac None.

    Phai loc ca theo phieu: phieu tao lai tu phieu bi tu choi (`command_service.clone_request`)
    dung CHUNG `file_url` voi phieu cu. Khop chi theo URL thi phieu moi se "lam tuoi quyen"
    cho luong duyet MOI tren ban song cua phieu CU - mo hop dong cua ho so khac cho nguoi
    khong lien quan."""
    fields = ["name", "sp_item_id", "sp_uploaded_at", "sp_synced_at"]
    if frappe.db.has_column(LINK_DT, "sp_content_hash"):
        fields.append("sp_content_hash")
    return frappe.db.get_value(
        LINK_DT, {"file_url": file_url, "business_doctype": business_doctype,
                  "business_name": business_name}, fields, as_dict=True)


def _tep_da_doi(lien, tep):
    """Noi dung tep trong Frappe co KHAC ban he thong da tai len lan truoc khong.

    Co `sp_content_hash` -> so ma bam (dung tuyet doi). Ban ghi cu chua co ma bam (truoc
    03/11/2026) -> chi coi la doi khi ban ghi File hien tai duoc tao SAU lan dong bo cuoi, tuc
    tep da bi go ra roi tai lai cung ten. Khong du du kien -> KHONG doi: sai chieu nay chi lam
    ban SharePoint cham mot nhip, sai chieu kia la xoa cong cua nguoi duyet."""
    from frappe.utils import get_datetime
    bam = lien.get("sp_content_hash")
    if bam:
        return bam_noi_dung(_noi_dung_tep(tep.get("file_url"))) != bam
    tao, dong_bo = tep.get("creation"), lien.get("sp_synced_at")
    if tao and dong_bo:
        return get_datetime(tao) > get_datetime(dong_bo)
    return False


def _ban_song_da_sua(lien, token):
    """Ban tren SharePoint co bi NGUOI sua sau lan he thong tai len khong. KHONG doc duoc moc
    (tep bi xoa / Graph loi / thieu moc nen) -> coi nhu DA sua: khong chac thi khong ghi de."""
    from frappe.utils import get_datetime
    nen = lien.get("sp_uploaded_at")
    if not nen:
        return True
    moc = doc_moc_sua(lien.get("sp_item_id"), token=token)
    if not moc:
        return True
    return get_datetime(moc) > get_datetime(nen) + timedelta(seconds=DUNG_SAI_GIAY)


def _dong_bo_tep(business_doctype, business_name, t, nguoi, token):
    """Mot tep cua `dong_bo_phieu`. Tra ve "tai_moi" / "ghi_de" / "tach_rieng" / "giu_ban_song".
    Nem loi ra ngoai - `dong_bo_phieu` ghi log tung tep."""
    lien = _lien_ket_cua_phieu(business_doctype, business_name, t.file_url)
    cach = "tai_moi"
    item_id = None
    if lien and lien.get("sp_item_id"):
        if not _tep_da_doi(lien, t):
            # Ban song giu nguyen; chi cap quyen cho nguoi trong luong hien tai.
            r = cap_quyen(lien.get("sp_item_id"), nguoi, token=token)
            _ghi_quyen(lien.get("name"), r)
            return "giu_ban_song"
        if _ban_song_da_sua(lien, token):
            cach = "tach_rieng"
        else:
            cach, item_id = "ghi_de", lien.get("sp_item_id")
    kq = tai_len(business_doctype, t.file_url, t.file_name, business_name, token=token,
                 item_id=item_id)
    # Cap quyen TRUOC khi ghi lien ket: ghi lien ket la thu bao "tep nay mo online duoc", ma
    # tep chua cap quyen thi nguoi bam vao se an 403 cua SharePoint.
    r = cap_quyen(kq["item_id"], nguoi, token=token)
    ghi_lien_ket(business_doctype, t.file_url, business_name, kq, r["da_cap"],
                 share_url=r.get("link"))
    if cach == "tach_rieng":
        frappe.log_error(
            "Phieu %s gui lai voi tep %s DA DOI trong Frappe, nhung ban tren SharePoint (%s) da "
            "co nguoi sua sau lan tai len truoc. Ban song GIU NGUYEN; ban moi tai len thanh tep "
            "rieng %s." % (business_name, t.file_name, lien.get("sp_item_id"), kq.get("web_url")),
            "SharePoint gui lai - giu ban song")
    return cach


def dong_bo_nen(business_doctype, business_name):
    """Diem vao cho `frappe.enqueue`. Phai la ham CAP MODULE thi enqueue moi tro toi duoc.

    Bat HET loi: day la viec chay nen sau khi nguoi dung da gui phieu xong. Hong thi ghi log de
    sua, tuyet doi khong nem nguoc ra - mot su co mang cua Microsoft khong duoc phep lam hong
    mot lan gui phieu da thanh cong.
    """
    try:
        return dong_bo_phieu(business_doctype, business_name)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "SharePoint soi guong nen %s" % business_name)
        return None


def dong_bo_mot_tep(business_doctype, business_name, file_url):
    """Dua DUNG MOT tep (vua duoc nguoi xu ly them o buoc duyet - `requests/add_file.py`) len
    SharePoint, cap quyen cho ca luong, ghi lien ket. Tra ve dict tong ket.

    KHAC `dong_bo_phieu` o cho KHONG dung toi tep nao khac cua phieu: tep da co tren SharePoint
    la ban SONG, nguoi duyet sua/comment truc tiep - tai lai la xoa sach cong cua ho (cung ly do
    voi `cap_bu_link`). Hai lop chan:
      1. tep nay DA co lien ket SharePoint -> bo qua (goi lai / job chay hai lan khong ghi de);
      2. mot dinh kem KHAC cua phieu trung ten sau khi lam sach -> bo qua + ghi log. (Tu
         03/11/2026 `tai_len` da khong bao gio ghi de theo duong dan - trung ten thi doi ten -
         nhung van bo qua o day de khong sinh "HopDong (2).docx" canh ban dang duoc duyet.)
    """
    if not duoc_soi_guong_phieu(business_doctype, business_name):
        return {"bo_qua": "loai phieu / phieu nay khong duoc dua len SharePoint"}
    if frappe.db.get_value(LINK_DT, {"file_url": file_url, "business_doctype": business_doctype,
                                     "business_name": business_name}, "sp_item_id"):
        return {"bo_qua": "tep da co tren SharePoint - khong tai lai"}
    tep = frappe.get_all(
        "File",
        filters={"attached_to_doctype": business_doctype, "attached_to_name": business_name},
        fields=["file_name", "file_url"], order_by="creation asc")
    cua_tep = [t for t in tep if t.file_url == file_url]
    if not cua_tep:
        return {"bo_qua": "tep khong thuoc phieu nay"}
    t = cua_tep[0]
    ten = wr_sp.safe_filename(t.file_name).lower()
    if any(wr_sp.safe_filename(k.file_name).lower() == ten for k in tep if k.file_url != file_url):
        frappe.log_error("Trung ten %s tren phieu %s - khong tai len de khoi ghi de tep cu"
                         % (t.file_name, business_name), "SharePoint them tep - trung ten")
        return {"bo_qua": "trung ten voi tep khac cua phieu"}
    token = wr_sp.get_app_token()
    kq = tai_len(business_doctype, t.file_url, t.file_name, business_name, token=token)
    r = cap_quyen(kq["item_id"], nguoi_trong_luong(business_doctype, business_name), token=token)
    ghi_lien_ket(business_doctype, t.file_url, business_name, kq, r["da_cap"],
                 share_url=r.get("link"))
    return {"xong": [t.file_name]}


def dong_bo_mot_tep_nen(business_doctype, business_name, file_url):
    """Diem vao `frappe.enqueue` cho `dong_bo_mot_tep`. Nuot HET loi (xem `dong_bo_nen`)."""
    try:
        return dong_bo_mot_tep(business_doctype, business_name, file_url)
    except Exception:
        frappe.log_error(frappe.get_traceback(),
                         "SharePoint them tep nen %s / %s" % (business_name, file_url))
        return None


#: Chi quet phieu CON DANG CHO DUYET. Phieu da xong thi khong con ai duyet de ma canh bao,
#: va quet ca bang moi gio chi de goi Graph cho nhung ho so khong ai doc nua la lang phi.
TRANG_THAI_CON_CHO = ("Pending", "Information Required")


def lam_tuoi_moc_sua():
    """Doc lai `lastModifiedDateTime` tu SharePoint cho cac phieu CON CHO DUYET.

    VI SAO CAN. Bang canh bao "tep doi sau khi duyet" doc `sp_last_modified`, ma truoc dot nay
    KHONG CO GI cap nhat truong do sau luc tai len - `doc_moc_sua` duoc viet ra roi khong ai
    goi. Nghia la tinh nang sai ca hai chieu: bao nham voi moi phieu dong bo sau khi da co cap
    duyet, va KHONG BAO GIO bat duoc mot lan sua that tren Word Online.

    Chi cap nhat `sp_last_modified`, TUYET DOI khong dung toi `sp_uploaded_at`: moc nen phai
    giu nguyen thi phep so moi con y nghia.

    Nuot loi tung ban ghi: mot tep bi xoa tay tren SharePoint khong duoc lam chet ca lan quet.
    """
    if not frappe.db.exists("DocType", LINK_DT):
        return {"bo_qua": "chua co DocType lien ket"}
    rows = frappe.get_all(
        LINK_DT, filters={"sp_item_id": ["is", "set"]},
        fields=["name", "business_doctype", "business_name", "sp_item_id"],
        limit_page_length=0)
    if not rows:
        return {"so_ban_ghi": 0}
    token, doi, loi = None, 0, 0
    for r in rows:
        try:
            req = frappe.db.get_value(r.business_doctype, r.business_name, "approval_request")
            if not req:
                continue
            tt = frappe.db.get_value("EC Approval Request", req, "approval_status")
            if tt not in TRANG_THAI_CON_CHO:
                continue
            token = token or wr_sp.get_app_token()
            moc = doc_moc_sua(r.sp_item_id, token=token)
            if moc:
                frappe.db.set_value(LINK_DT, r.name, "sp_last_modified", moc,
                                    update_modified=False)
                doi += 1
        except Exception:
            loi += 1
            frappe.log_error(frappe.get_traceback(), "lam tuoi moc sua %s" % r.name)
    return {"so_ban_ghi": len(rows), "da_cap_nhat": doi, "hong": loi}


def cap_bu_link(ten_ban_ghi, token=None):
    """Lay link chia se cho MOT ban ghi cu. CHI goi `cap_quyen`, TUYET DOI KHONG tai tep len lai.

    Ban tren SharePoint la ban SONG: nguoi duyet sua va comment truc tiep tren do (Hoan chot).
    `tai_len` ghi de bang ban cua Frappe, tuc xoa sach moi chinh sua cua ho - nen cap bu tuyet
    doi khong duoc di qua `dong_bo_phieu`.

    `createLink` voi cung type + scope tra ve link DA CO neu co, nen goi lai la an toan: cung
    nhung nguoi do, cung mot link. Danh sach nguoi doc lai tu luong duyet HIEN TAI, nen ai moi
    duoc them vao cap duyet sau lan dong bo dau cung duoc cap luon.
    """
    doc = frappe.get_doc(LINK_DT, ten_ban_ghi)
    if not doc.sp_item_id:
        return {"bo_qua": "khong co sp_item_id"}
    nguoi = nguoi_trong_luong(doc.business_doctype, doc.business_name)
    r = cap_quyen(doc.sp_item_id, nguoi, token=token)
    _ghi_quyen(doc, r)
    return {"link": bool(r.get("link")), "da_cap": len(r.get("da_cap") or [])}


def _ghi_quyen(doc_or_name, r):
    """Ghi ket qua `cap_quyen` vao ban ghi lien ket. KHONG dung toi moc nen / moc sua: day
    khong phai mot lan tai len. Lan cap quyen khong tra link thi GIU link cu."""
    doc = doc_or_name if hasattr(doc_or_name, "save") else frappe.get_doc(LINK_DT, doc_or_name)
    if r.get("link"):
        doc.sp_share_url = r["link"]
    if r.get("da_cap"):
        doc.sp_granted_to = ", ".join(r["da_cap"])
    doc.save(ignore_permissions=True)


def cap_bu_link_nen():
    """Diem vao cho `frappe.enqueue` tu patch p204. Moi ban ghi mot lan thu, hong thi ghi log va
    di tiep - mot tep loi khong duoc keo ca lo dung lai. Commit sau MOI ban ghi: viec nay goi
    Graph, cham; hong giua chung thi nhung ban da xong van phai con."""
    ten = frappe.get_all(LINK_DT, filters={"sp_item_id": ["is", "set"]}, pluck="name") or []
    xong, hong = 0, []
    try:
        token = wr_sp.get_app_token()
    except Exception:
        frappe.log_error(frappe.get_traceback(), "cap bu link SharePoint: khong lay duoc token")
        return
    for t in ten:
        try:
            cap_bu_link(t, token=token)
            frappe.db.commit()
            xong += 1
        except Exception:
            frappe.db.rollback()
            frappe.log_error(frappe.get_traceback(), "cap bu link SharePoint %s" % t)
            hong.append(t)
    frappe.log_error("cap bu link SharePoint: %d/%d xong, hong: %s" % (xong, len(ten), hong or "(khong)"),
                     "cap bu link SharePoint - tong ket")
