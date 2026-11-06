# Copyright (c) 2026, eCentric and contributors
"""AI soi anh khuon mat truoc khi luu (ec-face-photo-v2, 05/11/2026).

Hoan chot 05/11: anh hong -> CHAN, bao ly do tieng Viet de chup lai; anh lech nhung du mat ->
TU CAT cho mat vao giua (kieu anh the 4:5). AI loi / cham / tat -> VAN NHAN anh, danh dau
"chua kiem" cho HR xem. Nguoi dung bi chan 2 lan van thay anh dung -> duoc gui kem "nho HR xem".

KHONG import frappe (test chay khong can bench): `generate` duoc truyen vao.
Chi model Gemini nhan tep anh (dialects.ACCEPTS_FILES) - gateway tu bo qua model khac.
"""

PURPOSE = "face_photo_check"
BUDGET = 25            # nguoi dung dang doi tren trang
# fast=True (06/11): goi SONG SONG cac model Gemini nhan anh, model nao xong truoc thi dung.
# Truoc do goi lan luot: gemini-3-8-flash treo 15s -> het ngan sach -> ~45% anh "chua kiem".
ATTEMPT_TIMEOUT = 15

FACE_RATIO = 0.45      # chieu cao mat / chieu cao anh sau khi cat (anh the)
FACE_CENTER_Y = 0.45   # tam mat nam o 45% tu tren xuong (chua cho vai)
ASPECT = 0.8           # rong / cao = 4:5
MIN_FACE_PX = 80       # mat nho hon -> may khong nhan duoc

FLAGS = ("face_cut_off", "frontal", "eyes_open", "mask", "sunglasses", "covered", "blurry",
         "too_dark", "photo_of_screen", "heavy_filter")

SCHEMA = {
    "type": "object",
    "properties": {
        "faces": {"type": "integer"},
        "top": {"type": "integer"}, "left": {"type": "integer"},
        "bottom": {"type": "integer"}, "right": {"type": "integer"},
        "face_cut_off": {"type": "boolean"}, "frontal": {"type": "boolean"},
        "eyes_open": {"type": "boolean"}, "mask": {"type": "boolean"},
        "sunglasses": {"type": "boolean"}, "covered": {"type": "boolean"},
        "blurry": {"type": "boolean"}, "too_dark": {"type": "boolean"},
        "photo_of_screen": {"type": "boolean"}, "heavy_filter": {"type": "boolean"},
        "note": {"type": "string"},
    },
    "required": ["faces", "top", "left", "bottom", "right"] + list(FLAGS),
}

SYSTEM = (
    "You check ONE photo an employee submits to enrol in a face-recognition door / attendance "
    "terminal. Reply JSON only.\n"
    "faces = number of REAL people's faces visible in the photo (include people in the background; "
    "do not count faces on posters, screens or prints).\n"
    "top, left, bottom, right = bounding box of the MAIN face (largest / closest), integers 0-1000 "
    "relative to the image height (top, bottom) and width (left, right). The box covers forehead "
    "hairline to chin and ear to ear, not hair or neck. If faces = 0 put 0 in all four.\n"
    "face_cut_off = part of the main face (forehead, chin, mouth or one side) is outside the image.\n"
    "frontal = the person faces the camera roughly straight: head turned, tilted or bowed less than "
    "about 25 degrees, both eyes visible.\n"
    "eyes_open = both eyes open.\n"
    "mask = a face mask covers nose or mouth.\n"
    "sunglasses = dark or tinted glasses hide the eyes. NORMAL CLEAR EYEGLASSES ARE FINE -> false.\n"
    "covered = a hat, hand, hair, phone or object hides the eyebrows, eyes, nose or mouth.\n"
    "blurry = the face is too blurry to see the eyes clearly.\n"
    "too_dark = the face is too dark or strongly backlit to see its features.\n"
    "photo_of_screen = this is a photo of a screen or of a printed photo, not a live photo.\n"
    "heavy_filter = beauty filter, sticker, cartoon or AR effect on the face.\n"
    "Be fair: mark a problem only when it is clearly present. note = a few English words."
)

