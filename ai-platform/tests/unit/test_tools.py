"""Tests for built-in tool implementations."""

from __future__ import annotations

import os
import tempfile

import pytest

from tools.builtin import DatabaseTool, DirectoryTool, FileTool, GitTool, ShellTool
from tools.registry import ToolRegistry


# ── Fixtures ───────────────────────────────────────────────

@pytest.fixture
def temp_workspace() -> str:
    with tempfile.TemporaryDirectory() as tmp:
        yield tmp


@pytest.fixture
def file_tool(temp_workspace: str) -> FileTool:
    return FileTool({"workspace": temp_workspace})


@pytest.fixture
def dir_tool(temp_workspace: str) -> DirectoryTool:
    return DirectoryTool({"workspace": temp_workspace})


@pytest.fixture
def db_tool(temp_workspace: str) -> DatabaseTool:
    return DatabaseTool({"workspace": temp_workspace, "db_path": os.path.join(temp_workspace, "test.db")})


# ── FileTool Tests ─────────────────────────────────────────

class TestFileTool:
    def test_name(self, file_tool: FileTool):
        assert file_tool.name == "file"

    @pytest.mark.anyio
    async def test_write_and_read(self, file_tool: FileTool, temp_workspace: str):
        path = os.path.join(temp_workspace, "hello.txt")
        result = await file_tool.execute(action="write", path=path, content="Hello, World!")
        assert result["success"] is True
        assert "Written" in result["output"]

        result = await file_tool.execute(action="read", path=path)
        assert result["success"] is True
        assert result["output"] == "Hello, World!"

    @pytest.mark.anyio
    async def test_append(self, file_tool: FileTool, temp_workspace: str):
        path = os.path.join(temp_workspace, "append.txt")
        await file_tool.execute(action="write", path=path, content="Line 1\n")
        await file_tool.execute(action="append", path=path, content="Line 2\n")
        result = await file_tool.execute(action="read", path=path)
        assert result["output"] == "Line 1\nLine 2\n"

    @pytest.mark.anyio
    async def test_delete(self, file_tool: FileTool, temp_workspace: str):
        path = os.path.join(temp_workspace, "todelete.txt")
        await file_tool.execute(action="write", path=path, content="delete me")
        result = await file_tool.execute(action="delete", path=path)
        assert result["success"] is True
        assert not os.path.isfile(path)

    @pytest.mark.anyio
    async def test_read_nonexistent(self, file_tool: FileTool, temp_workspace: str):
        path = os.path.join(temp_workspace, "nonexistent.txt")
        result = await file_tool.execute(action="read", path=path)
        assert result["success"] is False
        assert "not found" in result["error"]

    @pytest.mark.anyio
    async def test_unknown_action(self, file_tool: FileTool, temp_workspace: str):
        result = await file_tool.execute(action="invalid", path="/tmp/test.txt")
        assert result["success"] is False

    @pytest.mark.anyio
    async def test_missing_path(self, file_tool: FileTool):
        result = await file_tool.execute(action="read")
        assert result["success"] is False


# ── DirectoryTool Tests ────────────────────────────────────

class TestDirectoryTool:
    def test_name(self, dir_tool: DirectoryTool):
        assert dir_tool.name == "directory"

    @pytest.mark.anyio
    async def test_create_and_list(self, dir_tool: DirectoryTool, temp_workspace: str):
        path = os.path.join(temp_workspace, "newdir")
        result = await dir_tool.execute(action="create", path=path)
        assert result["success"] is True
        assert os.path.isdir(path)

        result = await dir_tool.execute(action="list", path=temp_workspace)
        assert result["success"] is True
        entries = result["output"]
        assert any(e["name"] == "newdir" and e["type"] == "dir" for e in entries)

    @pytest.mark.anyio
    async def test_list_nonexistent(self, dir_tool: DirectoryTool):
        result = await dir_tool.execute(action="list", path="/nonexistent/path")
        assert result["success"] is False

    @pytest.mark.anyio
    async def test_remove(self, dir_tool: DirectoryTool, temp_workspace: str):
        path = os.path.join(temp_workspace, "toremove")
        await dir_tool.execute(action="create", path=path)
        result = await dir_tool.execute(action="remove", path=path)
        assert result["success"] is True
        assert not os.path.isdir(path)


# ── DatabaseTool Tests ─────────────────────────────────────

class TestDatabaseTool:
    def test_name(self, db_tool: DatabaseTool):
        assert db_tool.name == "database"

    @pytest.mark.anyio
    async def test_create_table_and_query(self, db_tool: DatabaseTool, temp_workspace: str):
        result = await db_tool.execute(query="CREATE TABLE IF NOT EXISTS test (id INTEGER PRIMARY KEY, name TEXT)")
        assert result["success"] is True

        result = await db_tool.execute(query="INSERT INTO test (name) VALUES (?)", params=["Alice"])
        assert result["success"] is True
        assert result["output"]["affected_rows"] == 1

        result = await db_tool.execute(query="SELECT * FROM test")
        assert result["success"] is True
        assert len(result["output"]) == 1
        assert result["output"][0]["name"] == "Alice"

    @pytest.mark.anyio
    async def test_invalid_sql(self, db_tool: DatabaseTool):
        result = await db_tool.execute(query="SELECT invalid FROM nowhere")
        assert result["success"] is False
        assert "error" in result

    @pytest.mark.anyio
    async def test_missing_query(self, db_tool: DatabaseTool):
        result = await db_tool.execute()
        assert result["success"] is False


# ── ToolRegistry Tests ─────────────────────────────────────

class TestToolRegistryIntegration:
    def test_all_tools_can_be_registered(self, temp_workspace: str):
        reg = ToolRegistry()
        config = {"workspace": temp_workspace, "db_path": os.path.join(temp_workspace, "data.db")}
        reg.register(FileTool(config))
        reg.register(DirectoryTool(config))
        reg.register(GitTool(config))
        reg.register(ShellTool(config))
        reg.register(DatabaseTool(config))
        assert len(reg) == 5
        names = [t.name for t in reg]
        assert "file" in names
        assert "directory" in names
        assert "git" in names
        assert "shell" in names
        assert "database" in names
