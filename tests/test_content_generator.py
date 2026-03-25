# tests/test_content_generator.py
import os
import subprocess
from unittest.mock import patch, MagicMock

import pytest

from context_bridge.content_generator import ContentGenerator


@pytest.fixture
def generator(tmp_path):
    return ContentGenerator(repo_name="my-app", cwd=str(tmp_path))


class TestStatusSummary:
    def test_generates_markdown_with_recent_commits(self, generator):
        git_log = "abc1234 Add user auth\ndef5678 Fix rate limiter"
        git_branch = "feature/auth"
        git_ahead = "3"

        with patch.object(generator, '_git', side_effect=[git_branch, git_log, git_ahead]):
            result = generator.generate_status()
            assert "# CLI Status: my-app" in result
            assert "Add user auth" in result
            assert "feature/auth" in result
            assert "3 commits ahead" in result

    def test_includes_last_updated_timestamp(self, generator):
        with patch.object(generator, '_git', side_effect=["main", "abc Fix thing", "0"]):
            result = generator.generate_status()
            assert "Last updated:" in result


class TestTodoList:
    def test_formats_todo_items(self, generator):
        todos = ["Add tests for auth", "Update API docs"]
        result = generator.generate_todos(todos)
        assert "# TODOs: my-app" in result
        assert "- [ ] Add tests for auth" in result
        assert "- [ ] Update API docs" in result

    def test_handles_completed_todos(self, generator):
        todos = ["[x] Implement JWT", "Add tests"]
        result = generator.generate_todos(todos)
        assert "- [x] Implement JWT" in result
        assert "- [ ] Add tests" in result


class TestSessionLog:
    def test_generates_session_log(self, generator):
        result = generator.generate_session_log(
            done=["Implemented JWT auth", "Refactored middleware"],
            decisions=["Chose RS256 over HS256"],
            needs_work=["Integration tests missing"],
        )
        assert "# Session Log: my-app" in result
        assert "Implemented JWT auth" in result
        assert "Chose RS256 over HS256" in result
        assert "Integration tests missing" in result


class TestDocNames:
    def test_status_doc_name(self, generator):
        assert generator.status_doc_name() == "[cli] Status - my-app.md"

    def test_todos_doc_name(self, generator):
        assert generator.todos_doc_name() == "[cli] TODOs - my-app.md"

    def test_session_log_doc_name(self, generator):
        name = generator.session_log_doc_name()
        assert name.startswith("[cli] Session Log - my-app - ")
        assert name.endswith(".md")
