# encoding:utf-8
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

from agent.prompt.workspace import ensure_user_context_files, load_context_files
from agent.tools.memory.memory_get import MemoryGetTool
from agent.tools.memory.memory_search import MemorySearchTool
from common.runtime_identity import RuntimeIdentity, use_identity


class _MemoryManager:
    def __init__(self, workspace: Path):
        self.config = SimpleNamespace(get_workspace=lambda: workspace)


def test_private_context_templates_are_created_without_copying_shared_data(tmp_path):
    (tmp_path / "USER.md").write_text("operator secret", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("legacy secret", encoding="utf-8")

    ensure_user_context_files(str(tmp_path), "user-a")

    private_user = tmp_path / "users" / "user-a" / "USER.md"
    private_memory = tmp_path / "memory" / "users" / "user-a" / "MEMORY.md"
    assert private_user.exists()
    assert private_memory.exists()
    assert "operator secret" not in private_user.read_text(encoding="utf-8")
    assert "legacy secret" not in private_memory.read_text(encoding="utf-8")


def test_context_prompt_loads_only_current_users_profile_and_memory(tmp_path):
    (tmp_path / "AGENT.md").write_text("shared persona", encoding="utf-8")
    (tmp_path / "RULE.md").write_text("shared rules", encoding="utf-8")
    (tmp_path / "USER.md").write_text("operator private", encoding="utf-8")
    (tmp_path / "MEMORY.md").write_text("legacy private", encoding="utf-8")
    (tmp_path / "users" / "user-a").mkdir(parents=True)
    (tmp_path / "users" / "user-a" / "USER.md").write_text(
        "profile a", encoding="utf-8"
    )
    (tmp_path / "memory" / "users" / "user-a").mkdir(parents=True)
    (tmp_path / "memory" / "users" / "user-a" / "MEMORY.md").write_text(
        "memory a", encoding="utf-8"
    )

    with use_identity(RuntimeIdentity(user_id="user-a")):
        files = load_context_files(str(tmp_path))

    combined = "\n".join(item.content for item in files)
    assert "shared persona" in combined
    assert "shared rules" in combined
    assert "profile a" in combined
    assert "memory a" in combined
    assert "operator private" not in combined
    assert "legacy private" not in combined


def test_memory_get_maps_memory_md_to_owner_and_rejects_other_user(tmp_path):
    own = tmp_path / "memory" / "users" / "user-a"
    other = tmp_path / "memory" / "users" / "user-b"
    own.mkdir(parents=True)
    other.mkdir(parents=True)
    (own / "MEMORY.md").write_text("only a", encoding="utf-8")
    (other / "MEMORY.md").write_text("only b", encoding="utf-8")
    tool = MemoryGetTool(_MemoryManager(tmp_path), user_id="user-a")

    own_result = tool.execute({"path": "MEMORY.md"})
    denied = tool.execute({"path": "memory/users/user-b/MEMORY.md"})
    traversal = tool.execute({
        "path": "memory/users/user-a/../../../MEMORY.md"
    })

    assert "only a" in own_result.result
    assert "Access denied" in denied.result
    assert "Access denied" in traversal.result


def test_memory_search_keeps_owned_memory_and_public_knowledge_only(tmp_path):
    manager = _MemoryManager(tmp_path)
    manager.search = AsyncMock(return_value=[
        SimpleNamespace(user_id=None, source="memory", path="MEMORY.md", start_line=1, end_line=1, score=1.0, snippet="legacy"),
        SimpleNamespace(user_id="user-b", source="memory", path="memory/users/user-b/x.md", start_line=1, end_line=1, score=.9, snippet="other"),
        SimpleNamespace(user_id="user-a", source="memory", path="memory/users/user-a/x.md", start_line=1, end_line=1, score=.8, snippet="own"),
        SimpleNamespace(user_id=None, source="knowledge", path="knowledge/public.md", start_line=1, end_line=1, score=.7, snippet="public"),
    ])
    tool = MemorySearchTool(manager, user_id="user-a")

    result = tool.execute({"query": "x", "max_results": 10})
    output = result.result

    assert "own" in output
    assert "public" in output
    assert "legacy" not in output
    assert "other" not in output
