"""
Tests for claude-memory MCP server — local storage tools only.

Claude.ai API tools (list_conversations, get_conversation, search_conversations)
are not tested here as they require a live Chrome session. get_conversation_summary
is tested with a mocked API.

Run with:
    pytest test_server.py -v
"""

import json
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch

import pytest

import server


@pytest.fixture(autouse=True)
def isolated_storage(tmp_path, monkeypatch):
    """Redirect all storage to a temporary directory for every test."""
    monkeypatch.setattr(server, "STORAGE_DIR", tmp_path)


# ── Helpers ───────────────────────────────────────────────────────────────────


def make_project(tmp_path: Path, name: str = "myproject") -> str:
    """Create a real directory and return its path string."""
    p = tmp_path / name
    p.mkdir(parents=True, exist_ok=True)
    return str(p)


def write_checkpoint(
    sessions_dir: Path,
    project_key: str,
    timestamp: str,
    summary: str,
    project_path: str = "/fake/project",
) -> None:
    """Write a raw checkpoint file with a controlled timestamp for ordering tests."""
    filename = f"{project_key}_{timestamp}_deadbe01.json"
    (sessions_dir / filename).write_text(json.dumps({
        "checkpoint_id": "deadbe01",
        "project_path": project_path,
        "saved_at": "2026-01-01T00:00:00+00:00",
        "summary": summary,
        "current_task": "",
        "key_files": [],
        "open_questions": "",
        "decisions_made": "",
    }))


