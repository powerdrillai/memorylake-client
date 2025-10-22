"""
Convenient client factory for creating memory tool instances.

This module provides the ``MemoryLakeClient`` class which serves as a factory
for creating memory tool instances in different modes:

* Local mode: File system-based (MemoryTool)
* Sync remote mode: Synchronous HTTP client (MemoryLakeMemoryTool)
* Async remote mode: Asynchronous HTTP client (AsyncMemoryLakeMemoryTool)
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

from .async_memorylake_memorytool import AsyncMemoryLakeMemoryTool
from .memorylake_memorytool import MemoryLakeMemoryTool
from .memorytool import MemoryTool

__all__ = ["MemoryLakeClient"]


class MemoryLakeClient:
    """
    Convenient client factory for creating memory tool instances.

    This factory class provides a simple way to create memory tool instances
    with shared configuration. It supports three modes:

    1. Local mode: File system-based memory tool (MemoryTool)
    2. Sync remote mode: Synchronous HTTP client (MemoryLakeMemoryTool)
    3. Async remote mode: Asynchronous HTTP client (AsyncMemoryLakeMemoryTool)

    Args:
        base_url: MemoryLake server base URL (required for remote modes)
        memory_id: Unique memory identifier (required for remote modes)
        storage_path: Local file system path (required for local mode)
        timeout: Request timeout in seconds (default: 30.0, remote modes only)
        headers: Optional HTTP headers (remote modes only)

    Example (Remote):
        client = MemoryLakeClient(
            base_url="https://api.memorylake.example.com",
            memory_id="mem-xxx",
        )

        # Synchronous remote
        sync_tool = client.create_sync_tool()
        sync_tool.create(...)
        sync_tool.close()

        # Asynchronous remote
        async with client.create_async_tool() as async_tool:
            await async_tool.create(...)

    Example (Local):
        client = MemoryLakeClient(storage_path="/path/to/memories")

        local_tool = client.create_local_tool()
        local_tool.create(...)

    Example (Convenience class methods):
        # Create client for remote mode
        remote_client = MemoryLakeClient.from_remote(
            base_url="https://api.memorylake.example.com",
            memory_id="mem-xxx",
        )

        # Create client for local mode
        local_client = MemoryLakeClient.from_local(storage_path="/path/to/memories")
    """

    def __init__(
        self,
        base_url: Optional[str] = None,
        memory_id: Optional[str] = None,
        storage_path: Optional[Union[str, Path]] = None,
        timeout: float = 30.0,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        """
        Initialize the MemoryLake client factory.

        Args:
            base_url: Base URL of the MemoryLake server (e.g., "https://api.memorylake.example.com")
            memory_id: Unique memory identifier (e.g., "mem-42d72643d1af4f22892f00f3d953c428")
            storage_path: Path to local memory storage directory
            timeout: Request timeout in seconds (default: 30.0)
            headers: Optional additional HTTP headers (e.g., for authentication)
        """
        self.base_url: Optional[str] = base_url
        self.memory_id: Optional[str] = memory_id
        self.storage_path: Optional[Union[str, Path]] = storage_path
        self.timeout: float = timeout
        self.headers: Optional[dict[str, str]] = headers

    @classmethod
    def from_remote(
        cls,
        base_url: str,
        memory_id: str,
        timeout: float = 30.0,
        headers: Optional[dict[str, str]] = None,
    ) -> "MemoryLakeClient":
        """
        Create a client configured for remote mode.

        Args:
            base_url: Base URL of the MemoryLake server
            memory_id: Unique memory identifier
            timeout: Request timeout in seconds (default: 30.0)
            headers: Optional additional HTTP headers

        Returns:
            MemoryLakeClient instance configured for remote access

        Example:
            client = MemoryLakeClient.from_remote(
                base_url="https://api.memorylake.example.com",
                memory_id="mem-xxx",
            )
            sync_tool = client.create_sync_tool()
        """
        return cls(base_url=base_url, memory_id=memory_id, timeout=timeout, headers=headers)

    @classmethod
    def from_local(cls, storage_path: Union[str, Path]) -> "MemoryLakeClient":
        """
        Create a client configured for local file system mode.

        Args:
            storage_path: Path to local memory storage directory

        Returns:
            MemoryLakeClient instance configured for local file system access

        Example:
            client = MemoryLakeClient.from_local(storage_path="/tmp/memories")
            local_tool = client.create_local_tool()
        """
        return cls(storage_path=storage_path)

    def create_local_tool(self) -> MemoryTool:
        """
        Create a local file system-based memory tool instance.

        Returns:
            MemoryTool instance for local file system operations

        Raises:
            ValueError: If storage_path was not provided during initialization

        Example:
            client = MemoryLakeClient(storage_path="/tmp/memories")
            tool = client.create_local_tool()
            tool.create(CreateCommand(path="/notes.txt", file_text="Hello"))
        """
        if self.storage_path is None:
            raise ValueError("storage_path is required for local mode")
        return MemoryTool(base_path=self.storage_path)

    def create_sync_tool(self) -> MemoryLakeMemoryTool:
        """
        Create a synchronous remote memory tool instance.

        Returns:
            MemoryLakeMemoryTool instance for synchronous HTTP operations

        Raises:
            ValueError: If base_url or memory_id were not provided during initialization

        Example:
            client = MemoryLakeClient(
                base_url="https://api.memorylake.example.com",
                memory_id="mem-xxx",
            )
            tool = client.create_sync_tool()
            result = tool.create(CreateCommand(...))
            tool.close()
        """
        if self.base_url is None or self.memory_id is None:
            raise ValueError("base_url and memory_id are required for sync remote mode")
        return MemoryLakeMemoryTool(
            base_url=self.base_url,
            memory_id=self.memory_id,
            timeout=self.timeout,
            headers=self.headers,
        )

    def create_async_tool(self) -> AsyncMemoryLakeMemoryTool:
        """
        Create an asynchronous remote memory tool instance.

        Returns:
            AsyncMemoryLakeMemoryTool instance for asynchronous HTTP operations

        Raises:
            ValueError: If base_url or memory_id were not provided during initialization

        Example:
            client = MemoryLakeClient(
                base_url="https://api.memorylake.example.com",
                memory_id="mem-xxx",
            )
            async with client.create_async_tool() as tool:
                result = await tool.create(CreateCommand(...))
        """
        if self.base_url is None or self.memory_id is None:
            raise ValueError("base_url and memory_id are required for async remote mode")
        return AsyncMemoryLakeMemoryTool(
            base_url=self.base_url,
            memory_id=self.memory_id,
            timeout=self.timeout,
            headers=self.headers,
        )
