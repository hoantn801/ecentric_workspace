# Copyright (c) 2026, eCentric and contributors
"""QC gate: every JS/jsdom suite must be able to LOCATE the shipped asset it tests.

Why this exists (2026-08-24): the 2026-08-19 reorg moved `approval_center/esign/ui` to
`platform/esign/ui`. Three suites (test_requester_panel_init.mjs,
test_requester_stabilization.mjs, frontend/test_payment_request_signing_panel.js) kept a
hard-coded relative path and silently ENOENT'd for five days - 52+ assertions were dead
weight and nobody noticed, because a suite that crashes on load looks the same as a suite
nobody ran. This test crawls the suites, extracts every asset filename they read, and asserts
the file exists somewhere in the app. It fails the moment a refactor orphans a suite again.

Pure filesystem + regex: no bench, no node, no network.
  bench --site <site> run-tests --module ecentric_workspace.approval_center.tests.test_js_suite_paths
"""
import os
import re
import unittest

_HERE = os.path.dirname(os.path.abspath(__file__))
_APP = os.path.abspath(os.path.join(_HERE, "..", ".."))          # ecentric_workspace/
_SUITE_DIRS = [os.path.join(_HERE, "js"), os.path.join(_HERE, "frontend")]

_ASSET_RE = re.compile(r'["\']([A-Za-z0-9_\-]+\.(?:html|js))["\']')
_IGNORE = {"package.json"}


def _shipped_assets():
    """filename -> [absolute paths] for every html/js shipped under the app (tests excluded)."""
    found = {}
    for root, dirs, files in os.walk(_APP):
        dirs[:] = [d for d in dirs if d not in (".git", "node_modules", "__pycache__", "tests")]
        for fn in files:
            if fn.endswith((".html", ".js")):
                found.setdefault(fn, []).append(os.path.join(root, fn))
    return found


class TestJsSuitePaths(unittest.TestCase):
    def test_every_suite_can_locate_its_assets(self):
        shipped = _shipped_assets()
        problems = []
        suites = 0
        for d in _SUITE_DIRS:
            if not os.path.isdir(d):
                continue
            for fn in sorted(os.listdir(d)):
                if not fn.endswith((".mjs", ".js")):
                    continue
                suites += 1
                with open(os.path.join(d, fn), encoding="utf-8") as fh:
                    src = fh.read()
                for line in src.splitlines():
                    if not any(t in line for t in ("readFileSync", "existsSync", "_ROOTS", "path.join")):
                        continue
                    if line.strip().startswith("//"):
                        continue
                    for asset in _ASSET_RE.findall(line):
                        if asset in _IGNORE or asset == fn:
                            continue
                        if asset not in shipped:
                            problems.append("%s -> '%s' is not shipped anywhere in the app"
                                            % (fn, asset))
        self.assertGreater(suites, 5, "suite discovery broke - expected several JS suites")
        self.assertEqual(problems, [], "orphaned JS suite asset reference(s):\n  "
                                       + "\n  ".join(problems))

    def test_known_esign_assets_live_under_platform(self):
        """Pins the post-reorg home of the assets the signing suites exercise, so a future move
        must update this test consciously instead of silently orphaning three suites."""
        ui = os.path.join(_APP, "platform", "esign", "ui")
        for asset in ("requester_signing_panel.html", "payment_request_signing.html",
                      "document_signing_section.html", "pdf_placement_editor.html"):
            self.assertTrue(os.path.isfile(os.path.join(ui, asset)),
                            "missing shipped asset platform/esign/ui/%s" % asset)
