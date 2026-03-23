"""Authentication and HTTP client for claude.ai API."""

import json
import time

import browser_cookie3
from curl_cffi import requests

CLAUDE_API_BASE = "https://claude.ai/api"
COOKIE_CACHE_TTL = 300  # 5 minutes


class ClaudeAuth:
    """Handles cookie-based authentication and HTTP requests to claude.ai."""

    def __init__(self):
        self._org_id = None
        self._cached_cookies = None
        self._cookie_cached_at = 0

    def get_cookie_header(self) -> str:
        """Get all Claude cookies formatted as a cookie header (cached for 5 min)."""
        now = time.time()
        if self._cached_cookies and (now - self._cookie_cached_at) < COOKIE_CACHE_TTL:
            return self._cached_cookies
        try:
            cj = browser_cookie3.chrome(domain_name='.claude.ai')
            cookies = [f"{cookie.name}={cookie.value}" for cookie in cj]
            self._cached_cookies = "; ".join(cookies)
            self._cookie_cached_at = now
            return self._cached_cookies
        except Exception as e:
            raise RuntimeError(f"Could not get cookies from Chrome: {e}")

    def _headers(self) -> dict:
        return {
            'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36',
            'Accept': 'application/json',
            'Accept-Language': 'en-US,en;q=0.5',
            'Referer': 'https://claude.ai/chats',
            'Content-Type': 'application/json',
            'Cookie': self.get_cookie_header(),
        }

    def get(self, endpoint: str) -> dict:
        """Make an authenticated GET request."""
        url = f"{CLAUDE_API_BASE}/{endpoint}"
        response = requests.get(url, headers=self._headers(), impersonate="chrome120")
        if response.status_code != 200:
            raise RuntimeError(
                f"API request failed: {response.status_code} - {response.text[:200]}"
            )
        return response.json()

    def post(self, endpoint: str, payload: dict, expected_status: int = 201) -> dict:
        """Make an authenticated POST request."""
        url = f"{CLAUDE_API_BASE}/{endpoint}"
        response = requests.post(
            url,
            headers=self._headers(),
            data=json.dumps(payload),
            impersonate="chrome120",
        )
        if response.status_code != expected_status:
            raise RuntimeError(
                f"API request failed: {response.status_code} - {response.text[:200]}"
            )
        return response.json()

    def delete(self, endpoint: str) -> None:
        """Make an authenticated DELETE request."""
        url = f"{CLAUDE_API_BASE}/{endpoint}"
        response = requests.delete(url, headers=self._headers(), impersonate="chrome120")
        if response.status_code != 204:
            raise RuntimeError(
                f"API request failed: {response.status_code} - {response.text[:200]}"
            )

    def get_organization_id(self) -> str:
        """Get the organization ID that contains conversations."""
        if self._org_id:
            return self._org_id

        orgs = self.get("organizations")
        if not orgs:
            raise RuntimeError("No organizations found")

        chat_orgs = [
            org for org in orgs
            if 'chat' in org.get('capabilities', [])
        ]
        if not chat_orgs:
            chat_orgs = orgs

        for org in chat_orgs:
            org_id = org['uuid']
            try:
                convos = self.get(f"organizations/{org_id}/chat_conversations")
                if convos:
                    self._org_id = org_id
                    return org_id
            except RuntimeError:
                continue

        self._org_id = chat_orgs[0]['uuid']
        return self._org_id
