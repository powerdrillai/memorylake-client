"""Tests for MemoryLakeClient factory class."""

from __future__ import annotations

import pytest

from memorylake import MemoryLakeClient
from memorylake.async_memorylake_memorytool import AsyncMemoryLakeMemoryTool
from memorylake.memorylake_memorytool import MemoryLakeMemoryTool
from memorylake.memorytool import MemoryTool


def test_client_create_local_tool(tmp_path: pytest.TempPathFactory) -> None:
    """Test creating a local file system tool."""
    client = MemoryLakeClient(storage_path=str(tmp_path))
    tool = client.create_local_tool()

    assert isinstance(tool, MemoryTool)
    assert tool._base_path == tmp_path  # pyright: ignore[reportPrivateUsage]


def test_client_create_local_tool_missing_path() -> None:
    """Test creating a local tool without storage_path raises ValueError."""
    client = MemoryLakeClient()

    with pytest.raises(ValueError, match="storage_path is required"):
        client.create_local_tool()


def test_client_create_sync_tool() -> None:
    """Test creating a synchronous remote tool."""
    client = MemoryLakeClient(
        base_url="https://api.example.com",
        memory_id="mem-123",
        timeout=60.0,
        headers={"Authorization": "Bearer token"},
    )
    tool = client.create_sync_tool()

    assert isinstance(tool, MemoryLakeMemoryTool)
    assert tool._base_url == "https://api.example.com"  # pyright: ignore[reportPrivateUsage]
    assert tool._memory_id == "mem-123"  # pyright: ignore[reportPrivateUsage]
    assert tool._timeout == 60.0  # pyright: ignore[reportPrivateUsage]
    assert tool._headers["Authorization"] == "Bearer token"  # pyright: ignore[reportPrivateUsage]

    # Clean up
    tool.close()


def test_client_create_sync_tool_missing_params() -> None:
    """Test creating a sync tool without required params raises ValueError."""
    # Missing both
    client1 = MemoryLakeClient()
    with pytest.raises(ValueError, match="base_url and memory_id are required"):
        client1.create_sync_tool()

    # Missing memory_id
    client2 = MemoryLakeClient(base_url="https://api.example.com")
    with pytest.raises(ValueError, match="base_url and memory_id are required"):
        client2.create_sync_tool()

    # Missing base_url
    client3 = MemoryLakeClient(memory_id="mem-123")
    with pytest.raises(ValueError, match="base_url and memory_id are required"):
        client3.create_sync_tool()


def test_client_create_async_tool() -> None:
    """Test creating an asynchronous remote tool."""
    client = MemoryLakeClient(
        base_url="https://api.example.com",
        memory_id="mem-456",
        timeout=45.0,
        headers={"X-API-Key": "secret"},
    )
    tool = client.create_async_tool()

    assert isinstance(tool, AsyncMemoryLakeMemoryTool)
    assert tool._base_url == "https://api.example.com"  # pyright: ignore[reportPrivateUsage]
    assert tool._memory_id == "mem-456"  # pyright: ignore[reportPrivateUsage]
    assert tool._timeout == 45.0  # pyright: ignore[reportPrivateUsage]
    assert tool._headers["X-API-Key"] == "secret"  # pyright: ignore[reportPrivateUsage]


def test_client_create_async_tool_missing_params() -> None:
    """Test creating an async tool without required params raises ValueError."""
    # Missing both
    client1 = MemoryLakeClient()
    with pytest.raises(ValueError, match="base_url and memory_id are required"):
        client1.create_async_tool()

    # Missing memory_id
    client2 = MemoryLakeClient(base_url="https://api.example.com")
    with pytest.raises(ValueError, match="base_url and memory_id are required"):
        client2.create_async_tool()

    # Missing base_url
    client3 = MemoryLakeClient(memory_id="mem-456")
    with pytest.raises(ValueError, match="base_url and memory_id are required"):
        client3.create_async_tool()


def test_client_from_remote() -> None:
    """Test convenience class method for remote client."""
    client = MemoryLakeClient.from_remote(
        base_url="https://api.example.com",
        memory_id="mem-789",
        timeout=120.0,
        headers={"Custom-Header": "value"},
    )

    assert client.base_url == "https://api.example.com"
    assert client.memory_id == "mem-789"
    assert client.timeout == 120.0
    assert client.headers == {"Custom-Header": "value"}
    assert client.storage_path is None

    # Should be able to create remote tools
    sync_tool = client.create_sync_tool()
    assert isinstance(sync_tool, MemoryLakeMemoryTool)
    sync_tool.close()

    async_tool = client.create_async_tool()
    assert isinstance(async_tool, AsyncMemoryLakeMemoryTool)


def test_client_from_local(tmp_path: pytest.TempPathFactory) -> None:
    """Test convenience class method for local client."""
    client = MemoryLakeClient.from_local(storage_path=str(tmp_path))

    assert client.storage_path == str(tmp_path)
    assert client.base_url is None
    assert client.memory_id is None

    # Should be able to create local tool
    tool = client.create_local_tool()
    assert isinstance(tool, MemoryTool)


def test_client_default_timeout() -> None:
    """Test that default timeout is 30.0 seconds."""
    client = MemoryLakeClient(
        base_url="https://api.example.com",
        memory_id="mem-default",
    )

    assert client.timeout == 30.0

    tool = client.create_sync_tool()
    assert tool._timeout == 30.0  # pyright: ignore[reportPrivateUsage]
    tool.close()


def test_client_none_headers() -> None:
    """Test that None headers are handled correctly."""
    client = MemoryLakeClient(
        base_url="https://api.example.com",
        memory_id="mem-no-headers",
        headers=None,
    )

    assert client.headers is None

    tool = client.create_sync_tool()
    # The tool should have created its own headers dict with version header
    assert "x-memorylake-client-version" in tool._headers  # pyright: ignore[reportPrivateUsage]
    tool.close()


def test_client_multiple_tool_creation() -> None:
    """Test that client can create multiple tool instances."""
    client = MemoryLakeClient(
        base_url="https://api.example.com",
        memory_id="mem-multi",
    )

    # Create multiple sync tools
    tool1 = client.create_sync_tool()
    tool2 = client.create_sync_tool()

    assert isinstance(tool1, MemoryLakeMemoryTool)
    assert isinstance(tool2, MemoryLakeMemoryTool)
    assert tool1 is not tool2  # Should be different instances

    tool1.close()
    tool2.close()

    # Create multiple async tools
    async_tool1 = client.create_async_tool()
    async_tool2 = client.create_async_tool()

    assert isinstance(async_tool1, AsyncMemoryLakeMemoryTool)
    assert isinstance(async_tool2, AsyncMemoryLakeMemoryTool)
    assert async_tool1 is not async_tool2  # Should be different instances
