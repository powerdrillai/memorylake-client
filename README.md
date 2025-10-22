# MemoryLake

[![codecov](https://codecov.io/gh/powerdrillai/memorylake-client/branch/main/graph/badge.svg)](https://codecov.io/gh/powerdrillai/memorylake-client)

## Developer Setup

**Prerequisites:** Python 3.9

**Install:**

```bash
pip install -e .[dev]
```

**Development Commands:**

```bash
./cicd/format.sh                 # Format code
./cicd/check-all-locally.sh      # Run all checks  
./cicd/test-all.sh               # Run tests
```

## 快速开始

```python
from memorylake import MemoryTool

tool = MemoryTool("./memory")
tool.create_file("/memories/profile.txt", "喜欢喝咖啡")
print(tool.view_path("/memories/profile.txt"))
```

## 核心方法

- `view_path(path, view_range=None)`: 查看文件或目录内容（文件带行号）。
- `create_file(path, file_text)` / `delete_path(path)`: 创建或删除记忆文件。
- `insert_line(path, line_index, insert_text)`: 在指定行插入文本。
- `replace_text(path, old_text, new_text)`: 进行唯一字符串替换。
- `rename_path(old_path, new_path)`: 移动或重命名文件/目录。
- `list_memories(path="/memories")` / `stats()`: 枚举目录或获取记忆统计。
- `execute_tool_payload(payload)`: 直接处理来自 Anthropic 工具调用的原始命令。

所有路径必须以 `/memories` 开头，否则会触发 `MemoryToolPathError`；文件系统异常会抛出 `MemoryToolOperationError`。

## 与 Anthropic SDK 协同

```python
from anthropic import Anthropic
from memorylake import MemoryTool

client = Anthropic()
tool = MemoryTool("./memory")

response = client.beta.messages.create(
    model="claude-sonnet-4-5",
    max_tokens=256,
    messages=[{"role": "user", "content": "记住我喜欢红茶"}],
    tools=[{"type": "memory_20250818", "name": "memory"}],
    betas=["context-management-2025-06-27"],
)

for block in response.content:
    if block.type == "tool_use" and block.name == "memory":
        result = tool.execute_tool_payload(block.input)
        print(result)
```

## 示例

- `example/chat.py`: 一个交互式终端聊天，使用官方 Anthropic SDK 与 `MemoryTool` 联动，输入 `/help` 可演示所有本地方法；支持 `--api-key`、`--base-url`、`--model`、`--memory-path` 参数或对应环境变量。
