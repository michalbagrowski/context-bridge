# tests/test_projects_api.py
import json
from unittest.mock import MagicMock, patch, call

import pytest

from context_bridge.projects_api import ProjectsAPI


@pytest.fixture
def projects_api(mock_cookies):
    """ProjectsAPI with org ID resolution mocked out."""
    api = ProjectsAPI()
    return api


@pytest.fixture
def mock_org(projects_api):
    """Patch get_organization_id to always return org-uuid-123."""
    with patch.object(projects_api._auth, "get_organization_id", return_value="org-uuid-123"):
        yield projects_api


class TestListProjects:
    def test_returns_project_list(self, mock_org):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "proj-1", "name": "My Project", "description": "desc"},
            {"uuid": "proj-2", "name": "Other", "description": ""},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            result = json.loads(mock_org.list_projects())
            assert len(result) == 2
            assert result[0]["name"] == "My Project"


class TestListProjectDocs:
    def test_returns_docs(self, mock_org):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "doc-1", "file_name": "notes.md", "created_at": "2026-03-20"},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            result = json.loads(mock_org.list_project_docs("proj-1"))
            assert len(result) == 1
            assert result[0]["file_name"] == "notes.md"


class TestCreateDoc:
    def test_creates_and_returns_doc(self, mock_org):
        mock_resp = MagicMock()
        mock_resp.status_code = 201
        mock_resp.json.return_value = {"uuid": "new-doc", "file_name": "test.md"}
        with patch("curl_cffi.requests.post", return_value=mock_resp):
            result = mock_org.create_doc("proj-1", "test.md", "# Hello")
            assert result["uuid"] == "new-doc"


class TestUpsertDoc:
    def test_deletes_existing_then_creates(self, mock_org):
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
            result = mock_org.upsert_doc("proj-1", "[cli] Status - myapp.md", "new content")
            assert result["uuid"] == "new-doc"
            del_mock.assert_called_once()


class TestResolveProjectId:
    def test_resolves_name_to_uuid(self, mock_org):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "proj-1", "name": "My App", "description": ""},
            {"uuid": "proj-2", "name": "Other App", "description": ""},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            uuid = mock_org.resolve_project_id(project_name="My App")
            assert uuid == "proj-1"

    def test_returns_none_for_no_match(self, mock_org):
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            {"uuid": "proj-1", "name": "Something Else", "description": ""},
        ]
        with patch("curl_cffi.requests.get", return_value=mock_resp):
            uuid = mock_org.resolve_project_id(project_name="My App")
            assert uuid is None
