# Copyright (c) 2026, eCentric and contributors
"""Anh tai len -> JPG chuan may cham cong. KHONG import frappe (test chay khong can bench)."""
import io

from ecentric_workspace.hr.face_photo import constants as C


class PhotoError(ValueError):
    """Loi nguoi dung sua duoc (anh hong, qua nho...). Thong diep tieng Viet."""


def prepare(raw):
    """bytes anh bat ky (JPG/PNG/HEIC da doi o trinh duyet) -> (jpeg_bytes, (w, h))."""
    from PIL import Image, ImageOps
    if not raw:
        raise PhotoError("Chưa có ảnh.")
    if len(raw) > C.MAX_UPLOAD_BYTES:
        raise PhotoError("Ảnh quá lớn (tối đa 12 MB). Chụp lại hoặc chọn ảnh khác.")
    try:
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise PhotoError("Không đọc được ảnh. Hãy chụp lại bằng camera hoặc chọn ảnh JPG/PNG.")
    img = ImageOps.exif_transpose(img)          # anh dien thoai hay bi xoay
    if img.mode != "RGB":
        img = img.convert("RGB")
    w, h = img.size
    if min(w, h) < C.MIN_SIDE:
        raise PhotoError("Ảnh quá nhỏ (%dx%d). Cần ảnh rõ mặt, cạnh ngắn ít nhất %d px." % (w, h, C.MIN_SIDE))
    scale = min(1.0, float(C.MAX_SIDE) / max(w, h))
    for _ in range(6):
        cur = img if scale >= 1.0 else img.resize((max(1, int(w * scale)), max(1, int(h * scale))),
                                                  Image.LANCZOS)
        for q in (90, 85, 80, 72, 65, 58, 50):
            buf = io.BytesIO()
            cur.save(buf, "JPEG", quality=q, optimize=True)
            if buf.tell() <= C.TARGET_BYTES:
                return buf.getvalue(), cur.size
        scale *= 0.8
    raise PhotoError("Không nén được ảnh xuống dưới 200 KB. Hãy chụp lại.")
