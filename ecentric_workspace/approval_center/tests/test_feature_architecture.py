"""Architecture guardrails for Approval Center vertical request features."""
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
FEATURES = ROOT / "features"
LAYERS = {"domain", "application", "controllers", "infrastructure", "ui"}


class TestFeatureArchitecture(unittest.TestCase):
    def test_feature_roots_only_contain_package_marker(self):
        for feature in FEATURES.iterdir():
            if not feature.is_dir() or feature.name == "__pycache__":
                continue
            self.assertEqual(
                {path.name for path in feature.iterdir() if path.is_file()},
                {"__init__.py"},
                feature.name,
            )
            self.assertEqual(
                {path.name for path in feature.iterdir()
                 if path.is_dir() and path.name != "__pycache__"},
                LAYERS,
                feature.name,
            )

    def test_inward_dependency_boundaries(self):
        forbidden = {
            "domain": (".controllers", ".infrastructure", ".ui"),
            "application": (".controllers", ".infrastructure", ".ui"),
            "controllers": (".infrastructure",),
        }
        for feature in FEATURES.iterdir():
            if not feature.is_dir() or feature.name == "__pycache__":
                continue
            for layer, fragments in forbidden.items():
                for source_file in (feature / layer).glob("*.py"):
                    source = source_file.read_text(encoding="utf-8")
                    for fragment in fragments:
                        self.assertNotIn(fragment, source, str(source_file))

if __name__ == "__main__":
    unittest.main()
