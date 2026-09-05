# Copyright (c) 2026, eCentric and contributors
"""Dua MOI tep trong goi ky ve PDF THAT truoc khi gui nha cung cap.

Vi sao (05/09, EC-PAYR-2026-00042 / chung tu e8fcc8a0): chi Hien dinh kem `p-mob.png` lam
phu luc. `create_document` gui no cho eContract voi `FileType: "pdf"` va `PdfBase64` = byte
PNG. AddDocument nhan (2xx, chung tu co 2 tep), lenh Trinh ky nhan (2xx) - roi eContract
KHONG lam gi: khong chu ky, task van "Cho gui di", 20 phut sau Manual Review
`provider_accepted_but_silent`. Cung code, cung nguoi, cung token, cung nguoi nhan, phieu
00053 hom truoc (chi mot PDF) ky xong trong 3 giay. Khac biet duy nhat: mot tep "pdf" khong
phai PDF.

eContract chi tung duoc chung minh la chay voi PDF that (12 chan duyet + 00053). Nen:

  - PDF that  -> giu nguyen.
  - Anh PNG/JPEG -> ve thanh mot PDF mot trang (Pillow, co san trong Frappe). Ban goc VAN
    la File cua phieu va van bam vao package_hash; chi ban gui di la ban ve lai.
  - Con lai (docx, xlsx, ...) -> `UnrenderableFile`. Tep CAN KY thi preflight da chan tu
    truoc (signable_not_pdf). Tep BO CHUNG TU thi tasks._provider_file GIU LAI TREN ERP,
    khong gui (su kien SupportingFileKeptInErp) - bang chung van o phieu, cap duyet xem tren
    ERP; chi ban PDF ky moi can sang nha cung cap. Tot hon ca hai: bat nguoi de nghi doi
    Excel sang PDF, hay mot lenh 2xx roi im lang.

Adapter SCTS con mot chot cuoi: byte khong bat dau bang %PDF- thi KHONG gui (xem
scts.create_document). Hai lop, vi lop sau la lop ma nguoi doc payload nhin thay.
"""
import io
import os

PDF_MAGIC = b"%PDF"
#: Chu ky bytes cua cac dinh dang anh ve duoc. Khong doan theo duoi ten tep.
_IMAGE_MAGICS = (
    (b"\x89PNG\r\n\x1a\n", "png"),
    (b"\xff\xd8\xff", "jpeg"),
)


class UnrenderableFile(Exception):
    """Tep khong phai PDF va khong phai anh ve duoc."""


def kind_of(content):
    """'pdf' | 'png' | 'jpeg' | None - theo BYTE, khong theo ten."""
    head = bytes(content[:8] or b"")
    if head.startswith(PDF_MAGIC):
        return "pdf"
    for magic, kind in _IMAGE_MAGICS:
        if head.startswith(magic):
            return kind
    return None


def is_renderable_mime(mime_type):
    """Loai tep ve duoc thanh PDF (theo mime da luu tren DSF, khi khong co byte)."""
    return str(mime_type or "").lower() in ("application/pdf", "image/png", "image/jpeg")


#: Tep se sang nha cung cap duoi dang nao. "erp_only" = chi luu tren ERP, KHONG gui.
DELIVERY_AS_IS, DELIVERY_RENDERED, DELIVERY_ERP_ONLY = "as_is", "rendered_pdf", "erp_only"


def delivery_for_name(file_name, requires_signature=False):
    """Doan theo ten (cho man hinh, truoc khi co byte). Byte moi la quyet dinh cuoi
    (`to_pdf`), nhung nguoi de nghi can biet TRUOC khi gui: to trinh di nguyen, anh di dang
    PDF ve lai, con bang tinh/word chi nam tren ERP."""
    ext = os.path.splitext(str(file_name or ""))[1].lower()
    if ext == ".pdf":
        return DELIVERY_AS_IS
    if ext in (".png", ".jpg", ".jpeg"):
        return DELIVERY_RENDERED
    return DELIVERY_ERP_ONLY


def pdf_file_name(file_name):
    base = os.path.splitext(str(file_name or "tep"))[0] or "tep"
    return base + ".pdf"


def flatten_to_rgb(im):
    """Anh RGB khong alpha de in ra PDF. Vung trong suot -> TRANG (khong de Pillow tu bo
    alpha: bo alpha = vung trong suot thanh den, anh chup man hinh nen trong thanh mot khoi
    den)."""
    from PIL import Image
    if im.mode in ("RGBA", "LA", "P"):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, (255, 255, 255))
        bg.paste(rgba, mask=rgba.getchannel("A"))
        return bg
    if im.mode != "RGB":
        return im.convert("RGB")
    return im.copy()


def to_pdf(content, file_name=None):
    """(pdf_bytes, converted). PDF that -> (content, False). Anh -> (PDF mot trang, True).
    Khac -> UnrenderableFile."""
    kind = kind_of(content)
    if kind == "pdf":
        return content, False
    if kind is None:
        raise UnrenderableFile("tep %r khong phai PDF hay anh PNG/JPEG" % (file_name or "?"))
    from PIL import Image                      # Frappe phu thuoc Pillow; khong them dependency
    with Image.open(io.BytesIO(content)) as im:
        im.load()
        rgb = flatten_to_rgb(im)
    buf = io.BytesIO()
    # 96 dpi: anh chup man hinh 1080px ~ 28 cm, vua mot trang; SCTS chi can mo duoc.
    rgb.save(buf, format="PDF", resolution=96.0)
    out = buf.getvalue()
    if not out.startswith(PDF_MAGIC):
        raise UnrenderableFile("ve %r thanh PDF that bai" % (file_name or "?"))
    return out, True