MSG = {
    "no_face": "Không thấy khuôn mặt nào trong ảnh. Chụp lại, nhìn thẳng vào camera.",
    "many": "Ảnh có hơn một người. Chụp lại, chỉ có mình bạn trong khung.",
    "face_cut_off": "Mặt bị cắt mất một phần (ra ngoài khung). Lùi ra hoặc nâng camera để cả khuôn mặt nằm trong khung.",
    "frontal": "Hãy nhìn thẳng vào camera, không quay, nghiêng hay cúi đầu.",
    "eyes_open": "Mắt đang nhắm. Mở mắt nhìn thẳng vào camera rồi chụp lại.",
    "mask": "Tháo khẩu trang rồi chụp lại.",
    "sunglasses": "Tháo kính râm / kính màu rồi chụp lại (kính cận thường thì vẫn được).",
    "covered": "Mặt đang bị che (mũ, tay, tóc…). Để lộ rõ lông mày, mắt, mũi, miệng rồi chụp lại.",
    "blurry": "Ảnh bị mờ. Giữ yên máy rồi chụp lại.",
    "too_dark": "Mặt quá tối hoặc ngược sáng. Quay mặt về phía cửa sổ / đèn rồi chụp lại.",
    "photo_of_screen": "Đây là ảnh chụp lại từ màn hình / ảnh in. Hãy chụp trực tiếp bằng camera.",
    "heavy_filter": "Ảnh có filter / hiệu ứng. Chụp ảnh thường, không filter.",
    "small": "Mặt quá nhỏ trong ảnh. Lại gần camera hơn rồi chụp lại.",
}
# frontal / eyes_open: True moi la TOT; cac co khac True la LOI.
GOOD_WHEN_TRUE = ("frontal", "eyes_open")


def _flag(v):
    """Model co the tra chuoi "false" -> bool("false") = True. Khong ro -> None."""
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no", ""):
        return False
    return None


def _int(v):
    try:
        return int(round(float(v)))
    except (TypeError, ValueError):
        return None


def ask(jpeg, generate):
    """-> dict tu model, hoac None khi AI khong tra loi duoc (khong bao gio raise)."""
    try:
        res = generate("Check this enrolment photo.", system=SYSTEM, schema=SCHEMA,
                       files=[{"data": jpeg, "mime_type": "image/jpeg"}], purpose=PURPOSE,
                       budget=BUDGET, attempt_timeout=ATTEMPT_TIMEOUT, fast=True)
    except Exception:
        return None
    data = (res or {}).get("data") if (res or {}).get("ok") else None
    if not isinstance(data, dict) or _int(data.get("faces")) is None:
        return None
    return data


def box_of(data):
    """-> (top, left, bottom, right) 0..1 hoac None neu khung vo ly."""
    v = [_int(data.get(k)) for k in ("top", "left", "bottom", "right")]
    if None in v:
        return None
    t, l, b, r = [min(1000, max(0, x)) / 1000.0 for x in v]
    if b - t < 0.03 or r - l < 0.03 or (b - t) * (r - l) > 0.95:
        return None
    return t, l, b, r


def decide(data):
    """-> (problems: [thong diep tieng Viet], box 0..1 | None)."""
    faces = _int(data.get("faces")) or 0
    if faces <= 0:
        return [MSG["no_face"]], None
    problems = []
    if faces > 1:
        problems.append(MSG["many"])
    for k in FLAGS:
        f = _flag(data.get(k))
        if f is None:
            continue
        bad = (not f) if k in GOOD_WHEN_TRUE else f
        if bad:
            problems.append(MSG[k])
    return problems, box_of(data)


def crop_rect(box, w, h, min_side):
    """Khung mat 0..1 + kich thuoc anh goc -> (x0, y0, x1, y1) pixel, anh 4:5 mat o giua.

    Mat qua sat mep -> khung truot vao trong (mat lech mot chut van hon cat mat mat).
    Anh goc khong du rong -> thu nho ca khung, giu ty le.
    """
    t, l, b, r = box
    fh = (b - t) * h
    cx, cy = (l + r) / 2.0 * w, (t + b) / 2.0 * h
    ch = fh / FACE_RATIO
    ch = max(ch, min_side / ASPECT)          # canh ngan (rong) >= min_side neu anh cho phep
    cw = ch * ASPECT
    k = min(1.0, w / cw, h / ch)
    cw, ch = cw * k, ch * k
    x0 = min(max(0.0, cx - cw / 2.0), w - cw)
    y0 = min(max(0.0, cy - ch * FACE_CENTER_Y), h - ch)
    return int(round(x0)), int(round(y0)), int(round(x0 + cw)), int(round(y0 + ch))


def face_px(box, h):
    return (box[2] - box[0]) * h
