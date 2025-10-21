

from __future__ import annotations

import argparse
import asyncio
import json
import os
from typing import Dict, List

from anthropic import AsyncAnthropic
from anthropic.types.beta import (
    BetaContentBlockParam,
    BetaMemoryTool20250818Command,
    BetaMessageParam,
)
from pydantic import TypeAdapter

try:
    from memorylake import AsyncMemoryLakeMemoryTool, AsyncMemoryLakeMemoryToolError
except ModuleNotFoundError:  # pragma: no cover - fallback when not installed
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from memorylake import AsyncMemoryLakeMemoryTool, AsyncMemoryLakeMemoryToolError  # type: ignore

# Claude memory tool requires the context management beta header (2025-06-27).
_BETA_FEATURES = ["context-management-2025-06-27"]
_COMMAND_ADAPTER = TypeAdapter(BetaMemoryTool20250818Command)

os.environ["ANTHROPIC_API_KEY"] = "DUMMY"

os.environ["ANTHROPIC_MODEL"] = "claude-sonnet-4-5-20250929"

os.environ["ANTHROPIC_BASE_URL"] = "http://107.155.48.191:8000/anthropic"

os.environ["MEMORYLAKE_BASE_URL"] = "http://117.50.226.120:9180"

os.environ["MEMORYLAKE_MEMORY_ID"] = "mem-fd8b66ec086d4e9b9082f85eb7219dde"


async def run_chat(
    api_key: str | None,
    anthropic_base_url: str | None,
    model: str,
    memorylake_base_url: str,
    memory_id: str,
    verbose: bool = False,
) -> None:
    """
    Run async chat session with remote MemoryLake server.

    Args:
        api_key: Anthropic API key
        anthropic_base_url: Anthropic API base URL (optional)
        model: Claude model identifier
        memorylake_base_url: MemoryLake server base URL
        memory_id: Unique memory identifier
        verbose: If True, print full raw responses and tool use details
    """
    client = AsyncAnthropic(api_key=api_key, base_url=anthropic_base_url)
    async with AsyncMemoryLakeMemoryTool(
        base_url=memorylake_base_url,
        memory_id=memory_id,
    ) as memory_tool:
        messages: List[BetaMessageParam] = []
        local_menu: Dict[str, str] = {
            "help": "Show command list",
            "memory-view": "View memory path",
            "memory-create": "Create file",
            "memory-insert": "Insert text",
            "memory-replace": "Replace text",
            "memory-delete": "Delete path",
            "memory-rename": "Rename path",
            "memory-exists": "Check existence",
            "memory-list": "List directory",
            "memory-clear": "Clear all memories",
            "memory-stats": "View stats",
            "memory-exec": "Execute raw tool command",
        }

        mode_str = "VERBOSE mode" if verbose else "normal mode"
        print(
            f"🧠 Claude + MemoryLake Remote demo (ASYNC {mode_str}) (model: {model})\n"
            f"   Server: {memorylake_base_url}\n"
            f"   Memory ID: {memory_id}\n"
            f"   Type '/exit' to quit · Local commands: /help"
        )

        while True:
            user_input = input("\nYou: ").strip()
            if not user_input:
                continue
            if user_input.lower() in {"/exit", "/quit"}:
                print("Conversation ended.")
                break

            if user_input.startswith("/"):
                if await _handle_local_command(user_input, memory_tool, local_menu):
                    continue

            messages.append({"role": "user", "content": user_input})

            needs_follow_up = True
            while needs_follow_up:
                needs_follow_up = False

                response = await client.beta.messages.create(
                    model=model,
                    max_tokens=1024,
                    messages=messages,
                    tools=[{"type": "memory_20250818", "name": "memory"}],
                    betas=_BETA_FEATURES,
                    tool_choice={"type": "auto"},
                )

                if verbose:
                    # Print full raw response in verbose mode
                    print("\n" + "=" * 80)
                    print("RAW RESPONSE:")
                    print("=" * 80)
                    print(json.dumps(response.model_dump(), indent=2, ensure_ascii=False))
                    print("=" * 80 + "\n")

                messages.append({"role": "assistant", "content": response.content})

                # Collect all tool results
                tool_results: List[BetaContentBlockParam] = []
                printed_header = False

                for block in response.content:
                    if block.type == "text":
                        if not printed_header:
                            print("\nClaude:", end=" ")
                            printed_header = True
                        print(block.text)
                    elif block.type == "tool_use" and block.name == "memory":
                        # Always print tool use details
                        print("\n" + "-" * 80)
                        print("🔧 TOOL USE:")
                        print("-" * 80)
                        input_dict = dict(block.input) if hasattr(block.input, 'items') else block.input
                        print(f"Command: {input_dict.get('command', 'unknown')}")
                        if 'path' in input_dict:
                            print(f"Path: {input_dict['path']}")
                        if 'old_path' in input_dict:
                            print(f"Old Path: {input_dict['old_path']}")
                        if 'new_path' in input_dict:
                            print(f"New Path: {input_dict['new_path']}")
                        if 'file_text' in input_dict:
                            preview = str(input_dict['file_text'])[:100]
                            if len(str(input_dict['file_text'])) > 100:
                                preview += "..."
                            print(f"Content: {preview}")
                        if 'old_str' in input_dict:
                            print(f"Old String: {str(input_dict['old_str'])[:50]}...")
                        if 'new_str' in input_dict:
                            print(f"New String: {str(input_dict['new_str'])[:50]}...")
                        if 'insert_line' in input_dict:
                            print(f"Insert Line: {input_dict['insert_line']}")
                        if 'insert_text' in input_dict:
                            print(f"Insert Text: {str(input_dict['insert_text'])[:50]}...")
                        if 'view_range' in input_dict:
                            print(f"View Range: {input_dict['view_range']}")
                        print("-" * 80)

                        if verbose:
                            # Print full raw input in verbose mode
                            print(f"Full Input: {json.dumps(input_dict, indent=2, ensure_ascii=False)}")
                            print("-" * 80)

                        command = _COMMAND_ADAPTER.validate_python(block.input)
                        result_text = await memory_tool.execute(command)

                        result_preview = str(result_text)[:200]
                        if len(str(result_text)) > 200:
                            result_preview += "..."
                        print(f"✓ Result: {result_preview}\n")

                        if verbose:
                            print(f"Full Result: {result_text}\n")

                        tool_result_block: BetaContentBlockParam = {
                            "type": "tool_result",
                            "tool_use_id": block.id,
                            "content": result_text,
                        }
                        tool_results.append(tool_result_block)

                # If there were any tool uses, add all results and continue
                if tool_results:
                    messages.append({"role": "user", "content": tool_results})
                    needs_follow_up = True


