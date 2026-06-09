from __future__ import annotations


class ProviderError(Exception):
    """Base exception for all provider-related errors."""


class ProviderNotConfigured(ProviderError):
    """Raised when a provider has no API key or endpoint configured."""


class ProviderNotAvailable(ProviderError):
    """Raised when a provider's API is unreachable."""


class ProviderRateLimited(ProviderError):
    """Raised when a provider returns a rate-limit error."""


class ProviderAuthError(ProviderError):
    """Raised on authentication / authorization failures."""
