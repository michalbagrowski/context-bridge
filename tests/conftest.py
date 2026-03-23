import json
from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def mock_cookies():
    """Mock browser_cookie3 to return fake cookies."""
    mock_cj = []
    cookie1 = MagicMock()
    cookie1.name = "sessionKey"
    cookie1.value = "fake-session-key"
    mock_cj.append(cookie1)
    cookie2 = MagicMock()
    cookie2.name = "CF_AppSession"
    cookie2.value = "fake-cf-session"
    mock_cj.append(cookie2)
    with patch("browser_cookie3.chrome", return_value=mock_cj):
        yield mock_cj


@pytest.fixture
def mock_orgs_response():
    """Standard org response with chat capability."""
    return [
        {
            "uuid": "org-uuid-123",
            "name": "My Org",
            "capabilities": ["chat"],
        }
    ]


@pytest.fixture
def sample_conversations():
    """Sample conversation list response."""
    return [
        {
            "uuid": "conv-1",
            "name": "Test Conversation",
            "created_at": "2026-03-20T10:00:00Z",
            "updated_at": "2026-03-20T12:00:00Z",
        },
        {
            "uuid": "conv-2",
            "name": "Another Chat",
            "created_at": "2026-03-19T10:00:00Z",
            "updated_at": "2026-03-19T12:00:00Z",
        },
    ]
