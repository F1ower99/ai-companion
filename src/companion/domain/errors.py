class ValidationError(ValueError):
    """An input violates a domain or persistence constraint."""


class NotFoundError(LookupError):
    """A requested domain record does not exist."""


class StorageError(RuntimeError):
    """Local storage is unavailable or could not complete an operation."""
