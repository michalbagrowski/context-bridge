# tests/test_integration.py
"""End-to-end integration test with mocked HTTP."""

import json
import os
from unittest.mock import MagicMock, patch, call

import pytest


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
        from context_bridge.projects_api import ProjectsAPI
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

        # Mock the API to resolve project name
        api = ProjectsAPI()
        api._auth._org_id = "org-123"

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "proj-abc", "name": "My App", "description": ""},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            project_id = api.resolve_project_id(config.project_name)
            assert project_id == "proj-abc"

        # Verify caching works
        config.save_cached_project_id(project_id)
        assert config.cached_project_id == "proj-abc"
