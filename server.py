#!/usr/bin/env python3
"""
MCP Server for reading Claude Desktop/Web conversations.
Allows Claude Code to reference chats from Claude.ai.

Uses Chrome browser cookies to authenticate with Claude.ai API.
Requires being logged into claude.ai in Chrome.
"""

import json
import os
from typing import Any

import browser_cookie3
from curl_cffi import requests
from mcp.server.fastmcp import FastMCP

# Initialize FastMCP server
mcp = FastMCP("claude-desktop-reader")

CLAUDE_API_BASE = "https://claude.ai/api"


def get_session_cookie() -> str:
      """Get the sessionKey cookie from Chrome browser."""
      try:
                cj = browser_cookie3.chrome(domain_name='.claude.ai')
                for cookie in cj:
                              if cookie.name == 'sessionKey':
                                                return cookie.value
                                        raise RuntimeError("sessionKey cookie not found in Chrome")
      except Exception as e:
                raise RuntimeError(f"Could not get session cookie from Chrome: {e}")


def get_all_cookies() -> str:
      """Get all Claude cookies formatted as a cookie header."""
      try:
                cj = browser_cookie3.chrome(domain_name='.claude.ai')
                cookies = []
                for cookie in cj:
                              cookies.append(f"{cookie.name}={cookie.value}")
                          return "; ".join(cookies)
except Exception as e:
        raise RuntimeError(f"Could not get cookies from Chrome: {e}")


def make_api_request(endpoint: str) -> dict:
      """Make an authenticated request to Claude API."""
      cookie_header = get_all_cookies()

    url = f"{CLAUDE_API_BASE}/{endpoint}"
    headers = {
              'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
              'Accept': 'application/json',
              'Accept-Language': 'en-US,en;q=0.5',
              'Referer': 'https://claude.ai/chats',
              'Content-Type': 'application/json',
              'Cookie': cookie_header
    }

    response = requests.get(url, headers=headers, impersonate="chrome120")

    if response.status_code != 200:
              raise RuntimeError(f"API request failed: {response.status_code} - {response.text[:200]}")

    return response.json()


def get_organization_id() -> str:
      """Get the user's personal organization ID."""
      orgs = make_api_request("organizations")
      if not orgs:
                raise RuntimeError("No organizations found")

      # Try to find personal org (contains user's email or "Organization" suffix)
      for org in orgs:
                name = org.get('name', '')
                # Personal orgs typically have format "email's Organization"
                if "'s Organization" in name or "@" in name:
                              return org['uuid']

            # Fallback: try each org and return first one that works
            cookie_header = get_all_cookies()
    for org in orgs:
              org_id = org['uuid']
              try:
                            url = f"{CLAUDE_API_BASE}/organizations/{org_id}/chat_conversations"
                            headers = {
                                'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
                                'Accept': 'application/json',
                                'Referer': 'https://claude.ai/chats',
                                'Cookie': cookie_header
                            }
                            response = requests.get(url, headers=headers, impersonate="chrome120")
                            if response.status_code == 200:
                                              return org_id
                                      except:
                            continue

    # Last resort: return first org
    return orgs[0]['uuid']


@mcp.tool()
def list_conversations(limit: int = 20) -> str:
      """
          List recent conversations from Claude.ai.

              Retrieves conversations you've had in Claude Desktop or claude.ai web.
                  Requires being logged into claude.ai in Chrome browser.

                      Args:
                              limit: Maximum number of conversations to return (default 20)

                                  Returns:
                                          JSON list of conversations with id, name, and timestamps
                                              """
    try:
              org_id = get_organization_id()
        conversations = make_api_request(f"organizations/{org_id}/chat_conversations")

        result = []
        for conv in conversations[:limit]:
                      result.append({
                                        "id": conv.get("uuid"),
                                        "name": conv.get("name") or "Untitled",
                                        "created_at": conv.get("created_at"),
                                        "updated_at": conv.get("updated_at")
                      })

        return json.dumps(result, indent=2)

except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_conversation(conversation_id: str) -> str:
      """
          Get the full content of a specific conversation from Claude.ai.

              Use list_conversations first to find the conversation ID.

                  Args:
                          conversation_id: The UUID of the conversation to retrieve

                              Returns:
                                      JSON with conversation details and all messages
                                          """
    try:
              org_id = get_organization_id()
        conversation = make_api_request(
                      f"organizations/{org_id}/chat_conversations/{conversation_id}"
        )

        messages = []
        for msg in conversation.get("chat_messages", []):
                      messages.append({
                                        "role": msg.get("sender"),
                                        "content": msg.get("text", ""),
                                        "created_at": msg.get("created_at")
                      })

        result = {
                      "id": conversation.get("uuid"),
                      "name": conversation.get("name") or "Untitled",
                      "created_at": conversation.get("created_at"),
                      "messages": messages
        }

        return json.dumps(result, indent=2)

except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_conversations(query: str, limit: int = 10) -> str:
      """
          Search conversations by name/title from Claude.ai.

              Args:
                      query: Search term to match against conversation names
                              limit: Maximum number of results to return

                                  Returns:
                                          JSON list of matching conversations
                                              """
    try:
              org_id = get_organization_id()
        conversations = make_api_request(f"organizations/{org_id}/chat_conversations")

        query_lower = query.lower()
        matches = []

        for conv in conversations:
                      name = conv.get("name") or ""
                      if query_lower in name.lower():
                                        matches.append({
                                                              "id": conv.get("uuid"),
                                                              "name": name or "Untitled",
                                                              "created_at": conv.get("created_at")
                                        })

                          if len(matches) >= limit:
                                                break

        return json.dumps(matches, indent=2)

except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_conversation_summary(conversation_id: str) -> str:
      """
          Get a condensed summary of a conversation (first and last few messages).

              Useful for getting context without loading the entire conversation.

                  Args:
                          conversation_id: The UUID of the conversation

                              Returns:
                                      JSON with conversation name and summarized messages
                                          """
    try:
              org_id = get_organization_id()
        conversation = make_api_request(
                      f"organizations/{org_id}/chat_conversations/{conversation_id}"
        )

        all_messages = conversation.get("chat_messages", [])

        # Get first 3 and last 3 messages
        if len(all_messages) <= 6:
                      summary_messages = all_messages
else:
            summary_messages = all_messages[:3] + [{"text": f"... ({len(all_messages) - 6} messages omitted) ...", "sender": "system"}] + all_messages[-3:]

        messages = []
        for msg in summary_messages:
                      messages.append({
                          "role": msg.get("sender"),
                          "content": msg.get("text", "")[:500] + ("..." if len(msg.get("text", "")) > 500 else ""),
        })

        result = {
                      "id": conversation.get("uuid"),
                      "name": conversation.get("name") or "Untitled",
                      "total_messages": len(all_messages),
                      "messages": messages
        }

        return json.dumps(result, indent=2)

except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
      mcp.run()
