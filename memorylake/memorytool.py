"""
Filesystem-based implementation of Anthropic's memory tool contract.

This module exposes ``MemoryTool`` which subclasses ``BetaAbstractMemoryTool`` and
implements the required commands described in Anthropic's official SDK examples:

* view
* create
* str_replace
* insert
* delete
* rename
* clear_all_memory

On top of the tool interface (used by Anthropic's ``tool_runner``), a handful of
lightweight helper methods are provided for direct programmatic access so that
callers can manage memories without synthesising command payloads themselves.
"""

from __future__ import annotations

import shutil
from collections.abc import Mapping
from pathlib import Path
from typing import Final

from anthropic.lib.tools import BetaAbstractMemoryTool
from anthropic.types.beta import (
    BetaMemoryTool20250818Command,
    BetaMemoryTool20250818CreateCommand,
    BetaMemoryTool20250818DeleteCommand,
    BetaMemoryTool20250818InsertCommand,
    BetaMemoryTool20250818RenameCommand,
    BetaMemoryTool20250818StrReplaceCommand,
    BetaMemoryTool20250818ViewCommand,
)
from pydantic import TypeAdapter
from typing_extensions import override

__all__ = ["MemoryTool", "MemoryToolError", "MemoryToolPathError", "MemoryToolOperationError"]


class MemoryToolError(Exception):
    """Base error raised by :class:`MemoryTool`."""


class MemoryToolPathError(MemoryToolError):
    """Raised when a provided memory path is invalid or unsafe."""


class MemoryToolOperationError(MemoryToolError):
    """Raised when a filesystem operation fails."""