def write_summary(summaries_dir: Path, conv_id: str, name: str, age_days: int) -> None:
    """Write a cached summary file with a controlled age."""
    cached_at = datetime.now(timezone.utc) - timedelta(days=age_days)
    (summaries_dir / f"{conv_id}.json").write_text(json.dumps({
        "id": conv_id,
        "name": name,
        "total_messages": 4,
        "messages": [
            {"role": "human", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"},
        ],
        "cached_at": cached_at.isoformat(),
    }))


# ── Session checkpoints ───────────────────────────────────────────────────────


class TestSaveSessionCheckpoint:
    def test_creates_file(self, tmp_path):
        result = json.loads(server.save_session_checkpoint(
            make_project(tmp_path), summary="Did some work"
        ))
        assert "checkpoint_id" in result
        assert Path(result["saved_to"]).exists()

    def test_key_files_parsed_correctly(self, tmp_path):
        server.save_session_checkpoint(
            make_project(tmp_path), summary="Work", key_files="a.py, b.py, c.py"
        )
        checkpoint = json.loads(server.get_latest_session_checkpoint(make_project(tmp_path)))
        assert checkpoint["key_files"] == ["a.py", "b.py", "c.py"]

    def test_empty_key_files(self, tmp_path):
        server.save_session_checkpoint(make_project(tmp_path), summary="Work")
        checkpoint = json.loads(server.get_latest_session_checkpoint(make_project(tmp_path)))
        assert checkpoint["key_files"] == []

    def test_all_fields_stored(self, tmp_path):
        server.save_session_checkpoint(
            make_project(tmp_path),
            summary="Summary",
            current_task="Task",
            open_questions="Q1",
            decisions_made="D1",
        )
        cp = json.loads(server.get_latest_session_checkpoint(make_project(tmp_path)))
        assert cp["summary"] == "Summary"
        assert cp["current_task"] == "Task"
        assert cp["open_questions"] == "Q1"
        assert cp["decisions_made"] == "D1"


class TestGetLatestSessionCheckpoint:
    def test_not_found(self, tmp_path):
        result = json.loads(server.get_latest_session_checkpoint(make_project(tmp_path)))
        assert result["found"] is False

    def test_returns_most_recent(self, tmp_path):
        project = make_project(tmp_path)
        pk = server._project_key(project)
        sessions_dir = server._storage("sessions")
        write_checkpoint(sessions_dir, pk, "20260310T100000Z", "First")
        write_checkpoint(sessions_dir, pk, "20260310T120000Z", "Second")
        write_checkpoint(sessions_dir, pk, "20260310T140000Z", "Third")

        result = json.loads(server.get_latest_session_checkpoint(project))
        assert result["found"] is True
        assert result["summary"] == "Third"
        assert result["total_checkpoints"] == 3

    def test_projects_isolated(self, tmp_path):
        proj_a = make_project(tmp_path, "project_a")
        proj_b = make_project(tmp_path, "project_b")
        server.save_session_checkpoint(proj_a, summary="A work")
        server.save_session_checkpoint(proj_b, summary="B work")

        assert json.loads(server.get_latest_session_checkpoint(proj_a))["summary"] == "A work"
        assert json.loads(server.get_latest_session_checkpoint(proj_b))["summary"] == "B work"


class TestListSessionCheckpoints:
    def test_returns_all(self, tmp_path):
        project = make_project(tmp_path)
        pk = server._project_key(project)
        sessions_dir = server._storage("sessions")
        for i, ts in enumerate(["20260310T100000Z", "20260310T110000Z", "20260310T120000Z"]):
            write_checkpoint(sessions_dir, pk, ts, f"Session {i}")

        result = json.loads(server.list_session_checkpoints(project))
        assert len(result) == 3

    def test_limit_respected(self, tmp_path):
        project = make_project(tmp_path)
        pk = server._project_key(project)
        sessions_dir = server._storage("sessions")
        for i in range(5):
            write_checkpoint(sessions_dir, pk, f"2026031{i}T100000Z", f"Session {i}")

        result = json.loads(server.list_session_checkpoints(project, limit=2))
        assert len(result) == 2

    def test_empty_project(self, tmp_path):
        result = json.loads(server.list_session_checkpoints(make_project(tmp_path)))
        assert result == []


class TestCleanupSessionCheckpoints:
    def _make_checkpoints(self, tmp_path, count: int) -> str:
        project = make_project(tmp_path)
        pk = server._project_key(project)
        sessions_dir = server._storage("sessions")
        for i in range(count):
            write_checkpoint(sessions_dir, pk, f"20260310T{i:02d}0000Z", f"Session {i}")
        return project

    def test_dry_run_does_not_delete(self, tmp_path):
        project = self._make_checkpoints(tmp_path, 5)
        result = json.loads(
            server.cleanup_session_checkpoints(project, keep_latest=3, dry_run=True)
        )
        assert result["dry_run"] is True
        assert result["deleted"] == 2
        # Files still exist
        assert len(list(server._storage("sessions").glob("*.json"))) == 5

    def test_deletes_oldest(self, tmp_path):
        project = self._make_checkpoints(tmp_path, 5)
        server.cleanup_session_checkpoints(project, keep_latest=3, dry_run=False)
        assert len(list(server._storage("sessions").glob("*.json"))) == 3

    def test_keep_more_than_exist(self, tmp_path):
        project = self._make_checkpoints(tmp_path, 3)
        result = json.loads(
            server.cleanup_session_checkpoints(project, keep_latest=10, dry_run=False)
        )
        assert result["deleted"] == 0
        assert len(list(server._storage("sessions").glob("*.json"))) == 3


# ── Image persistence ─────────────────────────────────────────────────────────


class TestSaveImage:
    def test_saves_description_only(self, tmp_path):
        result = json.loads(server.save_image("A screenshot of the login page"))
        assert result["has_file"] is False
        assert "image_id" in result
        meta_file = server._storage("images") / f"{result['image_id']}.json"
        assert meta_file.exists()

    def test_copies_file(self, tmp_path):
        src = tmp_path / "screenshot.png"
        src.write_bytes(b"\x89PNG\r\n\x1a\n")  # minimal PNG header

        result = json.loads(server.save_image("Login screenshot", source_path=str(src)))
        assert result["has_file"] is True
        assert Path(result["stored_path"]).exists()
        assert result["stored_path"] != str(src)  # it's a copy, not the original

    def test_missing_source_returns_error(self, tmp_path):
        result = json.loads(server.save_image("desc", source_path="/nonexistent/file.png"))
        assert "error" in result

    def test_tags_stored(self, tmp_path):
        result = json.loads(server.save_image("desc", tags="bug, login, screenshot"))
        meta = json.loads((server._storage("images") / f"{result['image_id']}.json").read_text())
        assert set(meta["tags"]) == {"bug", "login", "screenshot"}


class TestGetImage:
    def test_returns_metadata(self, tmp_path):
        saved = json.loads(server.save_image("A login form screenshot"))
        retrieved = json.loads(server.get_image(saved["image_id"]))
        assert retrieved["description"] == "A login form screenshot"
        assert retrieved["has_file"] is False

    def test_not_found(self, tmp_path):
        result = json.loads(server.get_image("nonexistent"))
        assert "error" in result

    def test_file_exists_flag(self, tmp_path):
        src = tmp_path / "img.png"
        src.write_bytes(b"PNG")
        saved = json.loads(server.save_image("desc", source_path=str(src)))
        retrieved = json.loads(server.get_image(saved["image_id"]))
        assert retrieved["file_exists"] is True


class TestListImages:
    def test_returns_all(self, tmp_path):
        server.save_image("Image 1")
        server.save_image("Image 2")
        result = json.loads(server.list_images())
        assert len(result) == 2

    def test_tag_filter(self, tmp_path):
        server.save_image("Image A", tags="bug")
        server.save_image("Image B", tags="feature")
        server.save_image("Image C", tags="bug,feature")

        bugs = json.loads(server.list_images(tags="bug"))
        assert len(bugs) == 2

    def test_limit(self, tmp_path):
        for i in range(5):
            server.save_image(f"Image {i}")
        result = json.loads(server.list_images(limit=3))
        assert len(result) == 3


class TestCleanupImages:
    def test_dry_run_preserves_files(self, tmp_path):
        server.save_image("Old image")
        result = json.loads(
            server.cleanup_images(older_than_days=0, remove_broken_refs=False, dry_run=True)
        )
        assert result["dry_run"] is True
        assert len(list(server._storage("images").glob("*.json"))) == 1

    def test_age_based_deletion(self, tmp_path):
        images_dir = server._storage("images")
        old_time = (datetime.now(timezone.utc) - timedelta(days=40)).isoformat()
        recent_time = datetime.now(timezone.utc).isoformat()

        for img_id, saved_at, label in [
            ("old000000001", old_time, "Old image"),
            ("new000000001", recent_time, "Recent image"),
        ]:
            (images_dir / f"{img_id}.json").write_text(json.dumps({
                "image_id": img_id,
                "stored_path": None,
                "original_path": None,
                "description": label,
                "tags": [],
                "saved_at": saved_at,
                "has_file": False,
            }))

        server.cleanup_images(older_than_days=30, remove_broken_refs=False, dry_run=False)
        remaining = [f.stem for f in images_dir.glob("*.json")]
        assert "new000000001" in remaining
        assert "old000000001" not in remaining

    def test_broken_ref_removal(self, tmp_path):
        images_dir = server._storage("images")
        (images_dir / "ghost000001.json").write_text(json.dumps({
            "image_id": "ghost000001",
            "stored_path": "/nonexistent/image.png",
            "original_path": None,
            "description": "Ghost image",
            "tags": [],
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "has_file": True,
        }))

        result = json.loads(
            server.cleanup_images(older_than_days=0, remove_broken_refs=True, dry_run=False)
        )
        assert result["broken_refs"]["count"] == 1
        assert not (images_dir / "ghost000001.json").exists()


# ── Project conversation registry ─────────────────────────────────────────────


class TestLinkConversation:
    def test_links_with_explicit_note(self, tmp_path):
        project = make_project(tmp_path)
        result = json.loads(
            server.link_conversation(project, "conv-abc", note="Planning session for auth")
        )
        assert result["status"] == "linked"
        assert result["note"] == "Planning session for auth"

    def test_updates_existing_link(self, tmp_path):
        project = make_project(tmp_path)
        server.link_conversation(project, "conv-abc", note="Old note")
        result = json.loads(
            server.link_conversation(project, "conv-abc", note="Better note")
        )
        assert result["status"] == "updated"
        assert result["note"] == "Better note"
        # Only one entry
        convs = json.loads(server.get_project_conversations(project))
        assert len(convs) == 1

    def test_auto_note_from_cached_summary(self, tmp_path):
        project = make_project(tmp_path)
        write_summary(server._storage("summaries"), "conv-xyz", "Auth Design", age_days=1)

        result = json.loads(server.link_conversation(project, "conv-xyz"))
        assert "Auth Design" in result["note"]

    def test_auto_note_graceful_when_api_fails(self, tmp_path):
        project = make_project(tmp_path)
        with patch.object(server, "_fetch_and_cache_summary", side_effect=RuntimeError("No Chrome")):
            result = json.loads(server.link_conversation(project, "conv-xyz"))
        assert result["status"] == "linked"
        assert result["note"] == ""

    def test_stores_project_path_in_registry(self, tmp_path):
        project = make_project(tmp_path)
        server.link_conversation(project, "conv-abc", note="Note")
        pk = server._project_key(project)
        registry = server._load_registry(pk)
        assert registry["project_path"] == str(Path(project).resolve())


class TestUnlinkConversation:
    def test_removes_entry(self, tmp_path):
        project = make_project(tmp_path)
        server.link_conversation(project, "conv-1", note="Note 1")
        server.link_conversation(project, "conv-2", note="Note 2")
        server.unlink_conversation(project, "conv-1")
        convs = json.loads(server.get_project_conversations(project))
        assert len(convs) == 1
        assert convs[0]["conversation_id"] == "conv-2"

    def test_error_if_not_linked(self, tmp_path):
        project = make_project(tmp_path)
        result = json.loads(server.unlink_conversation(project, "nonexistent"))
        assert "error" in result


class TestGetProjectConversations:
    def test_empty(self, tmp_path):
        result = json.loads(server.get_project_conversations(make_project(tmp_path)))
        assert result == []

    def test_returns_linked(self, tmp_path):
        project = make_project(tmp_path)
        server.link_conversation(project, "conv-1", note="First")
        server.link_conversation(project, "conv-2", note="Second")
        result = json.loads(server.get_project_conversations(project))
        assert len(result) == 2
        ids = {c["conversation_id"] for c in result}
        assert ids == {"conv-1", "conv-2"}


# ── resume_session ────────────────────────────────────────────────────────────


class TestResumeSession:
    def test_returns_checkpoint_and_conversations(self, tmp_path):
        project = make_project(tmp_path)
        server.save_session_checkpoint(project, summary="Did auth work")
        server.link_conversation(project, "conv-1", note="Auth design")

        result = json.loads(server.resume_session(project))
        assert result["checkpoint"]["found"] is True
        assert result["checkpoint"]["summary"] == "Did auth work"
        assert len(result["linked_conversations"]) == 1
        assert result["linked_conversations"][0]["note"] == "Auth design"

    def test_no_checkpoint(self, tmp_path):
        project = make_project(tmp_path)
        result = json.loads(server.resume_session(project))
        assert result["checkpoint"]["found"] is False
        assert result["linked_conversations"] == []

    def test_projects_isolated(self, tmp_path):
        proj_a = make_project(tmp_path, "alpha")
        proj_b = make_project(tmp_path, "beta")
        server.save_session_checkpoint(proj_a, summary="Alpha work")
        server.link_conversation(proj_b, "conv-b", note="Beta convo")

        res_a = json.loads(server.resume_session(proj_a))
        res_b = json.loads(server.resume_session(proj_b))

        assert res_a["checkpoint"]["summary"] == "Alpha work"
        assert res_a["linked_conversations"] == []
        assert res_b["checkpoint"]["found"] is False
        assert len(res_b["linked_conversations"]) == 1


# ── list_all_projects ─────────────────────────────────────────────────────────


class TestListAllProjects:
    def test_empty(self, tmp_path):
        result = json.loads(server.list_all_projects())
        assert result == []

    def test_from_checkpoints(self, tmp_path):
        project = make_project(tmp_path)
        server.save_session_checkpoint(project, summary="Work")
        result = json.loads(server.list_all_projects())
        assert len(result) == 1
        assert result[0]["checkpoint_count"] == 1

    def test_from_registry_only(self, tmp_path):
        project = make_project(tmp_path)
        server.link_conversation(project, "conv-1", note="Note")
        result = json.loads(server.list_all_projects())
        assert len(result) == 1
        assert result[0]["linked_conversations"] == 1
        assert result[0]["checkpoint_count"] == 0

    def test_combined(self, tmp_path):
        project = make_project(tmp_path)
        server.save_session_checkpoint(project, summary="Work")
        server.save_session_checkpoint(project, summary="More work")
        server.link_conversation(project, "conv-1", note="Note")
        server.link_conversation(project, "conv-2", note="Note 2")

        result = json.loads(server.list_all_projects())
        assert len(result) == 1
        assert result[0]["checkpoint_count"] == 2
        assert result[0]["linked_conversations"] == 2

    def test_multiple_projects(self, tmp_path):
        for name in ("alpha", "beta", "gamma"):
            server.save_session_checkpoint(make_project(tmp_path, name), summary=f"{name} work")
        result = json.loads(server.list_all_projects())
        assert len(result) == 3


# ── cleanup_summaries ─────────────────────────────────────────────────────────


class TestCleanupSummaries:
    def test_dry_run_preserves_files(self, tmp_path):
        summaries_dir = server._storage("summaries")
        write_summary(summaries_dir, "old-conv", "Old Convo", age_days=100)
        result = json.loads(server.cleanup_summaries(older_than_days=90, dry_run=True))
        assert result["dry_run"] is True
        assert result["count"] == 1
        assert (summaries_dir / "old-conv.json").exists()

    def test_deletes_old(self, tmp_path):
        summaries_dir = server._storage("summaries")
        write_summary(summaries_dir, "old-conv", "Old Convo", age_days=100)
        write_summary(summaries_dir, "new-conv", "New Convo", age_days=10)
        server.cleanup_summaries(older_than_days=90, dry_run=False)
        assert not (summaries_dir / "old-conv.json").exists()
        assert (summaries_dir / "new-conv.json").exists()

    def test_nothing_to_delete(self, tmp_path):
        summaries_dir = server._storage("summaries")
        write_summary(summaries_dir, "fresh-conv", "Fresh", age_days=5)
        result = json.loads(server.cleanup_summaries(older_than_days=90, dry_run=False))
        assert result["count"] == 0


# ── get_conversation_summary (caching) ───────────────────────────────────────


class TestGetConversationSummaryCache:
    MOCK_CONV = {
        "uuid": "test-conv-id",
        "name": "Test Conversation",
        "chat_messages": [
            {"sender": "human", "text": "Hello"},
            {"sender": "assistant", "text": "Hi there"},
        ],
    }

    def test_fetches_and_caches(self, tmp_path):
        with (
            patch.object(server, "get_organization_id", return_value="org-1"),
            patch.object(server, "make_api_request", return_value=self.MOCK_CONV),
        ):
            result = json.loads(server.get_conversation_summary("test-conv-id"))

        assert result["name"] == "Test Conversation"
        assert "cached_at" in result
        assert (server._storage("summaries") / "test-conv-id.json").exists()

    def test_serves_from_cache_without_api(self, tmp_path):
        write_summary(server._storage("summaries"), "cached-conv", "Cached Convo", age_days=1)

        with patch.object(server, "make_api_request", side_effect=RuntimeError("Should not call")):
            result = json.loads(server.get_conversation_summary("cached-conv"))

        assert result["name"] == "Cached Convo"

    def test_refresh_bypasses_cache(self, tmp_path):
        write_summary(server._storage("summaries"), "test-conv-id", "Old Name", age_days=5)

        with (
            patch.object(server, "get_organization_id", return_value="org-1"),
            patch.object(server, "make_api_request", return_value=self.MOCK_CONV),
        ):
            result = json.loads(server.get_conversation_summary("test-conv-id", refresh=True))

        assert result["name"] == "Test Conversation"
