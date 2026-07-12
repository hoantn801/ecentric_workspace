# Copyright (c) 2026, eCentric and contributors
"""Provider adapter registry. The orchestrator resolves an adapter from the settings
row; NOTHING outside esign/providers/* knows provider payload shapes."""
from ecentric_workspace.approval_center.esign.providers.base import ProviderError


def get_adapter(settings):
    """settings: dict-like with at least provider/base_url/site/request_timeout.
    S2A ships Mock only; the SCTS adapter arrives in S2B behind the same interface."""
    provider = (settings.get("provider") if isinstance(settings, dict) else settings.provider) or ""
    if provider == "Mock":
        from ecentric_workspace.approval_center.esign.providers.mock import MockAdapter
        return MockAdapter(settings)
    if provider == "SCTS":
        raise ProviderError("scts_adapter_not_implemented",
                            "SCTS adapter ships in phase S2B; use the Mock provider for UAT-dry runs.",
                            retryable=False)
    raise ProviderError("unknown_provider", "Unknown signature provider: %r" % provider,
                        retryable=False)
