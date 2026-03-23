#!/usr/bin/env python3
"""
MCP Server for bidirectional Claude.ai context bridge.

Reads conversations and Project knowledge from claude.ai.
Pushes status, TODOs, and session logs back to claude.ai Projects.
"""

import json
import re

from mcp.server.fastmcp import FastMCP

from context_bridge.conversations_api import (
    list_conversations,
    get_conversation,
    search_conversations,
    get_conversation_summary,
)
from context_bridge.projects_api import ProjectsAPI
from context_bridge.config import ProjectConfig
from context_bridge.content_generator import ContentGenerator

mcp = FastMCP("context-bridge")

# Register conversation tools (unchanged)
mcp.tool()(list_conversations)
mcp.tool()(get_conversation)
mcp.tool()(search_conversations)
mcp.tool()(get_conversation_summary)

# Shared instances
_projects = ProjectsAPI()


def _resolve_project_id(project: str = None) -> str:
    """Resolve project ID from argument, config, or cache."""
    if project:
        if re.match(
            r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$',
            project,
            re.I,
        ):
            return project
        resolved = _projects.resolve_project_id(project)
        if resolved:
            return resolved
        raise ValueError(f"Project '{project}' not found")

    config = ProjectConfig()
    if config.project_id:
        return config.project_id
    if config.cached_project_id:
        return config.cached_project_id
    if config.project_name:
        resolved = _projects.resolve_project_id(config.project_name)
        if resolved:
            config.save_cached_project_id(resolved)
            return resolved
        raise ValueError(
            f"Project '{config.project_name}' from CLAUDE.md not found on claude.ai. "
            "Create it first or use an explicit project ID."
        )
    raise ValueError(
        "No project configured. Add <!-- claude-project: Name --> to CLAUDE.md "
        "or pass the project parameter explicitly."
    )


@mcp.tool()
def list_projects() -> str:
    """
    List all claude.ai Projects in your organization.

    Returns:
        JSON list of projects with id, name, and description
    """
    return _projects.list_projects()


@mcp.tool()
def list_project_docs(project: str = "") -> str:
    """
    List knowledge documents in a claude.ai Project.

    Args:
        project: Project name or UUID. If empty, resolved from CLAUDE.md config.

    Returns:
        JSON list of documents with id, file_name, and created_at
    """
    try:
        project_id = _resolve_project_id(project or None)
        return _projects.list_project_docs(project_id)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_project_doc(doc_id: str, project: str = "") -> str:
    """
    Read a specific knowledge document from a claude.ai Project.

    Use list_project_docs first to find available documents.

    Args:
        doc_id: The UUID of the document to read
        project: Project name or UUID. If empty, resolved from CLAUDE.md config.

    Returns:
        JSON with document id, file_name, content, and created_at
    """
    try:
        project_id = _resolve_project_id(project or None)
        return _projects.get_project_doc(project_id, doc_id)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_project_conversations(project: str = "") -> str:
    """
    List conversations within a claude.ai Project.

    Args:
        project: Project name or UUID. If empty, resolved from CLAUDE.md config.

    Returns:
        JSON list of conversations with id, name, and timestamps
    """
    try:
        project_id = _resolve_project_id(project or None)
        return _projects.list_project_conversations(project_id)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_to_project(content: str, doc_name: str, project: str = "") -> str:
    """
    Push arbitrary content as a knowledge document to a claude.ai Project.

    Creates or replaces the document if one with the same name exists.

    Args:
        content: Markdown content to push
        doc_name: Name for the document (e.g., 'design-notes.md')
        project: Project name or UUID. If empty, resolved from CLAUDE.md config.

    Returns:
        JSON with the created document info
    """
    try:
        project_id = _resolve_project_id(project or None)
        result = _projects.upsert_doc(project_id, doc_name, content)
        return json.dumps(
            {
                "status": "success",
                "doc_id": result.get("uuid"),
                "file_name": doc_name,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_session_summary(project: str = "") -> str:
    """
    Auto-generate and push a status summary to a claude.ai Project.

    Generates content from git state: recent commits, current branch, diff stats.

    Args:
        project: Project name or UUID. If empty, resolved from CLAUDE.md config.

    Returns:
        JSON with push result
    """
    try:
        project_id = _resolve_project_id(project or None)
        config = ProjectConfig()
        gen = ContentGenerator(repo_name=config.repo_name)
        content = gen.generate_status()
        doc_name = gen.status_doc_name()
        result = _projects.upsert_doc(project_id, doc_name, content)
        return json.dumps(
            {
                "status": "success",
                "doc_id": result.get("uuid"),
                "file_name": doc_name,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def push_todos(todos: list[str], project: str = "") -> str:
    """
    Push a TODO list to a claude.ai Project.

    Args:
        todos: List of TODO items. Prefix with '[x]' for completed items.
        project: Project name or UUID. If empty, resolved from CLAUDE.md config.

    Returns:
        JSON with push result
    """
    try:
        project_id = _resolve_project_id(project or None)
        config = ProjectConfig()
        gen = ContentGenerator(repo_name=config.repo_name)
        content = gen.generate_todos(todos)
        doc_name = gen.todos_doc_name()
        result = _projects.upsert_doc(project_id, doc_name, content)
        return json.dumps(
            {
                "status": "success",
                "doc_id": result.get("uuid"),
                "file_name": doc_name,
            },
            indent=2,
        )
    except Exception as e:
        return json.dumps({"error": str(e)})


if __name__ == "__main__":
    mcp.run()
