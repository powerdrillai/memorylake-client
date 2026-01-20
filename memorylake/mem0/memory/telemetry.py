from typing import Any, Optional


def capture_client_event(
    event_name: str,
    instance: Any,
    additional_data: Optional[dict[str, Any]] = None,
) -> None:
    """Capture a client event for telemetry.

    This is a stub implementation. Parameters are part of the public API
    and are intentionally accepted but not used.
    """
    _ = event_name
    _ = instance
    _ = additional_data
    ...
