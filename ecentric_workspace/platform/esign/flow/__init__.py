# Copyright (c) 2026, eCentric and contributors
"""Declarative flow layer for the esign module (Payment Request only, Phase 1).

This package OWNS NOTHING at runtime yet: it names and orders the steps that the
existing services already execute, so there is one place to read "what happens, in
what order, who does it, where it can get parked" without tracing 8 files. It does
not replace ``esign.state`` (still the only source of truth for legal PACKAGE/DSR
transitions) or the Approval Engine (still the only source of truth for approval
state). See ``ecentric_workspace.approval_center.tests.test_esign_flow_contract``
for the check that keeps this declaration honest against ``esign.state``.
"""
