import json
import os
import tempfile

from context_bridge.config import ProjectConfig


class TestParseClaudeMd:
    def test_extracts_project_name(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# My Project\n\n<!-- claude-project: My App Name -->\n\nSome docs.")
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.project_name == "My App Name"
        assert config.project_id is None

    def test_extracts_project_id(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("<!-- claude-project-id: abc-123-def -->\n")
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.project_id == "abc-123-def"
        assert config.project_name is None

    def test_prefers_id_over_name(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("<!-- claude-project: Name -->\n<!-- claude-project-id: uuid-here -->\n")
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.project_id == "uuid-here"

    def test_returns_none_when_no_claude_md(self, tmp_path):
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.project_name is None
        assert config.project_id is None

    def test_returns_none_when_no_tag(self, tmp_path):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# Project\n\nJust regular docs.\n")
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.project_name is None


class TestRepoName:
    def test_derives_from_directory_name(self, tmp_path):
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.repo_name == tmp_path.name


class TestProjectCache:
    def test_caches_resolved_uuid(self, tmp_path):
        config = ProjectConfig(cwd=str(tmp_path))
        config.save_cached_project_id("resolved-uuid-456")
        cache_file = tmp_path / ".claude-project-cache"
        assert cache_file.exists()
        data = json.loads(cache_file.read_text())
        assert data["project_id"] == "resolved-uuid-456"

    def test_reads_cached_uuid(self, tmp_path):
        cache_file = tmp_path / ".claude-project-cache"
        cache_file.write_text(json.dumps({"project_id": "cached-uuid"}))
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.cached_project_id == "cached-uuid"

    def test_returns_none_when_no_cache(self, tmp_path):
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.cached_project_id is None


class TestCooldown:
    def test_no_cooldown_on_first_push(self, tmp_path):
        config = ProjectConfig(cwd=str(tmp_path))
        assert config.is_push_allowed() is True

    def test_cooldown_blocks_rapid_pushes(self, tmp_path):
        config = ProjectConfig(cwd=str(tmp_path))
        config.record_push()
        assert config.is_push_allowed() is False

    def test_cooldown_expires(self, tmp_path):
        import time
        config = ProjectConfig(cwd=str(tmp_path), cooldown_seconds=0)
        config.record_push()
        assert config.is_push_allowed() is True
