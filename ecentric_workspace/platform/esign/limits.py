# Copyright (c) 2026, eCentric and contributors
"""Gioi han KICH THUOC lenh AddDocument sang eContract (07/09).

EC-PAYR-2026-00044 (anh Dong, 6 PDF = 10,9 MB): AddDocument bi tu choi HTTP 413. Payload gui
MOI tep HAI LAN (PdfBase64 + OriginalBase64, dac ta noi ca hai la "Co"), base64 nang them
4/3 -> 10,9 MB thanh ~30,6 MB JSON. 30.000.000 byte dung bang MaxRequestBodySize mac dinh
cua ASP.NET Kestrel - khop voi con so do, khong phai ngau nhien.

[TEMP-WORKAROUND 2026-09-07 - gioi han suy ra tu mot lan 413, SCTS chua xac nhan]
Rui ro: neu SCTS nang/ha gioi han thi con so nay lech; hau qua chi la giu them/bot phu luc
tren ERP hoac mot lan 413 nua (co ma loi ro). Viec dung: hoi SCTS gioi han body va sua
SCTS_MAX_REQUEST_BYTES. Xem 03_BUGS_AND_NEXT_STEPS.md muc TEMP.

Quy tac dung o hai cho, CUNG MOT ham uoc luong:
  - luc gui (tasks._fit_payload_budget): vuot ngan -> bo phu luc lon nhat truoc, giu tren ERP
    (SupportingFileKeptInErp, ly do payload_budget); to trinh KHONG bao gio bo.
  - luc nguoi de nghi bam Gui (package.preflight_for_lock): rieng to trinh da vuot ngan ->
    tu choi ngay voi cau doc duoc (signable_too_large), vi khong co gi de bo nua.
"""

#: Kestrel MaxRequestBodySize mac dinh (byte). Do tu HTTP 413 ngay 07/09/2026.
SCTS_MAX_REQUEST_BYTES = 30_000_000
#: Phan JSON ngoai tep: fields, Signatures, headers... do rong tay (00043: < 20 KB).
_ENVELOPE_BYTES = 200_000
#: Chua 5% cho lech uoc luong / thay doi phia SCTS.
_SAFETY = 0.95


def payload_budget_bytes():
    return int(SCTS_MAX_REQUEST_BYTES * _SAFETY) - _ENVELOPE_BYTES


def payload_copies(settings):
    """So lan moi tep xuat hien trong payload: 2 (PdfBase64 + OriginalBase64) mac dinh; 1 khi
    Provider Settings bat `omit_original_base64` (thu nghiem 07/09, xem scts.create_document)."""
    get = settings.get if hasattr(settings, "get") else (lambda k, d=None: getattr(settings, k, d))
    return 1 if int(get("omit_original_base64") or 0) else 2


def payload_bytes_for(sizes, copies=2):
    """Uoc luong byte JSON cho danh sach kich thuoc tep (byte tho). Moi tep xuat hien
    `copies` lan, base64 = 4/3 (lam tron len theo khoi 3 byte)."""
    total = 0
    for n in sizes:
        n = int(n or 0)
        total += copies * (4 * ((n + 2) // 3))
    return total


def fits(sizes, copies=2):
    return payload_bytes_for(sizes, copies) <= payload_budget_bytes()


def raw_budget_mb(copies=2):
    return mb(payload_budget_bytes() * 3 // (4 * copies))


def mb(n):
    return "%.1f MB" % (float(n or 0) / 1048576.0)
