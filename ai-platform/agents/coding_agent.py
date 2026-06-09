from __future__ import annotations

import json
import logging
import re
from typing import Any

from providers.base import BaseProvider
from tools.registry import ToolRegistry

from .base import BaseAgent

logger = logging.getLogger("ai-platform.agent.coding")

SYSTEM_PROMPT = """You are a coding agent that generates source code based on natural-language tasks.

You MUST respond with a JSON object containing the files you create or modify.
Use this exact format:

```json
{
  "plan": "Brief explanation of your approach.",
  "files": [
    {
      "path": "relative/path/to/file.py",
      "content": "Complete file content here"
    }
  ],
  "commands": [
    "optional shell command to run after creating files"
  ]
}
```

Guidelines:
- Write complete, working code with no placeholder comments.
- Use appropriate file extensions (.py, .js, .tsx, .json, .md, etc.).
- For Python files, include a `from __future__ import annotations` import.
- Create all necessary files for the task.
- Keep commands minimal and safe (no destructive operations).
- If no shell commands are needed, omit the "commands" field.
- Respond ONLY with the JSON block. No additional text."""


class CodingAgent(BaseAgent):
    def __init__(
        self,
        name: str,
        provider: BaseProvider | None = None,
        tools: ToolRegistry | None = None,
        config: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(name, provider, tools, config)
        self._results: dict[str, Any] = {}

    @property
    def agent_type(self) -> str:
        return "coding"

    @property
    def description(self) -> str:
        return "Generates and modifies source code based on natural-language tasks."

    async def initialize(self) -> None:
        if not self.provider:
            raise RuntimeError("CodingAgent requires a provider to be set")

    async def run(self, task: str, **kwargs: Any) -> dict:
        if not self.provider:
            return {"status": "error", "output": "No provider configured", "metadata": {}}

        provider_name = kwargs.get("provider_name")
        model = kwargs.get("model")

        gen_kwargs: dict[str, Any] = {}
        if model:
            gen_kwargs["model"] = model
        if provider_name and hasattr(self.provider, "name") and self.provider.name != provider_name:
            return {"status": "error", "output": f"Provider '{provider_name}' not available", "metadata": {}}

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": task},
        ]

        try:
            result = await self.provider.generate(messages, **gen_kwargs)
            content = result.get("content", "")

            plan, files, commands = self._parse_response(content)

            created_files = []
            for file_spec in files:
                path = file_spec.get("path", "")
                file_content = file_spec.get("content", "")
                if path and file_content is not None:
                    file_tool = self.tools.get("file")
                    if file_tool:
                        await file_tool.execute(action="write", path=path, content=file_content)
                        created_files.append(path)

            command_results = []
            for cmd in commands:
                shell_tool = self.tools.get("shell")
                if shell_tool:
                    cmd_result = await shell_tool.execute(command=cmd)
                    command_results.append({"command": cmd, "result": cmd_result})

            output = {
                "plan": plan,
                "files_created": created_files,
                "command_results": command_results,
            }

            self._results = {
                "task": task,
                "provider": self.provider.name,
                "model": result.get("model", ""),
                "usage": result.get("usage", {}),
            }

            return {"status": "success", "output": json.dumps(output, indent=2), "metadata": self._results}

        except Exception as e:
            logger.exception("CodingAgent.run failed")
            return {"status": "error", "output": str(e), "metadata": self._results}

    async def complete(self) -> dict:
        return {"status": "success", "output": json.dumps(self._results, indent=2), "metadata": self._results}

    async def cleanup(self) -> None:
        self._results = {}

    def _parse_response(self, content: str) -> tuple[str, list[dict], list[str]]:
        plan = ""
        files = []
        commands = []

        json_match = re.search(r"```(?:json)?\s*\n(.*?)\n```", content, re.DOTALL)
        if json_match:
            raw = json_match.group(1)
        else:
            brace_start = content.find("{")
            brace_end = content.rfind("}")
            if brace_start != -1 and brace_end != -1:
                raw = content[brace_start : brace_end + 1]
            else:
                return plan, files, commands

        try:
            data = json.loads(raw)
            plan = data.get("plan", "")
            files = data.get("files", [])
            commands = data.get("commands", [])
        except json.JSONDecodeError:
            pass

        return plan, files, commands
