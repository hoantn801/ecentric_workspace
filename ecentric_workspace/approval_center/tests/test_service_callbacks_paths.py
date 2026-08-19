# Copyright (c) 2026, eCentric and contributors
"""Guard: service_callbacks() must build module paths that actually exist.

The 2026-08 module reorg moved feature services to
`approval_center.features.<feature>.application.service`, but the string-built path
in definition_support (and the fulfillment adapters) was missed, so every form that
routes submit/resubmit through service_callbacks raised ModuleNotFoundError on submit
('No module named ecentric_workspace.approval_center.asset_request'). This test walks
every feature that ships an application/service.py and asserts the callbacks resolve
to a real file, so a future move breaks the test instead of production submit.
"""
import os
import unittest

from ecentric_workspace.approval_center.shared import definition_support as ds

# repo root = .../ (parent of the top-level ecentric_workspace package)
_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.abspath(os.path.join(_HERE, "..", "..", ".."))
_FEATURES_DIR = os.path.join(_REPO, "ecentric_workspace", "approval_center", "features")


def _module_to_path(module):
    return os.path.join(_REPO, module.replace(".", os.sep) + ".py")


def _features_with_service():
    out = []
    for name in sorted(os.listdir(_FEATURES_DIR)):
        svc = os.path.join(_FEATURES_DIR, name, "application", "service.py")
        if os.path.isfile(svc):
            out.append(name)
    return out


class TestServiceCallbackPaths(unittest.TestCase):
    def test_asset_request_points_to_new_layout(self):
        cb = ds.service_callbacks("asset_request")
        self.assertEqual(cb["submitter"].module,
                         "ecentric_workspace.approval_center.features.asset_request.application.service")

    def test_every_feature_service_module_exists(self):
        feats = _features_with_service()
        self.assertGreater(len(feats), 10)  # sanity: we found the features
        missing = []
        for f in feats:
            cb = ds.service_callbacks(f)
            for role in ("submitter", "resubmitter"):
                mod = cb[role].module
                if not os.path.isfile(_module_to_path(mod)):
                    missing.append((f, role, mod))
        self.assertEqual(missing, [], "service_callbacks point at non-existent modules: %r" % missing)


if __name__ == "__main__":
    unittest.main()
