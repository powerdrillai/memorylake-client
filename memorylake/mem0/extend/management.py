"""Management client for project-related operations.

This module provides both synchronous and asynchronous clients for managing
projects within organizations via the Mem0 API.
"""

import os
from typing import Any, List, Optional

import httpx

from memorylake.mem0.client.utils import api_error_handler


class ManagementClient:
    """Synchronous client for managing projects.

    This class provides methods to create, retrieve, update, and delete
    projects using the Mem0 API.

    Attributes:
        api_key (str): The API key for authenticating with the Mem0 API.
        host (str): The base URL for the Mem0 API.
        client (httpx.Client): The HTTP client used for making API requests.
        org_id (str): Organization ID.
    """

    api_key: Optional[str]
    host: str
    org_id: str
    client: httpx.Client

    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        org_id: Optional[str] = None,
        client: Optional[httpx.Client] = None,
    ):
        """Initialize the ManagementClient.

        Args:
            api_key: The API key for authenticating with the Mem0 API. If not
                     provided, it will attempt to use the MEM0_API_KEY
                     environment variable.
            host: The base URL for the Mem0 API. Defaults to
                  "https://api.mem0.ai".
            org_id: The ID of the organization. Required for project operations.
            client: A custom httpx.Client instance. If provided, it will be
                    used instead of creating a new one. Note that base_url and
                    headers will be set/overridden as needed.

        Raises:
            ValueError: If no API key is provided or found in the environment.
            ValueError: If org_id is not provided.
        """
        self.api_key = api_key or os.getenv("MEM0_API_KEY")

        if not self.api_key:
            raise ValueError("Mem0 API Key not provided. Please provide an API Key.")

        if not host:
            raise ValueError("host is required for ManagementClient.")

        if not org_id:
            raise ValueError("org_id is required for ManagementClient.")

        self.host = host
        self.org_id = org_id

        if client is not None:
            self.client = client
            # Ensure the client has the correct base_url and headers
            self.client.base_url = httpx.URL(self.host)
            self.client.headers.update(
                {
                    "Authorization": f"Token {self.api_key}",
                }
            )
        else:
            self.client = httpx.Client(
                base_url=self.host,
                headers={
                    "Authorization": f"Token {self.api_key}",
                },
                timeout=300,
            )

    def _get_projects_url(self) -> str:
        """Get the URL for project list operations."""
        return f"/api/v1/orgs/organizations/{self.org_id}/projects/"

    def _get_project_url(self, project_id: str) -> str:
        """Get the URL for single project operations."""
        return f"/api/v1/orgs/organizations/{self.org_id}/projects/{project_id}/"

    @api_error_handler
    def create_project(self, name: str) -> dict[str, Any]:
        """Create a new project.

        Args:
            name: The name of the project to create.

        Returns:
            A dictionary containing the created project details with keys:
                - message: Success message
                - project_id: The unique identifier of the created project

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
        """
        payload: dict[str, Any] = {"name": name}
        response = self.client.post(self._get_projects_url(), json=payload)
        response.raise_for_status()
        return response.json()

    @api_error_handler
    def get_project(self, project_id: str) -> dict[str, Any]:
        """Retrieve a specific project by ID.

        Args:
            project_id: The ID of the project to retrieve.

        Returns:
            A dictionary containing the project details with keys:
                - project_id: Unique identifier of the project
                - name: Name of the project
                - description: Description of the project (optional)
                - created_at: Timestamp of creation
                - updated_at: Timestamp of last update
                - members: List of project members

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
            MemoryNotFoundError: If the project doesn't exist.
        """
        response = self.client.get(self._get_project_url(project_id))
        response.raise_for_status()
        return response.json()

    @api_error_handler
    def list_projects(self) -> list[dict[str, Any]]:
        """Retrieve all projects for the organization.

        Returns:
            A list of dictionaries, each containing project details with keys:
                - project_id: Unique identifier of the project
                - name: Name of the project
                - description: Description of the project (optional)
                - created_at: Timestamp of creation
                - updated_at: Timestamp of last update
                - members: List of project members

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
        """
        response = self.client.get(self._get_projects_url())
        response.raise_for_status()
        return response.json()

    @api_error_handler
    def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        custom_instructions: Optional[str] = None,
        custom_categories: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Update a project by ID.

        Args:
            project_id: The ID of the project to update.
            name: New name for the project.
            description: New description for the project.
            custom_instructions: Custom instructions for adding memories.
            custom_categories: Custom categories for memories.

        Returns:
            A dictionary containing the API response with key:
                - message: Success message

        Raises:
            ValueError: If no fields are provided for update.
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
            MemoryNotFoundError: If the project doesn't exist.
        """
        if (
            name is None
            and description is None
            and custom_instructions is None
            and custom_categories is None
        ):
            raise ValueError(
                "At least one field (name, description, custom_instructions, "
                + "or custom_categories) must be provided for update."
            )

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if custom_instructions is not None:
            payload["custom_instructions"] = custom_instructions
        if custom_categories is not None:
            payload["custom_categories"] = custom_categories

        response = self.client.patch(self._get_project_url(project_id), json=payload)
        response.raise_for_status()
        return response.json()

    @api_error_handler
    def delete_project(self, project_id: str) -> dict[str, Any]:
        """Delete a specific project by ID.

        Args:
            project_id: The ID of the project to delete.

        Returns:
            A dictionary containing the API response with key:
                - message: Success message

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
        """
        response = self.client.delete(self._get_project_url(project_id))
        response.raise_for_status()
        return response.json()


class AsyncManagementClient:
    """Asynchronous client for managing projects.

    This class provides asynchronous methods to create, retrieve, update,
    and delete projects using the Mem0 API.

    Attributes:
        api_key (str): The API key for authenticating with the Mem0 API.
        host (str): The base URL for the Mem0 API.
        async_client (httpx.AsyncClient): The async HTTP client for API requests.
        org_id (str): Organization ID.
    """

    api_key: Optional[str]
    host: str
    org_id: str
    async_client: httpx.AsyncClient

    def __init__(
        self,
        api_key: Optional[str] = None,
        host: Optional[str] = None,
        org_id: Optional[str] = None,
        client: Optional[httpx.AsyncClient] = None,
    ):
        """Initialize the AsyncManagementClient.

        Args:
            api_key: The API key for authenticating with the Mem0 API. If not
                     provided, it will attempt to use the MEM0_API_KEY
                     environment variable.
            host: The base URL for the Mem0 API.
            org_id: The ID of the organization. Required for project operations.
            client: A custom httpx.AsyncClient instance. If provided, it will be
                    used instead of creating a new one. Note that base_url and
                    headers will be set/overridden as needed.

        Raises:
            ValueError: If no API key is provided or found in the environment.
            ValueError: If org_id is not provided.
        """
        self.api_key = api_key or os.getenv("MEM0_API_KEY")

        if not self.api_key:
            raise ValueError("Mem0 API Key not provided. Please provide an API Key.")

        if not host:
            raise ValueError("host is required for AsyncManagementClient.")

        if not org_id:
            raise ValueError("org_id is required for AsyncManagementClient.")

        self.host = host
        self.org_id = org_id

        if client is not None:
            self.async_client = client
            # Ensure the client has the correct base_url and headers
            self.async_client.base_url = httpx.URL(self.host)
            self.async_client.headers.update(
                {
                    "Authorization": f"Token {self.api_key}",
                }
            )
        else:
            self.async_client = httpx.AsyncClient(
                base_url=self.host,
                headers={
                    "Authorization": f"Token {self.api_key}",
                },
                timeout=300,
            )

    async def __aenter__(self) -> "AsyncManagementClient":
        """Async context manager entry."""
        return self

    async def __aexit__(
        self,
        exc_type: Optional[type[BaseException]],
        exc_val: Optional[BaseException],
        exc_tb: Any,
    ) -> None:
        """Async context manager exit."""
        await self.async_client.aclose()

    def _get_projects_url(self) -> str:
        """Get the URL for project list operations."""
        return f"/api/v1/orgs/organizations/{self.org_id}/projects/"

    def _get_project_url(self, project_id: str) -> str:
        """Get the URL for single project operations."""
        return f"/api/v1/orgs/organizations/{self.org_id}/projects/{project_id}/"

    @api_error_handler
    async def create_project(self, name: str) -> dict[str, Any]:
        """Create a new project.

        Args:
            name: The name of the project to create.

        Returns:
            A dictionary containing the created project details with keys:
                - message: Success message
                - project_id: The unique identifier of the created project

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
        """
        payload: dict[str, Any] = {"name": name}
        response = await self.async_client.post(self._get_projects_url(), json=payload)
        response.raise_for_status()
        return response.json()

    @api_error_handler
    async def get_project(self, project_id: str) -> dict[str, Any]:
        """Retrieve a specific project by ID.

        Args:
            project_id: The ID of the project to retrieve.

        Returns:
            A dictionary containing the project details with keys:
                - project_id: Unique identifier of the project
                - name: Name of the project
                - description: Description of the project (optional)
                - created_at: Timestamp of creation
                - updated_at: Timestamp of last update
                - members: List of project members

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
            MemoryNotFoundError: If the project doesn't exist.
        """
        response = await self.async_client.get(self._get_project_url(project_id))
        response.raise_for_status()
        return response.json()

    @api_error_handler
    async def list_projects(self) -> list[dict[str, Any]]:
        """Retrieve all projects for the organization.

        Returns:
            A list of dictionaries, each containing project details with keys:
                - project_id: Unique identifier of the project
                - name: Name of the project
                - description: Description of the project (optional)
                - created_at: Timestamp of creation
                - updated_at: Timestamp of last update
                - members: List of project members

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
        """
        response = await self.async_client.get(self._get_projects_url())
        response.raise_for_status()
        return response.json()

    @api_error_handler
    async def update_project(
        self,
        project_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        custom_instructions: Optional[str] = None,
        custom_categories: Optional[List[str]] = None,
    ) -> dict[str, Any]:
        """Update a project by ID.

        Args:
            project_id: The ID of the project to update.
            name: New name for the project.
            description: New description for the project.
            custom_instructions: Custom instructions for adding memories.
            custom_categories: Custom categories for memories.

        Returns:
            A dictionary containing the API response with key:
                - message: Success message

        Raises:
            ValueError: If no fields are provided for update.
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
            MemoryNotFoundError: If the project doesn't exist.
        """
        if (
            name is None
            and description is None
            and custom_instructions is None
            and custom_categories is None
        ):
            raise ValueError(
                "At least one field (name, description, custom_instructions, "
                + "or custom_categories) must be provided for update."
            )

        payload: dict[str, Any] = {}
        if name is not None:
            payload["name"] = name
        if description is not None:
            payload["description"] = description
        if custom_instructions is not None:
            payload["custom_instructions"] = custom_instructions
        if custom_categories is not None:
            payload["custom_categories"] = custom_categories

        response = await self.async_client.patch(
            self._get_project_url(project_id),
            json=payload,
        )
        response.raise_for_status()
        return response.json()

    @api_error_handler
    async def delete_project(self, project_id: str) -> dict[str, Any]:
        """Delete a specific project by ID.

        Args:
            project_id: The ID of the project to delete.

        Returns:
            A dictionary containing the API response with key:
                - message: Success message

        Raises:
            ValidationError: If the input data is invalid.
            AuthenticationError: If authentication fails.
            RateLimitError: If rate limits are exceeded.
            NetworkError: If network connectivity issues occur.
        """
        response = await self.async_client.delete(self._get_project_url(project_id))
        response.raise_for_status()
        return response.json()
