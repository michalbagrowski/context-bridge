# tests/test_integration.py
"""End-to-end integration test with mocked HTTP."""

import json
import os
from unittest.mock import MagicMock, patch

import pytest

import context_bridge.config as config_module


@pytest.fixture(autouse=True)
def isolated_cache(tmp_path, monkeypatch):
    """Redirect project cache to tmp_path."""
    cache_dir = tmp_path / "project-cache"
    cache_dir.mkdir()
    monkeypatch.setattr(config_module, "STORAGE_DIR", cache_dir)


class TestFullPushFlow:
    def test_push_status_from_configured_repo(self, tmp_path, mock_cookies):
        # Set up CLAUDE.md with project tag
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("# My App\n\n<!-- claude-project: My Test App -->\n")

        # Initialize a git repo for content generator
        import subprocess
        subprocess.run(["git", "init"], cwd=str(tmp_path), capture_output=True)
        subprocess.run(["git", "commit", "--allow-empty", "-m", "init"], cwd=str(tmp_path), capture_output=True)

        from context_bridge.config import ProjectConfig
        from context_bridge.content_generator import ContentGenerator

        config = ProjectConfig(cwd=str(tmp_path))
        assert config.project_name == "My Test App"

        gen = ContentGenerator(repo_name=config.repo_name, cwd=str(tmp_path))
        status = gen.generate_status()
        assert f"# CLI Status: {tmp_path.name}" in status

        doc_name = gen.status_doc_name()
        assert doc_name == f"[cli] Status - {tmp_path.name}.md"

    def test_config_to_project_resolution(self, tmp_path, mock_cookies):
        claude_md = tmp_path / "CLAUDE.md"
        claude_md.write_text("<!-- claude-project: My App -->\n")

        from context_bridge.config import ProjectConfig
        from context_bridge.projects_api import ProjectsAPI

        config = ProjectConfig(cwd=str(tmp_path))

        # Mock the API to resolve project name — need org + project list responses
        api = ProjectsAPI()

        mock_resp_orgs = MagicMock()
        mock_resp_orgs.status_code = 200
        mock_resp_orgs.json.return_value = [{"uuid": "org-123", "capabilities": ["chat"]}]

        mock_resp_convos = MagicMock()
        mock_resp_convos.status_code = 200
        mock_resp_convos.json.return_value = [{"uuid": "c1"}]

        mock_resp_projects = MagicMock()
        mock_resp_projects.status_code = 200
        mock_resp_projects.json.return_value = [
            {"uuid": "proj-abc", "name": "My App", "description": ""},
        ]

        with patch("curl_cffi.requests.get", side_effect=[mock_resp_orgs, mock_resp_convos, mock_resp_projects]):
            project_id = api.resolve_project_id(config.project_name)
            assert project_id == "proj-abc"

        # Verify caching works
        config.save_cached_project_id(project_id)
        assert config.cached_project_id == "proj-abc"
