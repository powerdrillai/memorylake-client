"""
Integration tests for MemoryLake with real server.

These tests connect to a real MemoryLake server to verify end-to-end functionality.
Set MEMORYLAKE_BASE_URL and MEMORYLAKE_MEMORY_ID environment variables to run these tests.

Environment Variables:
    MEMORYLAKE_BASE_URL: Base URL of the MemoryLake server (e.g., https://api.memorylake.example.com)
    MEMORYLAKE_MEMORY_ID: Memory identifier for the test session (e.g., mem-xxx)

Running Tests:
    MEMORYLAKE_BASE_URL="..." MEMORYLAKE_MEMORY_ID="..." python -m pytest -v memorylake/test/test_memorylake_integration.py

Test Coverage:
    ✓ create - Create files
    ✓ view - View file contents (with and without range)
    ✓ str_replace - Replace text in files
    ✓ insert - Insert lines into files
    ✓ delete - Delete files
    ✓ rename - Rename/move files
    ✓ execute_tool_payload - Execute raw tool commands
"""

from __future__ import annotations

import asyncio
import os
import time
from collections.abc import Awaitable, Callable, Generator
from typing import TypeVar

import pytest
from anthropic.types.beta import (
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)

from memorylake.async_memorylake_memorytool import (
    AsyncMemoryLakeMemoryTool,
    AsyncMemoryLakeMemoryToolError,
)
from memorylake.memorylake_memorytool import MemoryLakeMemoryTool, MemoryLakeMemoryToolError

_T = TypeVar("_T")


def _get_server_config() -> tuple[str, str] | None:
    """
    Get server configuration from environment variables.

    Returns:
        Tuple of (base_url, memory_id) if both are set, None otherwise
    """
    base_url = os.environ.get("MEMORYLAKE_BASE_URL")
    memory_id = os.environ.get("MEMORYLAKE_MEMORY_ID")
    if base_url and memory_id:
        return (base_url, memory_id)
    return None


def _retry_sync_operation(
    operation: Callable[[], _T],
    *,
    retries: int = 3,
    delay_seconds: float = 0.3,
) -> _T:
    """Retry a synchronous remote operation when the server reports missing resources."""

    last_error: MemoryLakeMemoryToolError | None = None
    for attempt in range(retries):
        try:
            return operation()
        except MemoryLakeMemoryToolError as exc:
            message = str(exc)
            if "not found" not in message and "missing" not in message:
                raise
            last_error = exc
            if attempt < retries - 1:
                time.sleep(delay_seconds)
    raise last_error if last_error is not None else MemoryLakeMemoryToolError("Remote operation failed")


async def _retry_async_operation(
    operation: Callable[[], Awaitable[_T]],
    *,
    retries: int = 3,
    delay_seconds: float = 0.3,
) -> _T:
    """Retry an asynchronous remote operation under the same conditions as its sync counterpart."""

    last_error: AsyncMemoryLakeMemoryToolError | None = None
    for attempt in range(retries):
        try:
            return await operation()
        except AsyncMemoryLakeMemoryToolError as exc:
            message = str(exc)
            if "not found" not in message and "missing" not in message:
                raise
            last_error = exc
            if attempt < retries - 1:
                await asyncio.sleep(delay_seconds)
    raise last_error if last_error is not None else AsyncMemoryLakeMemoryToolError("Remote operation failed")


# Skip all tests in this file if server config is not available
pytestmark = [
    pytest.mark.skipif(
        _get_server_config() is None,
        reason="MEMORYLAKE_BASE_URL and MEMORYLAKE_MEMORY_ID must be set for integration tests",
    ),
    pytest.mark.xdist_group("memorylake-remote"),
]


@pytest.fixture(scope="session", autouse=True)
def clear_all_memories_once() -> Generator[None, None, None]:
    """
    Fixture to clear all memories once at the start of the test session.

    This ensures a clean test environment at the beginning.
    Uses session scope to run only once before all tests start.
    Does not clear after tests to avoid interfering with running tests.
    """
    config = _get_server_config()
    if config is None:
        # If config is not available, tests will be skipped anyway
        yield
        return

    base_url, memory_id = config

    # Clear before all tests
    print("\n🧹 Clearing all memories before integration test session...")
    tool = MemoryLakeMemoryTool(base_url=base_url, memory_id=memory_id)
    try:
        result = tool.clear_all_memory()
        print(f"✓ Cleared memories: {result}")
    except Exception as e:
        print(f"⚠ Warning: Failed to clear memories before tests: {e}")
    finally:
        tool.close()

    # Run all tests
    yield

    # Note: Not clearing after tests to avoid race conditions with running tests


