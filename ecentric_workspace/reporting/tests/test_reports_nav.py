# Copyright (c) 2026, eCentric and contributors
"""Pure tests for the Reports Center nav wiring (no bench)."""
import unittest

from ecentric_workspace.shell import nav
from ecentric_workspace.reporting import nav as rnav


class TestReportsNav(unittest.TestCase):
    def test_reporting_provider_has_hub_item(self):
        routes = {it["route"] for it in rnav.items()}
        self.assertIn("/reports", routes)
        hub = next(it for it in rnav.items() if it["route"] == "/reports")
        self.assertEqual(hub["group"], "Báo cáo & Phân tích")
        self.assertLess(hub["order"], 10)  # sits above Báo cáo tuần

    def test_reporting_context_entry_is_reports(self):
        self.assertEqual(nav.CONTEXTS["reporting"]["entry"]["route"], "/reports")

    def test_reports_route_composes_in_reporting_context(self):
        routes = {it["route"] for it in nav.compose("reporting")}
        self.assertIn("/reports", routes)

    def test_reports_route_resolves_to_reporting_context(self):
        self.assertEqual(nav.resolve_context("/reports"), "reporting")

    def test_full_registry_still_valid(self):
        # compose_all() runs validate() across every provider -> no dup key/route
        allr = [it["route"] for it in nav.compose_all()]
        self.assertIn("/reports", allr)
        self.assertEqual(len(allr), len(set(allr)), "duplicate routes in registry")


if __name__ == "__main__":
    unittest.main()
