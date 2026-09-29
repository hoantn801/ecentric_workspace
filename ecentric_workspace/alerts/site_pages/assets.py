# Copyright (c) 2026, eCentric and contributors
"""Asset CSS/JS cua Alert Center (public/alerts/) va dau phien ban `?v=` trong 5 trang.

VI SAO CAN `?v=`. Frappe Cloud phuc vu /assets/* voi `Cache-Control: max-age=31536000,
immutable` (do tren live 29/09/2026). Duong dan khong doi thi trinh duyet giu ban cu MOT NAM.
Nen moi the <script src> / <link href> tro vao public/alerts/ phai mang `?v=<10 ky tu dau
cua sha256 noi dung file>`; doi file -> doi `?v=` -> doi HTML trang -> bump BASELINE_SHA256 +
patch resync (resync_manifest bat buoc). Test alerts/tests/test_site_pages_nhieu_lop.py bat
moi `?v=` lech.

    python -m ecentric_workspace.alerts.site_pages.assets --check   # liet ke ?v= lech
    python -m ecentric_workspace.alerts.site_pages.assets --stamp   # ghi lai ?v= trong 5 trang
"""
import hashlib
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(os.path.dirname(_HERE))            # .../ecentric_workspace (package)
ASSET_DIR = os.path.join(APP_DIR, "public", "alerts")
URL_PREFIX = "/assets/ecentric_workspace/alerts/"
PAGE_KEYS = ("overview", "policies", "rules", "locks", "integration_health")

ASSET_REF = re.compile(r'(/assets/ecentric_workspace/alerts/([A-Za-z0-9_.-]+))\?v=([0-9a-f]*)')


def version(fname):
    """10 ky tu dau sha256 cua file asset (bytes, CRLF -> LF de Windows/Linux ra cung so)."""
    with io.open(os.path.join(ASSET_DIR, fname), "rb") as fh:
        raw = fh.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()[:10]


def refs(html):
    """[(ten file, ?v= dang ghi)] theo thu tu xuat hien."""
    return [(m.group(2), m.group(3)) for m in ASSET_REF.finditer(html)]


def stale(html):
    """[(ten file, dang ghi, phai la)] cho moi tham chieu lech hoac tro vao file khong ton tai."""
    out = []
    for fname, have in refs(html):
        if not os.path.isfile(os.path.join(ASSET_DIR, fname)):
            out.append((fname, have, None))
            continue
        want = version(fname)
        if have != want:
            out.append((fname, have, want))
    return out


def stamp(html):
    return ASSET_REF.sub(lambda m: "%s?v=%s" % (m.group(1), version(m.group(2))), html)


def page_path(key):
    return os.path.join(_HERE, key, "main_section.html")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    bad = 0
    for key in PAGE_KEYS:
        path = page_path(key)
        with io.open(path, encoding="utf-8", newline="") as fh:
            html = fh.read()
        issues = stale(html)
        if "--stamp" in argv and issues:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(stamp(html))
            print("STAMPED %s: %s" % (key, ", ".join("%s %s->%s" % i for i in issues)))
        elif issues:
            bad += 1
            print("STALE   %s: %s" % (key, ", ".join("%s %s->%s" % i for i in issues)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
