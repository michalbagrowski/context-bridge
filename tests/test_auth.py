import json
from unittest.mock import MagicMock, patch

from context_bridge.auth import ClaudeAuth


class TestGetCookieHeader:
    def test_returns_formatted_cookie_string(self, mock_cookies):
        auth = ClaudeAuth()
        header = auth.get_cookie_header()
        assert "sessionKey=fake-session-key" in header
        assert "CF_AppSession=fake-cf-session" in header

    def test_raises_on_cookie_failure(self):
        with patch("browser_cookie3.chrome", side_effect=Exception("no chrome")):
            auth = ClaudeAuth()
            try:
                auth.get_cookie_header()
                assert False, "Should have raised"
            except RuntimeError as e:
                assert "Could not get cookies" in str(e)


class TestMakeApiRequest:
    def test_get_request_returns_json(self, mock_cookies):
        auth = ClaudeAuth()
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"key": "value"}
        with patch("curl_cffi.requests.get", return_value=mock_response):
            result = auth.get("organizations")
            assert result == {"key": "value"}

    def test_post_request_sends_payload(self, mock_cookies):
        auth = ClaudeAuth()
        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = {"uuid": "new-doc"}
        with patch("curl_cffi.requests.post", return_value=mock_response) as mock_post:
            result = auth.post("some/endpoint", {"file_name": "test.md", "content": "hello"})
            assert result == {"uuid": "new-doc"}
            call_kwargs = mock_post.call_args
            assert "hello" in call_kwargs.kwargs.get("data", "") or "hello" in str(call_kwargs)

    def test_delete_request(self, mock_cookies):
        auth = ClaudeAuth()
        mock_response = MagicMock()
        mock_response.status_code = 204
        with patch("curl_cffi.requests.delete", return_value=mock_response):
            auth.delete("some/endpoint")  # Should not raise

    def test_get_raises_on_non_200(self, mock_cookies):
        auth = ClaudeAuth()
        mock_response = MagicMock()
        mock_response.status_code = 403
        mock_response.text = "Forbidden"
        with patch("curl_cffi.requests.get", return_value=mock_response):
            try:
                auth.get("organizations")
                assert False, "Should have raised"
            except RuntimeError as e:
                assert "403" in str(e)


class TestGetOrganizationId:
    def test_returns_org_with_conversations(self, mock_cookies, mock_orgs_response, sample_conversations):
        auth = ClaudeAuth()
        mock_resp_orgs = MagicMock()
        mock_resp_orgs.status_code = 200
        mock_resp_orgs.json.return_value = mock_orgs_response

        mock_resp_convos = MagicMock()
        mock_resp_convos.status_code = 200
        mock_resp_convos.json.return_value = sample_conversations

        with patch("curl_cffi.requests.get", side_effect=[mock_resp_orgs, mock_resp_convos]):
            org_id = auth.get_organization_id()
            assert org_id == "org-uuid-123"