async def _handle_local_command(
    raw: str,
    memory_tool: AsyncMemoryLakeMemoryTool,
    menu: Dict[str, str],
) -> bool:
    command_line = raw[1:].strip()
    if not command_line:
        _print_menu(menu)
        return True

    parts = command_line.split()
    name = parts[0]
    args = parts[1:]

    try:
        if name == "help":
            _print_menu(menu)
        elif name == "memory-view":
            path = args[0] if args else _prompt("Path")
            view_range = None
            if len(args) >= 3:
                view_range = [int(args[1]), int(args[2])]
            else:
                range_input = _prompt("Line range (e.g. 1 10, optional)")
                if range_input:
                    tokens = range_input.replace(",", " ").split()
                    if len(tokens) == 2:
                        view_range = [int(tokens[0]), int(tokens[1])]
            # Use execute with view command
            from anthropic.types.beta import BetaMemoryTool20250818ViewCommand
            view_cmd = BetaMemoryTool20250818ViewCommand(
                command="view",
                path=path,
                view_range=view_range,
            )
            result = await memory_tool.execute(view_cmd)
            print(result)
        elif name == "memory-create":
            path = args[0] if args else _prompt("Path")
            text = " ".join(args[1:]) if len(args) > 1 else _prompt("Content")
            from anthropic.types.beta import BetaMemoryTool20250818CreateCommand
            create_cmd = BetaMemoryTool20250818CreateCommand(
                command="create",
                path=path,
                file_text=text,
            )
            result = await memory_tool.execute(create_cmd)
            print(result)
        elif name == "memory-insert":
            path = args[0] if args else _prompt("Path")
            line_index = int(args[1]) if len(args) > 1 else int(_prompt("Line number"))
            text = " ".join(args[2:]) if len(args) > 2 else _prompt("Text")
            from anthropic.types.beta import BetaMemoryTool20250818InsertCommand
            insert_cmd = BetaMemoryTool20250818InsertCommand(
                command="insert",
                path=path,
                insert_line=line_index,
                insert_text=text,
            )
            result = await memory_tool.execute(insert_cmd)
            print(result)
        elif name == "memory-replace":
            path = args[0] if args else _prompt("Path")
            old = args[1] if len(args) > 1 else _prompt("Old text")
            new = args[2] if len(args) > 2 else _prompt("New text")
            from anthropic.types.beta import BetaMemoryTool20250818StrReplaceCommand
            replace_cmd = BetaMemoryTool20250818StrReplaceCommand(
                command="str_replace",
                path=path,
                old_str=old,
                new_str=new,
            )
            result = await memory_tool.execute(replace_cmd)
            print(result)
        elif name == "memory-delete":
            path = args[0] if args else _prompt("Path")
            from anthropic.types.beta import BetaMemoryTool20250818DeleteCommand
            delete_cmd = BetaMemoryTool20250818DeleteCommand(
                command="delete",
                path=path,
            )
            result = await memory_tool.execute(delete_cmd)
            print(result)
        elif name == "memory-rename":
            old = args[0] if args else _prompt("Old path")
            new = args[1] if len(args) > 1 else _prompt("New path")
            from anthropic.types.beta import BetaMemoryTool20250818RenameCommand
            rename_cmd = BetaMemoryTool20250818RenameCommand(
                command="rename",
                old_path=old,
                new_path=new,
            )
            result = await memory_tool.execute(rename_cmd)
            print(result)
        elif name == "memory-exists":
            path = args[0] if args else _prompt("Path")
            exists = await memory_tool.memory_exists(path)
            print("Exists" if exists else "Does not exist")
        elif name == "memory-list":
            path = args[0] if args else "/memories"
            entries = await memory_tool.list_memories(path)
            if not entries:
                print("(empty)")
            else:
                for item in entries:
                    print(item)
        elif name == "memory-clear":
            confirm = _prompt("Are you sure you want to clear all memories? (yes/no)")
            if confirm.lower() == "yes":
                result = await memory_tool.clear_all_memory()
                print(result)
            else:
                print("Cancelled")
        elif name == "memory-stats":
            stats = await memory_tool.stats()
            for key, value in stats.items():
                print(f"{key}: {value}")
        elif name == "memory-exec":
            await _run_exec_command(memory_tool, args)
        else:
            print("Unknown command")
    except AsyncMemoryLakeMemoryToolError as exc:
        print(f"Error: {exc}")
    except ValueError as exc:
        print(f"Invalid input: {exc}")
    except Exception as exc:  # pragma: no cover - safety net
        print(f"Error: {exc}")
    return True


