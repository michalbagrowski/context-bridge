# tests/test_projects_api.py
import json
from unittest.mock import MagicMock, patch, call

import pytest

from context_bridge.projects_api import ProjectsAPI


@pytest.fixture
def projects_api(mock_cookies):
    """ProjectsAPI with pre-cached org ID to avoid HTTP calls on init."""
    api = ProjectsAPI()
    api._auth._org_id = "org-uuid-123"
    return api


class TestListProjects:
    def test_returns_project_list(self, projects_api):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "proj-1", "name": "My Project", "description": "desc"},
            {"uuid": "proj-2", "name": "Other", "description": ""},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            result = json.loads(projects_api.list_projects())
            assert len(result) == 2
            assert result[0]["name"] == "My Project"


class TestListProjectDocs:
    def test_returns_docs(self, projects_api):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "doc-1", "file_name": "notes.md", "created_at": "2026-03-20"},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            result = json.loads(projects_api.list_project_docs("proj-1"))
            assert len(result) == 1
            assert result[0]["file_name"] == "notes.md"


class TestCreateDoc:
    def test_creates_and_returns_doc(self, projects_api):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"uuid": "new-doc", "file_name": "test.md"}
        with patch("curl_cffi.requests.post", return_value=mock_resp):
            result = projects_api.create_doc("proj-1", "test.md", "# Hello")
            assert result["uuid"] == "new-doc"


class TestUpsertDoc:
    def test_deletes_existing_then_creates(self, projects_api):
        mock_list = MagicMock()
        mock_list.status_code = 200
        mock_list.json.return_value = [
            {"uuid": "old-doc", "file_name": "[cli] Status - myapp.md"},
        ]
        mock_delete = MagicMock()
        mock_delete.status_code = 204
        mock_create = MagicMock()
        mock_create.status_code = 201
        mock_create.json.return_value = {"uuid": "new-doc", "file_name": "[cli] Status - myapp.md"}

        with patch("curl_cffi.requests.get", return_value=mock_list), \
             patch("curl_cffi.requests.delete", return_value=mock_delete) as del_mock, \
             patch("curl_cffi.requests.post", return_value=mock_create):
            result = projects_api.upsert_doc("proj-1", "[cli] Status - myapp.md", "new content")
            assert result["uuid"] == "new-doc"
            del_mock.assert_called_once()


class TestResolveProjectId:
    def test_resolves_name_to_uuid(self, projects_api):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "proj-1", "name": "My App", "description": ""},
            {"uuid": "proj-2", "name": "Other App", "description": ""},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            uuid = projects_api.resolve_project_id(project_name="My App")
            assert uuid == "proj-1"

    def test_returns_none_for_no_match(self, projects_api):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "proj-1", "name": "Something Else", "description": ""},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            uuid = projects_api.resolve_project_id(project_name="My App")
            assert uuid is None
