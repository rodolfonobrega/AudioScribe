"""
Error Handler - Error classification utilities for retry vs fallback decisions.

This module provides functions to categorize LiteLLM exceptions and determine
whether an error should trigger a retry with exponential backoff or an immediate
fallback to the next model in the chain.
"""


# Define exception types that should trigger retries
# These errors are typically temporary and may succeed on retry
RETRYABLE_ERRORS = (
    'APIConnectionError',
    'ServiceUnavailableError',
    'RateLimitError',
    'InternalServerError',
    'TimeoutError',
    'APITimeoutError',
)

# Define exception types that should trigger immediate fallback
# These errors indicate configuration or authorization issues that won't resolve with retry
FALLBACK_ERRORS = (
    'AuthenticationError',
    'BadRequestError',
    'InvalidRequestError',
    'BudgetExceededError',
    'ContentPolicyViolationError',
    'ContextLengthExceededError',
    'NotFoundError',
    'PermissionError',
)


def _get_error_name(error: Exception) -> str:
    """
    Extract the error type name from an exception.

    Args:
        error: Exception to classify

    Returns:
        Error type name (e.g., 'APIConnectionError')
    """
    # Get the class name
    error_name = error.__class__.__name__

    # Check if it's a LiteLLM error (might be wrapped)
    if hasattr(error, '__cause__') and error.__cause__:
        cause_name = error.__cause__.__class__.__name__
        # Prioritize the underlying cause
        return cause_name

    return error_name


def should_retry(error: Exception) -> bool:
    """
    Determine if an error should trigger a retry with exponential backoff.

    Retryable errors are typically transient issues like network problems,
    rate limits, or temporary service unavailability.

    Args:
        error: Exception to evaluate

    Returns:
        True if error should trigger a retry, False otherwise

    Examples:
        >>> should_retry(APIConnectionError("Connection failed"))
        True
        >>> should_retry(AuthenticationError("Invalid API key"))
        False
    """
    error_name = _get_error_name(error)

    # Check if error type is in retryable list
    for retryable_type in RETRYABLE_ERRORS:
        if retryable_type in error_name:
            return True

    # Also check error message content for common retryable patterns
    error_message = str(error).lower()
    retryable_patterns = [
        'rate limit',
        'timeout',
        'connection',
        'service unavailable',
        'try again',
        'temporarily unavailable',
        'server error',
        'gateway timeout',
        'network',
    ]

    for pattern in retryable_patterns:
        if pattern in error_message:
            return True

    return False


def should_fallback(error: Exception) -> bool:
    """
    Determine if an error should trigger an immediate fallback to the next model.

    Fallback errors indicate fundamental issues with the current model configuration
    that are unlikely to resolve with retries (e.g., invalid API key, model not found).

    Args:
        error: Exception to evaluate

    Returns:
        True if error should trigger fallback, False otherwise

    Examples:
        >>> should_fallback(AuthenticationError("Invalid API key"))
        True
        >>> should_fallback(APIConnectionError("Network error"))
        False
    """
    error_name = _get_error_name(error)

    # Check if error type is in fallback list
    for fallback_type in FALLBACK_ERRORS:
        if fallback_type in error_name:
            return True

    # Also check error message content for common fallback patterns
    error_message = str(error).lower()
    fallback_patterns = [
        'authentication',
        'invalid api key',
        'unauthorized',
        'forbidden',
        'not found',
        'does not exist',
        'invalid request',
        'budget exceeded',
        'quota exceeded',
        'content policy',
        'permission denied',
    ]

    for pattern in fallback_patterns:
        if pattern in error_message:
            return True

    return False


def retry_with_backoff(retry_count: int, base_delay: float = 1.0) -> float:
    """
    Calculate exponential backoff delay for retries.

    Uses exponential backoff with a maximum cap to avoid excessive delays.
    Formula: min(base_delay * (2 ^ retry_count), 60)

    Args:
        retry_count: Current retry attempt number (0-indexed)
        base_delay: Base delay in seconds (default: 1.0)

    Returns:
        Delay in seconds before next retry

    Examples:
        >>> retry_with_backoff(0, 1.0)
        1.0
        >>> retry_with_backoff(1, 1.0)
        2.0
        >>> retry_with_backoff(2, 1.0)
        4.0
        >>> retry_with_backoff(10, 1.0)  # Capped at 60 seconds
        60.0
    """
    # Calculate exponential delay: base_delay * (2 ^ retry_count)
    delay = base_delay * (2 ** retry_count)

    # Cap at 60 seconds maximum
    return min(delay, 60.0)


def classify_error(error: Exception) -> str:
    """
    Classify an error into one of three categories: retry, fallback, or unknown.

    Args:
        error: Exception to classify

    Returns:
        One of: 'retry', 'fallback', 'unknown'

    Examples:
        >>> classify_error(APIConnectionError("Connection failed"))
        'retry'
        >>> classify_error(AuthenticationError("Invalid API key"))
        'fallback'
    """
    # Check for fallback first (auth/config errors)
    if should_fallback(error):
        return 'fallback'

    # Then check for retry (transient errors)
    if should_retry(error):
        return 'retry'

    # Unknown error type
    return 'unknown'
