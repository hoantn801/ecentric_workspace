# Copyright (c) 2026, eCentric and contributors
"""Asset CSS/JS cua Khao sat (public/surveys/) va dau phien ban `?v=` trong 4 trang.

Frappe Cloud phuc vu /assets/* voi `Cache-Control: max-age=31536000, immutable` (do 29/09):
duong dan khong doi thi trinh duyet giu ban cu MOT NAM. Moi the tro vao public/surveys/ mang
`?v=<10 ky tu dau sha256 noi dung>`; doi file -> doi ?v= -> doi HTML trang -> patch resync +
resync_manifest.json. Test: surveys/tests/test_pages.py bat moi ?v= lech.

    python -m ecentric_workspace.surveys.pages.assets --check
    python -m ecentric_workspace.surveys.pages.assets --stamp
(Cung cach voi alerts/site_pages/assets.py.)
"""
import hashlib
import io
import os
import re
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.dirname(os.path.dirname(_HERE))
ASSET_DIR = os.path.join(APP_DIR, "public", "surveys")
PAGE_KEYS = ("hub", "fill", "manage", "builder")
ASSET_REF = re.compile(r'(/assets/ecentric_workspace/surveys/([A-Za-z0-9_.-]+))\?v=([0-9a-f]*)')


def version(fname):
    with io.open(os.path.join(ASSET_DIR, fname), "rb") as fh:
        raw = fh.read().replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()[:10]


def stale(html):
    out = []
    for m in ASSET_REF.finditer(html):
        fname, have = m.group(2), m.group(3)
        if not os.path.isfile(os.path.join(ASSET_DIR, fname)):
            out.append((fname, have, None))
        elif have != version(fname):
            out.append((fname, have, version(fname)))
    return out


def stamp(html):
    return ASSET_REF.sub(lambda m: "%s?v=%s" % (m.group(1), version(m.group(2))), html)


def page_path(key):
    return os.path.join(_HERE, key, "main_section.html")


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    bad = 0
    for key in PAGE_KEYS:
        with io.open(page_path(key), encoding="utf-8", newline="") as fh:
            html = fh.read()
        issues = stale(html)
        if "--stamp" in argv and issues:
            with io.open(page_path(key), "w", encoding="utf-8", newline="") as fh:
                fh.write(stamp(html))
            print("STAMPED %s" % key)
        elif issues:
            bad += 1
            print("STALE   %s: %s" % (key, issues))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
