# Copyright (c) 2026, eCentric and contributors
"""Ho tro dung trang huong dan tu byte cua repo.

HAI cho thay the, ca hai lam LUC SYNC chu khong luc chay:
  * `{{img:<ten tep>}}`  -> anh chup man hinh nhung thang vao trang duoi dang data URI.
    Vi sao nhung chu khong tro toi /files: anh la MOT PHAN cua bai viet, phai di theo
    repo. Neu tro toi File tren site thi mot lan don dep tep la bai huong dan thung lo,
    va mot site moi (staging) se khong co anh nao - trong khi noi dung thi van bao "xem
    anh duoi day".
  * `{{guides_list}}`    -> danh sach bai tu guides.registry (mot cho khai duy nhat).

Trang huong dan KHONG co du lieu nghiep vu, nen khong dung khoa chong troi (expect_sha)
nhu cac form: nguon su that la repo, sync la ghi de. Dung sua tay tren Desk.
"""
import base64
import io
import os

from ecentric_workspace.guides import registry

_MIME = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png", ".svg": "image/svg+xml"}


def _esc(s):
    return (str(s or "").replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def embed_images(html, img_dir):
    """Thay {{img:x.jpg}} bang data URI. Thieu tep -> NEM LOI, khong de trang co o anh vo."""
    out = html
    while "{{img:" in out:
        i = out.index("{{img:")
        j = out.index("}}", i)
        name = out[i + 6:j].strip()
        path = os.path.join(img_dir, name)
        if not os.path.isfile(path):
            raise ValueError("guides: thieu anh %s (%s)" % (name, path))
        ext = os.path.splitext(name)[1].lower()
        mime = _MIME.get(ext)
        if not mime:
            raise ValueError("guides: duoi anh khong ho tro: %s" % name)
        with open(path, "rb") as fh:
            b64 = base64.b64encode(fh.read()).decode("ascii")
        out = out[:i] + "data:%s;base64,%s" % (mime, b64) + out[j + 2:]
    return out


def render_guides_list():
    """The danh sach bai cho trang muc luc - sinh tu registry, khong go tay."""
    cards = []
    for g in registry.listed():
        cards.append(
            '<a class="gcard" href="%s">'
            '<div class="gcard-t">%s</div>'
            '<div class="gcard-s">%s</div>'
            '<div class="gcard-m">%s · cập nhật %s</div>'
            '</a>' % (_esc(g["route"]), _esc(g["title"]), _esc(g["summary"]),
                      _esc(g.get("audience") or ""), _esc(g.get("updated") or "")))
    if not cards:
        return '<p class="empty">Chưa có hướng dẫn nào.</p>'
    return '<div class="gcards">%s</div>' % "".join(cards)


def build(page_dir, html_name="main_section.html"):
    """Doc main_section.html cua mot trang huong dan va tra ve HTML da thay the."""
    with io.open(os.path.join(page_dir, html_name), encoding="utf-8") as fh:
        html = fh.read()
    html = html.replace("{{guides_list}}", render_guides_list())
    return embed_images(html, os.path.join(page_dir, "img"))
