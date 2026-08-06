"""QuantMind domain exceptions."""


class QuantMindError(Exception):
    """Base exception for QuantMind."""


class DataProviderError(QuantMindError):
    """Raised when a data provider cannot fulfil a request."""


class SymbolNotFound(DataProviderError):
    """Raised when a symbol cannot be resolved."""


class UnsupportedInterval(DataProviderError):
    """Raised when an interval is not supported by a provider."""


class ConfigurationError(QuantMindError):
    """Raised when required configuration is missing."""
