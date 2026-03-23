"""Conversation reading tools for the MCP server."""

import json

from context_bridge.auth import ClaudeAuth


def _get_auth() -> ClaudeAuth:
    """Lazy-initialize auth to avoid import-time HTTP calls."""
    if not hasattr(_get_auth, "_instance"):
        _get_auth._instance = ClaudeAuth()
    return _get_auth._instance


def list_conversations(limit: int = 20) -> str:
    """List recent conversations from Claude.ai."""
    try:
        org_id = _get_auth().get_organization_id()
        conversations = _get_auth().get(f"organizations/{org_id}/chat_conversations")
        result = []
        for conv in conversations[:limit]:
            result.append({
                "id": conv.get("uuid"),
                "name": conv.get("name") or "Untitled",
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at"),
            })
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_conversation(conversation_id: str) -> str:
    """Get the full content of a specific conversation."""
    try:
        org_id = _get_auth().get_organization_id()
        conversation = _get_auth().get(
            f"organizations/{org_id}/chat_conversations/{conversation_id}"
        )
        messages = []
        for msg in conversation.get("chat_messages", []):
            messages.append({
                "role": msg.get("sender"),
                "content": msg.get("text", ""),
                "created_at": msg.get("created_at"),
            })
        return json.dumps({
            "id": conversation.get("uuid"),
            "name": conversation.get("name") or "Untitled",
            "created_at": conversation.get("created_at"),
            "messages": messages,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def search_conversations(query: str, limit: int = 10) -> str:
    """Search conversations by name/title."""
    try:
        org_id = _get_auth().get_organization_id()
        conversations = _get_auth().get(f"organizations/{org_id}/chat_conversations")
        query_lower = query.lower()
        matches = []
        for conv in conversations:
            name = conv.get("name") or ""
            if query_lower in name.lower():
                matches.append({
                    "id": conv.get("uuid"),
                    "name": name or "Untitled",
                    "created_at": conv.get("created_at"),
                })
                if len(matches) >= limit:
                    break
        return json.dumps(matches, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


def get_conversation_summary(conversation_id: str) -> str:
    """Get first and last messages of a conversation."""
    try:
        org_id = _get_auth().get_organization_id()
        conversation = _get_auth().get(
            f"organizations/{org_id}/chat_conversations/{conversation_id}"
        )
        all_messages = conversation.get("chat_messages", [])
        if len(all_messages) <= 6:
            summary_messages = all_messages
        else:
            summary_messages = (
                all_messages[:3]
                + [{"text": f"... ({len(all_messages) - 6} messages omitted) ...", "sender": "system"}]
                + all_messages[-3:]
            )
        messages = []
        for msg in summary_messages:
            text = msg.get("text", "")
            messages.append({
                "role": msg.get("sender"),
                "content": text[:500] + ("..." if len(text) > 500 else ""),
            })
        return json.dumps({
            "id": conversation.get("uuid"),
            "name": conversation.get("name") or "Untitled",
            "total_messages": len(all_messages),
            "messages": messages,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})
