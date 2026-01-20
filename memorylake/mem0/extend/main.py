from __future__ import annotations

import uuid
from typing import Any, Literal, Optional

from memorylake.mem0.client.main import AsyncMemoryClient, MemoryClient
from memorylake.mem0.client.utils import api_error_handler
from memorylake.mem0.memory.telemetry import capture_client_event


class MemoryLakeClient(MemoryClient):

    def new_reflection(
        self,
        target_type: Literal["user", "location"],
        target_id: str,
    ) -> Reflection:
        return Reflection(
            target_type=target_type,
            target_id=target_id,
            memory_client=self,
        )

    @api_error_handler
    def end_session(
        self,
        chat_session_id: str,
        timestamp: int,
    ) -> dict[str, Any]:
        """End a chat session.

        Args:
            chat_session_id: The ID of the chat session to end.
            timestamp: The timestamp of the session end event.

        Returns:
            A dictionary containing the API response.
        """
        payload = self._prepare_params(
            {
                "chat_session_id": chat_session_id,
                "timestamp": timestamp,
                "event_type": "end",
            }
        )
        response = self.client.post("/v3/chat_session/event/", json=payload)
        response.raise_for_status()
        capture_client_event(
            "client.end_session",
            self,
            {"chat_session_id": chat_session_id, "sync_type": "sync"},
        )
        return response.json()

    def prepare_params(self, kwargs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return self._prepare_params(kwargs)


class AsyncMemoryLakeClient(AsyncMemoryClient):

    def new_reflection(
        self,
        target_type: Literal["user", "location"],
        target_id: str,
    ) -> AsyncReflection:
        return AsyncReflection(
            target_type=target_type,
            target_id=target_id,
            memory_client=self,
        )

    @api_error_handler
    async def end_session(
        self,
        chat_session_id: str,
        timestamp: int,
    ) -> dict[str, Any]:
        """End a chat session.

        Args:
            chat_session_id: The ID of the chat session to end.
            timestamp: The timestamp of the session end event.

        Returns:
            A dictionary containing the API response.
        """
        payload = self._prepare_params(
            {
                "chat_session_id": chat_session_id,
                "timestamp": timestamp,
                "event_type": "end",
            }
        )
        response = await self.async_client.post("/v3/chat_session/event/", json=payload)
        response.raise_for_status()
        capture_client_event(
            "client.end_session",
            self,
            {"chat_session_id": chat_session_id, "sync_type": "async"},
        )
        return response.json()

    def prepare_params(self, kwargs: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        return self._prepare_params(kwargs)


class Reflection:

    target_type: Literal["user", "location"]
    target_id: str
    memory_client: MemoryLakeClient
    reflect_id: str

    def __init__(
        self,
        target_type: Literal["user", "location"],
        target_id: str,
        memory_client: MemoryLakeClient,
    ):
        self.target_type = target_type
        self.target_id = target_id
        self.memory_client = memory_client
        self.reflect_id = str(uuid.uuid4())

    @api_error_handler
    def recollect(self, **kwargs: Any) -> dict[str, Any]:
        kwargs["metadata"] = self._prepare_metadata(kwargs.get("metadata") or {})
        payload = self.memory_client.prepare_params(kwargs)
        response = self.memory_client.client.post("/v3/memories/recollect/", json=payload)
        response.raise_for_status()
        capture_client_event(
            "client.recollect",
            self.memory_client,
            {"reflect_id": self.reflect_id, "sync_type": "sync"},
        )
        return response.json()

    def save(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs["metadata"] = self._prepare_metadata(kwargs.get("metadata") or {})
        return self.memory_client.add(messages, **kwargs)

    def _prepare_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        user_extension: dict[str, Any] = metadata.get("memorylake_extension") or {}
        metadata["memorylake_extension"] = {
            **user_extension,
            "reflect_id": self.reflect_id,
            "reflect_target": {
                "target_type": self.target_type,
                "target_id": self.target_id,
            },
        }

        return metadata


class AsyncReflection:

    target_type: Literal["user", "location"]
    target_id: str
    memory_client: AsyncMemoryLakeClient
    reflect_id: str

    def __init__(
        self,
        target_type: Literal["user", "location"],
        target_id: str,
        memory_client: AsyncMemoryLakeClient,
    ):
        self.target_type = target_type
        self.target_id = target_id
        self.memory_client = memory_client
        self.reflect_id = str(uuid.uuid4())

    @api_error_handler
    async def recollect(self, **kwargs: Any) -> dict[str, Any]:
        kwargs["metadata"] = self._prepare_metadata(kwargs.get("metadata") or {})
        payload = self.memory_client.prepare_params(kwargs)
        response = await self.memory_client.async_client.post("/v3/memories/recollect/", json=payload)
        response.raise_for_status()
        capture_client_event(
            "client.recollect",
            self.memory_client,
            {"reflect_id": self.reflect_id, "sync_type": "async"},
        )
        return response.json()

    async def save(self, messages: Any, **kwargs: Any) -> dict[str, Any]:
        kwargs["metadata"] = self._prepare_metadata(kwargs.get("metadata") or {})
        return await self.memory_client.add(messages, **kwargs)

    def _prepare_metadata(self, metadata: dict[str, Any]) -> dict[str, Any]:
        user_extension: dict[str, Any] = metadata.get("memorylake_extension") or {}
        metadata["memorylake_extension"] = {
            **user_extension,
            "reflect_id": self.reflect_id,
            "reflect_target": {
                "target_type": self.target_type,
                "target_id": self.target_id,
            },
        }

        return metadata
