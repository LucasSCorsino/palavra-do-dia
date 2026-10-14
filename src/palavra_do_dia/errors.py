"""Domain exceptions. Every expected failure derives from ``DailyWordError``."""


class DailyWordError(Exception):
    """Base class for all expected application errors."""


class ConfigError(DailyWordError):
    """Required configuration is missing or invalid."""


class SelectionError(DailyWordError):
    """The AI could not produce a usable passage choice."""


class InvalidReferenceError(DailyWordError):
    """A reference does not exist, is malformed, or was already used. Retryable."""


class ProviderUnavailableError(DailyWordError):
    """A Bible provider is down or returned an unusable response."""


class AllProvidersFailedError(DailyWordError):
    """No Bible provider could serve the requested chapter."""


class NotificationError(DailyWordError):
    """The notification could not be delivered."""
