# Copyright (c) 2026, eCentric and contributors
"""Asset cua trang huong dan (public/guides/ + public/vendor/mermaid/) va dau `?v=` trong trang.

Frappe Cloud phuc vu /assets/* voi `Cache-Control: max-age=31536000, immutable`: duong dan
khong doi thi trinh duyet giu ban cu MOT NAM. Moi the tro vao cac asset nay mang
`?v=<10 ky tu dau sha256 noi dung>`; doi file -> doi ?v= -> doi HTML trang -> patch resync +
resync_manifest.json. Test: guides/tests/test_guide_assets.py bat moi ?v= lech.

    python -m ecentric_workspace.guides.assets --check
    python -m ecentric_workspace.guides.assets --stamp
(Cung cach voi dao_tao/pages/assets.py va alerts/site_pages/assets.py.)
"""
import glob
import hashlib
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(_HERE)
PUBLIC_DIR = os.path.join(APP_DIR, "public")
PAGES_DIR = os.path.join(_HERE, "pages")
ASSET_REF = re.compile(
    r'(/assets/ecentric_workspace/((?:guides|vendor/mermaid)/[A-Za-z0-9_.-]+))\?v=([0-9a-f]*)')


def version(fname):
    with io.open(os.path.join(PUBLIC_DIR, fname), "rb") as fh:
        raw = fh.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()[:10]


def stale(html):
    out = []
    for m in ASSET_REF.finditer(html):
        fname, have = m.group(2), m.group(3)
        if not os.path.isfile(os.path.join(PUBLIC_DIR, fname)):
            out.append((fname, have, None))
        elif have != version(fname):
            out.append((fname, have, version(fname)))
    return out


def stamp(html):
    return ASSET_REF.sub(lambda m: "%s?v=%s" % (m.group(1), version(m.group(2))), html)


def page_paths():
    """Moi trang huong dan co nap asset cua module (quet, khong liet ke tay)."""
    out = []
    for p in sorted(glob.glob(os.path.join(PAGES_DIR, "*", "main_section.html"))):
        with io.open(p, encoding="utf-8") as fh:
            if ASSET_REF.search(fh.read()):
                out.append(p)
    return out


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    bad = 0
    for path in page_paths():
        with io.open(path, encoding="utf-8", newline="") as fh:
            html = fh.read()
        issues = stale(html)
        key = os.path.basename(os.path.dirname(path))
        if "--stamp" in argv and issues:
            with io.open(path, "w", encoding="utf-8", newline="") as fh:
                fh.write(stamp(html))
            print("STAMPED %s" % key)
        elif issues:
            bad += 1
            print("STALE   %s: %s" % (key, issues))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
