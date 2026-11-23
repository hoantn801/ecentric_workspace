# Copyright (c) 2026, eCentric and contributors
"""Doi chieu lop chu cua "Ban PDF de ky" voi phieu (hook ec_esign_document_verifiers, chot 18/11/2026
voi chat Ky so - THIETKE_ky_so_hop_dong muc 2e).

Vi sao. Tep ky do NGUOI LAP tu xuat tu Word (phuong an b) - sua duoc noi dung truoc khi xuat. Chot
toi thieu de khong ky nham: dung so hop dong (dung hop dong nay) + dung so tien tra creator da
duoc duyet. Cung tinh than may kiem ban ky (domain.kol.signed_pdf_findings), nhung truoc khi ky nen
KHONG dem chu ky so.

THUAN. Nguoi goi truyen: van ban (noi cac trang), tap con so trong van ban (kol_ai.number_tokens -
so khop NGUYEN con so: 5.000.000 khong "khop" 15.000.000).
"""
import re


def _squeeze(text):
    return re.sub(r"\s+", "", str(text or "")).lower()


def findings(text, tokens, contract_no=None, payable_digits=None, check_contract_no=True):
    """-> danh sach van de (rong = khop).

    contract_no: so HD tren phieu; PDF tach chu co the chen dau cach / xuong dong giua cac ky tu
      nen so khop sau khi bo moi khoang trang.
    payable_digits: so tien tra creator da lam tron, chi chu so ("9000000").
    check_contract_no=False: hop dong theo MAU CUA CREATOR - van ban do creator soan, khong co so
      HD cua ERP; chi doi chieu so tien.
    """
    out = []
    if not _squeeze(text):
        return ["Không đọc được chữ trong tệp - xuất lại bằng Word → Lưu thành PDF."]
    if check_contract_no:
        if not contract_no:
            out.append("Phiếu chưa có số hợp đồng - tạo hợp đồng từ mẫu trước.")
        elif _squeeze(contract_no) not in _squeeze(text):
            out.append("Không thấy số hợp đồng %s trong tệp - có thể tải nhầm tệp của hợp đồng khác."
                       % contract_no)
    if payable_digits and str(payable_digits) not in (tokens or set()):
        out.append("Không thấy số tiền trả creator %s trong tệp - số tiền trên tệp khác phiếu đã duyệt."
                   % format_digits(payable_digits))
    return out


def format_digits(digits):
    try:
        return "{:,}".format(int(digits)) + " đ"
    except (TypeError, ValueError):
        return str(digits)
