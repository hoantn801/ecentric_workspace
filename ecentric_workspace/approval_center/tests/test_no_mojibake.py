# Copyright (c) 2026, eCentric and contributors
"""QC gate: no mojibake (double-encoded Vietnamese) anywhere in the app source.

Mojibake happens when UTF-8 bytes are read as cp1252/latin-1 and re-saved as
UTF-8, so "Bạn" becomes "BÃ¡ÂºÂ¡n". It is not cosmetic: these strings are
`frappe.throw()` messages and status labels, so users saw garbage every time a
form failed validation. Worse, `_()` cannot match a corrupted msgid, so the
message is untranslatable as well.

Why a TEST and not a one-off cleanup: the corruption enters through a TOOL, not
through typing -- a PowerShell script that writes without an explicit UTF-8
encoding, an editor guessing the codepage, a paste through a terminal on the
wrong code page. Any of those silently re-corrupts a file that was just fixed,
which is how these 64 lines accumulated in the first place.

Detection is round-trip based, NOT a character blacklist: `Â`, `Ã` and `Ä` are
all legitimate Vietnamese ("Âm thanh", "NGÂN SÁCH"), so a blacklist produces
false positives. A line counts as mojibake only when re-reading it as cp1252
and decoding UTF-8 yields DIFFERENT, valid Vietnamese.

Run WITHOUT a bench:
  python3 -m unittest ecentric_workspace.approval_center.tests.test_no_mojibake
"""
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.path.dirname(os.path.dirname(HERE))          # .../ecentric_workspace

SCAN_EXT = (".py", ".js", ".html", ".json", ".md", ".css", ".txt")
SKIP_DIRS = {"__pycache__", "node_modules", "vendor", "pdfjs", ".git"}

#: files that legitimately CONTAIN mojibake because they exist to detect it
ALLOW = (
    os.path.join("shell", "tests", "test_legacy_pages_shell.py"),
    os.path.join("approval_center", "tests", "test_no_mojibake.py"),
)

# cp1252 has no byte 0x90 / 0x9D, so those halves of a UTF-8 sequence are
# destroyed rather than mangled and repair is not always reversible. DETECTION
# only needs the round-trip to change something, so that does not matter here.
_CP = []
for _b in range(256):
    try:
        _CP.append(bytes([_b]).decode("cp1252"))
    except Exception:
        _CP.append(None)
_REV = {c: b for b, c in enumerate(_CP) if c is not None}


def looks_like_mojibake(line):
    """True when the line decodes to different, valid text via cp1252 -> utf-8."""
    try:
        raw = bytes(_REV[c] for c in line)
    except KeyError:
        return False                      # holds chars cp1252 cannot represent
    try:
        decoded = raw.decode("utf-8")
    except UnicodeDecodeError:
        return False                      # not a re-encoded UTF-8 byte string
    if decoded == line:
        return False                      # pure ASCII / already correct
    # a real reversal yields Vietnamese; a coincidence yields control chars
    return any("À" <= ch <= "ỹ" for ch in decoded)


def scan():
    offenders = []
    for root, dirs, files in os.walk(APP):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if not f.endswith(SCAN_EXT):
                continue
            path = os.path.join(root, f)
            if any(path.endswith(a) for a in ALLOW):
                continue
            try:
                src = io.open(path, encoding="utf-8").read()
            except Exception:
                continue
            for i, line in enumerate(src.splitlines(), 1):
                if looks_like_mojibake(line):
                    offenders.append((os.path.relpath(path, APP), i, line.strip()[:90]))
    return offenders


#: Known offenders deliberately NOT repaired, with the reason. The gate asserts
#: this list never GROWS -- the debt stays visible and no NEW mojibake can land,
#: but a deploy is not blocked on a change we cannot safely make.
#:
#: legacy_pages/approval_page/main_section.html is drift-locked by
#: page_sync.BASELINE_SHA256: any byte change means bumping the baseline, moving
#: the old hash into SUPERSEDES_SHA256 and shipping a resync patch. If live has
#: drifted from the baseline the sync REFUSES, the patch raises, and `bench
#: migrate` fails -- i.e. a two-word cosmetic fix inside an upload-error toast
#: can block a whole deploy. Live state is not readable from here, so this is
#: routed to the page owner rather than guessed at.
KNOWN_UNFIXED = {
    ("legacy_pages/approval_page/main_section.html", 4871),
    ("legacy_pages/approval_page/main_section.html", 4880),
}


class TestNoMojibake(unittest.TestCase):
    def test_no_new_mojibake_in_source(self):
        offenders = [o for o in scan() if (o[0].replace(os.sep, "/"), o[1]) not in KNOWN_UNFIXED]
        self.assertEqual(
            offenders, [],
            "double-encoded Vietnamese found (%d lines). Repair by decoding the "
            "line cp1252 -> utf-8, and make sure whatever WROTE the file passes "
            "encoding='utf-8' explicitly:\n  " % len(offenders)
            + "\n  ".join("%s:%d  %s" % o for o in offenders))

    def test_known_unfixed_list_does_not_rot(self):
        """The exception list must describe REAL offenders. If someone repairs
        one of these lines the entry has to go, otherwise the list slowly turns
        into a blanket exemption for a whole file."""
        live = {(o[0].replace(os.sep, "/"), o[1]) for o in scan()}
        stale = KNOWN_UNFIXED - live
        self.assertEqual(stale, set(),
                         "these lines are clean now -- drop them from "
                         "KNOWN_UNFIXED: %s" % sorted(stale))

    def test_detector_actually_detects(self):
        # vacuity guard: a gate that never fires is a gate that is not running
        self.assertTrue(looks_like_mojibake("BÃ¡ÂºÂ¡n khÃƒÂ´ng cÃƒÂ³ quyÃ¡Â»â€¡n"))
        self.assertTrue(looks_like_mojibake("Cáº§n bá»• sung"))

    def test_correct_vietnamese_is_not_flagged(self):
        # all of these contain A-circumflex / A-tilde and are perfectly valid,
        # which is exactly why the gate cannot be a character blacklist
        for good in ("Bạn không có quyền xem yêu cầu này.",
                     "TỔNG NGÂN SÁCH",
                     "Âm thanh",
                     "NHÂN SỰ / Chấm công",
                     "Đang phê duyệt"):
            self.assertFalse(looks_like_mojibake(good), good)


if __name__ == "__main__":
    unittest.main()
