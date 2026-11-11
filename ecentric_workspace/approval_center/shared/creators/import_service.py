# Copyright (c) 2026, eCentric and contributors
"""Nhap creator tu sheet cu "TOOL TAO HDDV & BBNT" (tab CREATOR MASTER, ~354 dong).

Chay thu mac dinh (apply=False): kiem tung dong, khong ghi gi. apply=True moi tao.
Moi dong di qua DUNG CreatorService.prepare + do trung + insert_prepared nhu tren form:
  * trung CUNG (CCCD/MST/STK da co tren ERP hoac o dong truoc trong file) -> bo qua;
  * trung MEM (ten/SDT/TikTok/Shopee)  -> BO QUA, bao lai (QC 11/11: tao luon thi chay lai
    lan hai la nhan doi moi creator khong co CCCD/MST/STK). Nguoi khac that thi tao tay tren form;
  * thieu du lieu bat buoc             -> bao loi, khong tao.
Chi EC Finance / System Manager duoc chay. Ket qua KHONG chua CCCD/STK.
"""
import datetime as _dt
import re
import unicodedata

from ecentric_workspace.approval_center.shared.creators import domain
from ecentric_workspace.approval_center.shared.creators.service import CreatorError, CreatorService

MAX_ROWS = 500
TYPE_MAP = {"ca nhan": "Cá nhân", "individual": "Cá nhân", "cong ty": "Công ty",
            "company": "Công ty", "ho kinh doanh": "Hộ kinh doanh", "hkd": "Hộ kinh doanh"}
# cot sheet (da chuan hoa: bo dau, ha chu, '_') -> truong Supplier
COLUMN_MAP = {
    "supplier_name": ("full_name_or_legal_name", "full_name", "ho_ten", "ten", "ten_creator",
                      "ten_phap_nhan", "creator_name"),
    "ec_cr_type": ("creator_type", "loai", "loai_creator", "type"),
    "ec_cr_party_code": ("party_code", "ma_viet_tat", "ma_doi_tac", "code"),
    "ec_cr_tiktok_id": ("tiktok_id", "id_tiktok", "tiktok"),
    "ec_cr_channel_url": ("channel_url", "link_kenh", "tiktok_url", "link_tiktok"),
    "ec_cr_shopee_id": ("shopee_id", "id_shopee"),
    "ec_cr_shopee_url": ("shopee_channel_url", "shopee_url", "link_shopee"),
    "ec_cr_email": ("email",),
    "ec_phone": ("phone", "sdt", "so_dien_thoai"),
    "ec_cr_cccd": ("cccd", "so_cccd", "cmnd", "cccd_cmnd"),
    "ec_cr_cccd_issue_date": ("cccd_issue_date", "ngay_cap"),
    "ec_cr_cccd_issue_place": ("cccd_issue_place", "noi_cap"),
    "ec_cr_dob": ("dob", "ngay_sinh"),
    "ec_cr_address": ("address", "dia_chi"),
    "tax_id": ("tax_id", "mst", "ma_so_thue"),
    "ec_cr_representative_name": ("representative_name", "nguoi_dai_dien"),
    "ec_cr_representative_title": ("representative_title", "chuc_vu"),
    "ec_cr_account_holder": ("account_holder", "chu_tai_khoan", "ten_tai_khoan"),
    "ec_bank_account_no": ("account_no", "so_tai_khoan", "stk"),
    "ec_bank_name": ("bank", "ngan_hang", "bank_name"),
    "ec_cr_bank_branch": ("bank_branch", "chi_nhanh"),
    "ec_cr_cccd_front": ("cccd_front_link", "cccd_mat_truoc", "anh_cccd_truoc"),
    "ec_cr_cccd_back": ("cccd_back_link", "cccd_mat_sau", "anh_cccd_sau"),
    "ec_cr_misa_code": ("misa_code", "ma_khach_hang", "ma_kh", "ma_misa"),
}
DATE_FIELDS = ("ec_cr_dob", "ec_cr_cccd_issue_date")
IGNORED = ("creator_key", "stt", "no", "ghi_chu", "note", "notes")


def header_key(text):
    text = unicodedata.normalize("NFD", str(text or "")).replace("đ", "d").replace("Đ", "D")
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn").lower()
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")


def _alias_index():
    return {alias: field for field, aliases in COLUMN_MAP.items() for alias in aliases}


def unmapped_headers(headers):
    index = _alias_index()
    return [h for h in headers if header_key(h) not in index and header_key(h) not in IGNORED]


def parse_date(value):
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return _dt.datetime.strptime(text[:10], fmt).date().isoformat()
        except ValueError:
            continue
    raise CreatorError("Ngày không đọc được: %s (cần dd/mm/yyyy)." % text)


def map_row(row):
    index = _alias_index()
    data = {}
    for header, value in (row or {}).items():
        field = index.get(header_key(header))
        text = str(value if value is not None else "").strip()
        if field and text and field not in data:
            data[field] = text
    if "ec_cr_type" in data:
        data["ec_cr_type"] = TYPE_MAP.get(header_key(data["ec_cr_type"]).replace("_", " "),
                                          data["ec_cr_type"])
    for field in DATE_FIELDS:
        if data.get(field):
            data[field] = parse_date(data[field])
    return data


def import_rows(user, rows, apply=False, service=None):
    service = service or CreatorService()
    service.require_finance(user)
    rows = list(rows or [])
    if len(rows) > MAX_ROWS:
        raise CreatorError("Tối đa %d dòng mỗi lần nhập." % MAX_ROWS)
    known = list(service.repo.identity_rows())
    used_misa = set()
    out = {"apply": bool(apply), "total": len(rows), "created": 0, "would_create": 0,
           "duplicate": 0, "soft_duplicate": 0, "errors": 0,
           "unmapped_headers": unmapped_headers(rows[0].keys()) if rows else [], "rows": []}
    for idx, raw in enumerate(rows, start=2):  # dong 1 cua file la tieu de
        item = {"line": idx}
        try:
            data = map_row(raw)
            misa = data.pop("ec_cr_misa_code", None)
            item["name"] = data.get("supplier_name", "")
            values = service.prepare(data)
            dup = domain.classify_duplicates(values, known)
            if dup["hard"]:
                out["duplicate"] += 1
                item.update(status="trung", existing=dup["hard"][0]["name"] or "(dòng trước)",
                            matched=[domain.KEY_LABELS[f] for f in dup["hard"][0]["matched"]])
                out["rows"].append(item)
                continue
            if dup["soft"]:
                out["soft_duplicate"] += 1
                item.update(status="trung_mem", soft=[m["name"] or "(dòng trước)" for m in dup["soft"]],
                            message="Có thể đã có: " + "; ".join(domain.describe_match(m) for m in dup["soft"])
                            + ". Bỏ qua; nếu đúng là người khác, tạo tay trên form.")
                out["rows"].append(item)
                continue
            if misa:
                if misa in used_misa or service.repo.misa_owner(misa, ""):
                    raise CreatorError("Mã MISA %s đã gán cho creator khác." % misa)
                used_misa.add(misa)
                values["ec_cr_misa_code"] = misa
            if apply:
                item["creator"] = service.insert_prepared(values, [])
                out["created"] += 1
                item["status"] = "da_tao"
            else:
                out["would_create"] += 1
                item["status"] = "se_tao"
            known.append(dict(values, name=item.get("creator") or "",
                              supplier_name=values.get("supplier_name")))
        except CreatorError as e:
            out["errors"] += 1
            item.update(status="loi", message=str(e))
        out["rows"].append(item)
    return out
