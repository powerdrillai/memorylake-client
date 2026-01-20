import json
import logging
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

import httpx
from typeguard import TypeCheckError as TypeCheckError
from typeguard import check_type as typeguard_check_type

from memorylake.mem0.exceptions import (
    NetworkError,
    create_exception_from_response,
)

logger = logging.getLogger(__name__)


if TYPE_CHECKING:
    # When type-checking, `safe_cast` is just an alias to `cast`
    from typing import cast as cast
    safe_cast = cast
else:
    # When not type-checking, `safe_cast` is a function that actually performs runtime type checking
    def safe_cast(typ: Any, value: object) -> Any:
        """
        Safely cast a value to the given type - if the cast fails, an TypeCheckError is raised.

        This replaces `typing.cast`, which does not perform any runtime checks.
        """
        try:
            return typeguard_check_type(value, typ)
        except TypeCheckError:
            # Here, the type checking failed
            raise


class APIError(Exception):
    """Exception raised for errors in the API.

    Deprecated: Use specific exception classes from mem0.exceptions instead.
    This class is maintained for backward compatibility.
    """

    pass


def api_error_handler(func: Callable[..., Any]) -> Callable[..., Any]:
    """Decorator to handle API errors consistently.

    This decorator catches HTTP and request errors and converts them to
    appropriate structured exception classes with detailed error information.

    The decorator analyzes HTTP status codes and response content to create
    the most specific exception type with helpful error messages, suggestions,
    and debug information.
    """
    @wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error occurred: {e}")

            # Extract error details from response
            response_text: str = ""
            error_details: dict[str, Any] = {}
            debug_info: dict[str, Any] = {
                "status_code": e.response.status_code,
                "url": str(e.request.url),
                "method": e.request.method,
            }

            try:
                response_text = e.response.text
                # Try to parse JSON response for additional error details
                if e.response.headers.get("content-type", "").startswith("application/json"):
                    error_data = json.loads(response_text)
                    if isinstance(error_data, dict):
                        error_details = safe_cast(dict[str, Any], error_data)
                        response_text = error_details.get("detail", response_text)
            except (json.JSONDecodeError, AttributeError):
                # Fallback to plain text response
                pass

            # Add rate limit information if available
            if e.response.status_code == 429:
                retry_after = e.response.headers.get("Retry-After")
                if retry_after:
                    try:
                        debug_info["retry_after"] = int(retry_after)
                    except ValueError:
                        pass

                # Add rate limit headers if available
                for header in ["X-RateLimit-Limit", "X-RateLimit-Remaining", "X-RateLimit-Reset"]:
                    value = e.response.headers.get(header)
                    if value:
                        debug_info[header.lower().replace("-", "_")] = value

            # Create specific exception based on status code
            exception = create_exception_from_response(
                status_code=e.response.status_code,
                response_text=response_text,
                details=error_details,
                debug_info=debug_info,
            )

            raise exception

        except httpx.RequestError as e:
            logger.error(f"Request error occurred: {e}")

            # Determine the appropriate exception type based on error type
            if isinstance(e, httpx.TimeoutException):
                raise NetworkError(
                    message=f"Request timed out: {str(e)}",
                    error_code="NET_TIMEOUT",
                    suggestion="Please check your internet connection and try again",
                    debug_info={"error_type": "timeout", "original_error": str(e)},
                )
            elif isinstance(e, httpx.ConnectError):
                raise NetworkError(
                    message=f"Connection failed: {str(e)}",
                    error_code="NET_CONNECT",
                    suggestion="Please check your internet connection and try again",
                    debug_info={"error_type": "connection", "original_error": str(e)},
                )
            else:
                # Generic network error for other request errors
                raise NetworkError(
                    message=f"Network request failed: {str(e)}",
                    error_code="NET_GENERIC",
                    suggestion="Please check your internet connection and try again",
                    debug_info={"error_type": "request", "original_error": str(e)},
                )

    return wrapper
