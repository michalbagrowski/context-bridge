"""Verify all tools are registered on the MCP server."""

import sys
import os

# Ensure the project root is on sys.path so `import server` works
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))


def test_all_tools_registered():
    import server

    # _tool_manager._tools is a dict keyed by tool name in mcp >= 1.x
    tool_names = list(server.mcp._tool_manager._tools.keys())

    expected = [
        "list_conversations",
        "get_conversation",
        "search_conversations",
        "get_conversation_summary",
        "list_projects",
        "list_project_docs",
        "get_project_doc",
        "list_project_conversations",
        "push_to_project",
        "push_session_summary",
        "push_todos",
    ]
    for name in expected:
        assert name in tool_names, f"Tool '{name}' not registered. Found: {tool_names}"