def test_sync_remote_server_full_workflow() -> None:
    """Test synchronous client with real server - full CRUD workflow."""
    config = _get_server_config()
    assert config is not None, "Server config must be available"
    base_url, memory_id = config

    tool = MemoryLakeMemoryTool(
        base_url=base_url,
        memory_id=memory_id,
    )

    test_path = "/memories/integration_test_sync.txt"

    # Test 1: Create file
    create_result = tool.create(
        BetaMemoryTool20250818CreateCommand(
            command="create",
            path=test_path,
            file_text="Hello, MemoryLake!\nThis is line 2.",
        ),
    )
    assert "created" in create_result.lower() or "success" in create_result.lower()

    # Test 2: View file
    view_result = tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path=test_path,
        ),
    )
    assert "Hello, MemoryLake!" in view_result
    assert "This is line 2." in view_result

    # Test 3: String replace
    replace_result = tool.str_replace(
        BetaMemoryTool20250818StrReplaceCommand(
            command="str_replace",
            path=test_path,
            old_str="Hello, MemoryLake!",
            new_str="Hello, Integration Test!",
        ),
    )
    assert "replaced" in replace_result.lower() or "success" in replace_result.lower()

    # Test 4: Insert line
    insert_result = _retry_sync_operation(
        lambda: tool.insert(
            BetaMemoryTool20250818InsertCommand(
                command="insert",
                path=test_path,
                insert_line=2,
                insert_text="This is a new line inserted.",
            ),
        ),
    )
    assert "inserted" in insert_result.lower() or "success" in insert_result.lower()

    # Test 5: View with range
    view_range_result = tool.view(
        BetaMemoryTool20250818ViewCommand(
            command="view",
            path=test_path,
            view_range=[1, 2],
        ),
    )
    assert "Hello, Integration Test!" in view_range_result

    # Test 6: Rename file
    renamed_path = "/memories/integration_test_sync_renamed.txt"

    rename_result = tool.rename(
        BetaMemoryTool20250818RenameCommand(
            command="rename",
            old_path=test_path,
            new_path=renamed_path,
        ),
    )
    assert "renamed" in rename_result.lower() or "success" in rename_result.lower()

    # Test 7: Delete renamed file
    delete_result = tool.delete(
        BetaMemoryTool20250818DeleteCommand(
            command="delete",
            path=renamed_path,
        ),
    )
    assert "deleted" in delete_result.lower() or "success" in delete_result.lower()

    # Note: All memories will be automatically cleared by the fixture after all tests complete


@pytest.mark.asyncio
async def test_async_remote_server_full_workflow() -> None:
    """Test asynchronous client with real server - full CRUD workflow."""
    config = _get_server_config()
    assert config is not None, "Server config must be available"
    base_url, memory_id = config

    async with AsyncMemoryLakeMemoryTool(
        base_url=base_url,
        memory_id=memory_id,
    ) as tool:
        test_path = "/memories/integration_test_async.txt"

        # Test 1: Create file
        create_result = await tool.create(
            BetaMemoryTool20250818CreateCommand(
                command="create",
                path=test_path,
                file_text="Async test content\nLine 2 of async test",
            ),
        )
        assert "created" in create_result.lower() or "success" in create_result.lower()

        # Test 2: View file
        view_result = await tool.view(
            BetaMemoryTool20250818ViewCommand(
                command="view",
                path=test_path,
            ),
        )
        assert "Async test content" in view_result
        assert "Line 2 of async test" in view_result

        # Test 3: String replace
        replace_result = await tool.str_replace(
            BetaMemoryTool20250818StrReplaceCommand(
                command="str_replace",
                path=test_path,
                old_str="Async test content",
                new_str="Modified async content",
            ),
        )
        assert "replaced" in replace_result.lower() or "success" in replace_result.lower()

        # Test 4: Insert line
        insert_result = await _retry_async_operation(
            lambda: tool.insert(
                BetaMemoryTool20250818InsertCommand(
                    command="insert",
                    path=test_path,
                    insert_line=0,
                    insert_text="First line inserted",
                ),
            ),
        )
        assert "inserted" in insert_result.lower() or "success" in insert_result.lower()

        # Test 5: View with range
        view_range_result = await tool.view(
            BetaMemoryTool20250818ViewCommand(
                command="view",
                path=test_path,
                view_range=[1, 3],
            ),
        )
        assert "First line inserted" in view_range_result or "Modified async content" in view_range_result

        # Test 6: Rename file
        renamed_path = "/memories/integration_test_async_renamed.txt"

        rename_result = await tool.rename(
            BetaMemoryTool20250818RenameCommand(
                command="rename",
                old_path=test_path,
                new_path=renamed_path,
            ),
        )
        assert "renamed" in rename_result.lower() or "success" in rename_result.lower()

        # Test 7: Delete renamed file
        delete_result = await tool.delete(
            BetaMemoryTool20250818DeleteCommand(
                command="delete",
                path=renamed_path,
            ),
        )
        assert "deleted" in delete_result.lower() or "success" in delete_result.lower()


@pytest.mark.asyncio
async def test_async_remote_server_execute_tool_payload() -> None:
    """Test asynchronous client execute_tool_payload method with real server."""
    config = _get_server_config()
    assert config is not None, "Server config must be available"
    base_url, memory_id = config

    async with AsyncMemoryLakeMemoryTool(
        base_url=base_url,
        memory_id=memory_id,
    ) as tool:
        test_path = "/memories/integration_test_payload.txt"

        # Test execute_tool_payload with create command
        create_result = await tool.execute_tool_payload(
            {
                "command": "create",
                "path": test_path,
                "file_text": "Testing execute_tool_payload",
            },
        )
        assert "created" in create_result.lower() or "success" in create_result.lower()

        # Test execute_tool_payload with view command
        view_result = await tool.execute_tool_payload(
            {
                "command": "view",
                "path": test_path,
            },
        )
        assert "Testing execute_tool_payload" in view_result


def test_sync_remote_server_execute_tool_payload() -> None:
    """Test synchronous client execute_tool_payload method with real server."""
    config = _get_server_config()
    assert config is not None, "Server config must be available"
    base_url, memory_id = config

    tool = MemoryLakeMemoryTool(
        base_url=base_url,
        memory_id=memory_id,
    )

    test_path = "/memories/integration_test_sync_payload.txt"

    # Test execute_tool_payload with create command
    create_result = tool.execute_tool_payload(
        {
            "command": "create",
            "path": test_path,
            "file_text": "Testing sync execute_tool_payload",
        },
    )
    assert "created" in create_result.lower() or "success" in create_result.lower()

    # Test execute_tool_payload with view command
    view_result = tool.execute_tool_payload(
        {
            "command": "view",
            "path": test_path,
        },
    )
    assert "Testing sync execute_tool_payload" in view_result
