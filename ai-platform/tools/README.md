# Tools

Plugin-like tool framework.

Tools are self-contained capabilities agents can invoke. Each tool
implements `BaseTool` and is registered in the central registry.

- `base.py` — Abstract BaseTool
- `registry.py` — Central tool registry
- `builtin/` — Built-in tool implementations (skeletons)
