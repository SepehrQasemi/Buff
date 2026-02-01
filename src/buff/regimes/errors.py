"""Custom exceptions for regime semantics."""


class RegimeError(Exception):
    """Base exception for regime semantics."""


class RegimeSchemaError(RegimeError):
    """Raised when regime schema validation fails."""


class RegimeEvaluationError(RegimeError):
    """Raised when regime evaluation encounters an unrecoverable error."""
