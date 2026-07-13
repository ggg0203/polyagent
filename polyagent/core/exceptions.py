"""Exception hierarchy for LLM operations.

`RetryableError` marks errors where retrying the same request may succeed;
`BudgetExceededError` is a hard, non-retryable run-level failure.
"""

from __future__ import annotations


class LLMError(Exception):
    """Base class for all LLM-layer errors."""


class RetryableError(LLMError):
    """An error after which retrying the same request may succeed."""


class RateLimitError(RetryableError):
    """Provider returned 429 / quota-exceeded. Honours `Retry-After`."""

    def __init__(self, message: str = "rate limited", retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class TimeoutError(RetryableError):
    """Request timed out."""


class ProviderUnavailableError(RetryableError):
    """Provider returned 5xx or is otherwise unreachable."""


class BudgetExceededError(LLMError):
    """Token budget for the current run has been exhausted."""