async def _run_exec_command(memory_tool: AsyncMemoryLakeMemoryTool, args: List[str]) -> None:
    command = args[0] if args else _prompt("command (view/create/insert/str_replace/delete/rename)")
    extra = args[1:]
    payload: Dict[str, object] = {"command": command}

    if command == "view":
        path = extra[0] if extra else _prompt("Path")
        payload["path"] = path
        if len(extra) >= 3:
            payload["view_range"] = [int(extra[1]), int(extra[2])]
        else:
            range_input = _prompt("Line range (e.g. 1 10, optional)")
            if range_input:
                tokens = range_input.replace(",", " ").split()
                if len(tokens) == 2:
                    payload["view_range"] = [int(tokens[0]), int(tokens[1])]
    elif command == "create":
        path = extra[0] if extra else _prompt("Path")
        text = " ".join(extra[1:]) if len(extra) > 1 else _prompt("Content")
        payload.update({"path": path, "file_text": text})
    elif command == "insert":
        path = extra[0] if extra else _prompt("Path")
        index = int(extra[1]) if len(extra) > 1 else int(_prompt("Line number"))
        text = " ".join(extra[2:]) if len(extra) > 2 else _prompt("Text")
        payload.update({"path": path, "insert_line": index, "insert_text": text})
    elif command == "str_replace":
        path = extra[0] if extra else _prompt("Path")
        old = extra[1] if len(extra) > 1 else _prompt("Old text")
        new = extra[2] if len(extra) > 2 else _prompt("New text")
        payload.update({"path": path, "old_str": old, "new_str": new})
    elif command == "delete":
        path = extra[0] if extra else _prompt("Path")
        payload["path"] = path
    elif command == "rename":
        old = extra[0] if extra else _prompt("Old path")
        new = extra[1] if len(extra) > 1 else _prompt("New path")
        payload.update({"old_path": old, "new_path": new})
    else:
        print("Unsupported tool command")
        return

    result = await memory_tool.execute_tool_payload(payload)
    print(result)


def _print_menu(menu: Dict[str, str]) -> None:
    print("Local commands:")
    for key, desc in menu.items():
        print(f"/{key} - {desc}")
    print("/exit - exit")


def _prompt(label: str) -> str:
    return input(f"{label}: ").strip()


def _parse_args() -> argparse.Namespace:
    default_model = os.environ.get("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    parser = argparse.ArgumentParser(description="Async Anthropic memory tool chat demo with remote MemoryLake server.")
    parser.add_argument(
        "--api-key",
        default=os.environ.get("ANTHROPIC_API_KEY"),
        help="Anthropic API key (falls back to ANTHROPIC_API_KEY env).",
    )
    parser.add_argument(
        "--anthropic-base-url",
        default=os.environ.get("ANTHROPIC_BASE_URL"),
        help="Anthropic API base URL (falls back to ANTHROPIC_BASE_URL env).",
    )
    parser.add_argument(
        "--model",
        default=default_model,
        help=f"Claude model identifier (default: {default_model}).",
    )
    parser.add_argument(
        "--memorylake-base-url",
        default=os.environ.get("MEMORYLAKE_BASE_URL"),
        help="MemoryLake server base URL (falls back to MEMORYLAKE_BASE_URL env).",
    )
    parser.add_argument(
        "--memory-id",
        default=os.environ.get("MEMORYLAKE_MEMORY_ID"),
        help="Memory identifier (falls back to MEMORYLAKE_MEMORY_ID env).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Show full raw responses and tool use details.",
    )
    args = parser.parse_args()
    if not args.api_key:
        parser.error(
            "Anthropic API key is required. Provide via --api-key or set ANTHROPIC_API_KEY."
        )
    return args


if __name__ == "__main__":
    args = _parse_args()
    asyncio.run(
        run_chat(
            api_key=args.api_key,
            anthropic_base_url=args.anthropic_base_url,
            model=args.model,
            memorylake_base_url=args.memorylake_base_url,
            memory_id=args.memory_id,
            verbose=args.verbose,
        )
    )