class MemoryTool(BetaAbstractMemoryTool):
    """Filesystem-backed implementation of the Anthropic memory tool contract."""

    _MEMORY_ROOT_NAME: Final[str] = "memories"
    _NAMESPACE_PREFIX: Final[str] = "/memories"
    _COMMAND_ADAPTER: Final[TypeAdapter[BetaMemoryTool20250818Command]] = TypeAdapter(
        BetaMemoryTool20250818Command
    )

    def __init__(self, base_path: str | Path = "./memory") -> None:
        super().__init__()
        self._base_path: Path = Path(base_path).expanduser().resolve()
        self._memory_root: Path = self._base_path / self._MEMORY_ROOT_NAME
        self._memory_root.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # Tool interface (invoked by Anthropic runtime)
    # ------------------------------------------------------------------ #
    @override
    def view(self, command: BetaMemoryTool20250818ViewCommand) -> str:
        target = self._resolve_path(command.path)

        if target.is_dir():
            entries: list[str] = []
            for item in sorted(target.iterdir()):
                if item.name.startswith("."):
                    continue
                suffix = "/" if item.is_dir() else ""
                entries.append(f"{item.name}{suffix}")

            lines = [f"Directory: {command.path}"]
            lines.extend(f"- {entry}" for entry in entries)
            return "\n".join(lines)

        if not target.is_file():
            raise MemoryToolOperationError(f"path does not exist: {command.path}")

        content = target.read_text(encoding="utf-8").splitlines()
        if command.view_range:
            start_line = max(1, command.view_range[0]) - 1
            end_line = (
                len(content)
                if command.view_range[1] == -1
                else max(command.view_range[1], start_line + 1)
            )
            content = content[start_line:end_line]
            base_idx = start_line + 1
        else:
            base_idx = 1

        numbered = [f"{idx + base_idx:4d}: {line}" for idx, line in enumerate(content)]
        output_lines: list[str] = [f"File: {command.path}"]
        if numbered:
            output_lines.extend(numbered)
        else:
            output_lines.append("(empty file)")
        return "\n".join(output_lines)

    @override
    def create(self, command: BetaMemoryTool20250818CreateCommand) -> str:
        target = self._resolve_path(command.path)
        self._ensure_parent_dir(target)
        target.write_text(command.file_text, encoding="utf-8")
        return f"File created: {command.path}"

    @override
    def str_replace(self, command: BetaMemoryTool20250818StrReplaceCommand) -> str:
        target = self._resolve_path(command.path)
        if not target.is_file():
            raise MemoryToolOperationError(f"file not found: {command.path}")

        content = target.read_text(encoding="utf-8")
        matches = content.count(command.old_str)
        if matches == 0:
            raise MemoryToolOperationError(f"text not found in {command.path}")
        if matches > 1:
            raise MemoryToolOperationError(
                f"text appears {matches} times in {command.path}; must be unique"
            )

        target.write_text(content.replace(command.old_str, command.new_str), encoding="utf-8")
        return f"File updated: {command.path}"

    @override
    def insert(self, command: BetaMemoryTool20250818InsertCommand) -> str:
        target = self._resolve_path(command.path)
        if not target.is_file():
            raise MemoryToolOperationError(f"file not found: {command.path}")

        lines = target.read_text(encoding="utf-8").splitlines()
        if command.insert_line < 0 or command.insert_line > len(lines):
            raise MemoryToolOperationError(
                f"insert_line must be between 0 and {len(lines)}, got {command.insert_line}"
            )

        lines.insert(command.insert_line, command.insert_text.rstrip("\n"))
        target.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return f"Line inserted in {command.path}"

    @override
    def delete(self, command: BetaMemoryTool20250818DeleteCommand) -> str:
        if command.path.rstrip("/") == self._NAMESPACE_PREFIX:
            raise MemoryToolPathError("refusing to delete the /memories root")

        target = self._resolve_path(command.path)
        if target.is_file():
            target.unlink()
            return f"File deleted: {command.path}"
        if target.is_dir():
            shutil.rmtree(target)
            return f"Directory deleted: {command.path}"

        raise MemoryToolOperationError(f"path does not exist: {command.path}")

    @override
    def rename(self, command: BetaMemoryTool20250818RenameCommand) -> str:
        source = self._resolve_path(command.old_path)
        destination = self._resolve_path(command.new_path)

        if not source.exists():
            raise MemoryToolOperationError(f"source path not found: {command.old_path}")
        if destination.exists():
            raise MemoryToolOperationError(f"destination already exists: {command.new_path}")

        self._ensure_parent_dir(destination)
        source.rename(destination)
        return f"Renamed {command.old_path} to {command.new_path}"

    @override
    def clear_all_memory(self) -> str:
        if self._memory_root.exists():
            shutil.rmtree(self._memory_root)
        self._memory_root.mkdir(parents=True, exist_ok=True)
        return "Cleared all memories"

    # ------------------------------------------------------------------ #
    # Helper methods for direct programmatic use
    # ------------------------------------------------------------------ #
    def create_file(self, path: str, file_text: str) -> None:
        self.create(
            BetaMemoryTool20250818CreateCommand(
                command="create",
                path=path,
                file_text=file_text,
            )
        )

    def view_path(
        self,
        path: str,
        view_range: tuple[int, int] | None = None,
    ) -> str:
        return self.view(
            BetaMemoryTool20250818ViewCommand(
                command="view",
                path=path,
                view_range=list(view_range) if view_range else None,
            )
        )

    def replace_text(self, path: str, old_text: str, new_text: str) -> None:
        self.str_replace(
            BetaMemoryTool20250818StrReplaceCommand(
                command="str_replace",
                path=path,
                old_str=old_text,
                new_str=new_text,
            )
        )

    def insert_line(self, path: str, line_index: int, insert_text: str) -> None:
        self.insert(
            BetaMemoryTool20250818InsertCommand(
                command="insert",
                path=path,
                insert_line=line_index,
                insert_text=insert_text,
            )
        )

    def delete_path(self, path: str) -> None:
        self.delete(
            BetaMemoryTool20250818DeleteCommand(
                command="delete",
                path=path,
            )
        )

    def rename_path(self, old_path: str, new_path: str) -> None:
        self.rename(
            BetaMemoryTool20250818RenameCommand(
                command="rename",
                old_path=old_path,
                new_path=new_path,
            )
        )

    def memory_exists(self, path: str) -> bool:
        try:
            return self._resolve_path(path).exists()
        except MemoryToolPathError:
            raise
        except Exception as exc:  # pragma: no cover - defensive
            raise MemoryToolOperationError(f"failed to test {path}: {exc}") from exc

    def list_memories(self, path: str = "/memories") -> list[str]:
        target = self._resolve_path(path)
        if not target.is_dir():
            raise MemoryToolOperationError(f"path is not a directory: {path}")

        results: list[str] = []
        for item in sorted(target.rglob("*")):
            if item.name.startswith("."):
                continue
            relative = item.relative_to(self._memory_root)
            display = f"{self._NAMESPACE_PREFIX}/{relative.as_posix()}"
            if item.is_dir():
                display += "/"
            results.append(display)
        return results

    def stats(self) -> dict[str, int]:
        totals = {"files": 0, "directories": 0, "bytes": 0}
        if not self._memory_root.exists():
            return totals

        for item in self._memory_root.rglob("*"):
            if item.name.startswith("."):
                continue
            if item.is_file():
                totals["files"] += 1
                totals["bytes"] += item.stat().st_size
            elif item.is_dir():
                totals["directories"] += 1
        return totals

    def execute_tool_payload(self, payload: Mapping[str, object]) -> str:
        """Validate and execute a raw tool payload from Anthropic responses."""
        command: BetaMemoryTool20250818Command = self._COMMAND_ADAPTER.validate_python(payload)
        result = self.execute(command)
        # Always return the string representation of the result
        return str(result)

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #
    def _resolve_path(self, memory_path: str) -> Path:
        if not memory_path.startswith(self._NAMESPACE_PREFIX):
            raise MemoryToolPathError(
                f"path must start with {self._NAMESPACE_PREFIX}: {memory_path}"
            )

        relative_part = memory_path[len(self._NAMESPACE_PREFIX):].lstrip("/")
        base = self._memory_root if not relative_part else self._memory_root / relative_part

        try:
            resolved = base.resolve()
            resolved.relative_to(self._memory_root)
        except ValueError as exc:
            raise MemoryToolPathError(f"path escapes memory root: {memory_path}") from exc

        return resolved

    def _ensure_parent_dir(self, target: Path) -> None:
        target.parent.mkdir(parents=True, exist_ok=True)
