import json
from unittest.mock import MagicMock, patch

from context_bridge.conversations_api import (
    list_conversations,
    get_conversation,
    search_conversations,
    get_conversation_summary,
)


class TestListConversations:
    def test_returns_limited_conversations(self, mock_cookies, mock_orgs_response, sample_conversations):
        mock_resp_orgs = MagicMock()
        mock_resp_orgs.status_code = 200
        mock_resp_orgs.json.return_value = mock_orgs_response

        mock_resp_convos = MagicMock()
        mock_resp_convos.status_code = 200
        mock_resp_convos.json.return_value = sample_conversations

        with patch("curl_cffi.requests.get", side_effect=[mock_resp_orgs, mock_resp_convos, mock_resp_convos]):
            result = json.loads(list_conversations(limit=1))
            assert len(result) == 1
            assert result[0]["id"] == "conv-1"
            assert result[0]["name"] == "Test Conversation"


class TestSearchConversations:
    def test_finds_matching_conversation(self, mock_cookies, mock_orgs_response, sample_conversations):
        mock_resp_orgs = MagicMock()
        mock_resp_orgs.status_code = 200
        mock_resp_orgs.json.return_value = mock_orgs_response

        mock_resp_convos = MagicMock()
        mock_resp_convos.status_code = 200
        mock_resp_convos.json.return_value = sample_conversations

        with patch("curl_cffi.requests.get", side_effect=[mock_resp_orgs, mock_resp_convos, mock_resp_convos]):
            result = json.loads(search_conversations("Another"))
            assert len(result) == 1
            assert result[0]["name"] == "Another Chat"
