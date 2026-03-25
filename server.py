#!/usr/bin/env python3
"""
claude-memory MCP server.

Gives Claude Code persistent memory across terminal restarts and context-window
compaction, and provides targeted access to relevant claude.ai conversations.

Local storage tools (no Chrome required):
  - resume_session                    ← start here every session
  - save_session_checkpoint / list_session_checkpoints / cleanup_session_checkpoints
  - save_image / get_image / list_images / cleanup_images
  - link_conversation / unlink_conversation / get_project_conversations
  - list_all_projects
  - cleanup_summaries

Claude.ai conversation tools (require Chrome login):
  - list_conversations / get_conversation / search_conversations
  - get_conversation_summary          ← cached on first fetch

IMPORTANT — no LLM inference in this file:
  This server retrieves and stores data only. All summarisation, relevance
  judgement, and reasoning is performed by Claude Code itself (subscription),
  never by programmatic calls to the Anthropic API. Do not import anthropic
  or any other inference SDK here.
"""

import hashlib
import json
import re
import shutil
import uuid
from datetime import datetime, timezone
from pathlib import Path

import browser_cookie3
from curl_cffi import requests
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("claude-memory")

CLAUDE_API_BASE = "https://claude.ai/api"
STORAGE_DIR = Path.home() / ".claude-memory"

# Parses checkpoint filenames: {project_key}_{YYYYMMDDTHHMMSSZ}_{id8}
# The timestamp pattern is distinct enough that greedy (.+) correctly captures
# the full project_key even when it contains underscores.
CHECKPOINT_RE = re.compile(r"^(.+)_(\d{8}T\d{6}Z)_([0-9a-f]{8})$")


# ── Storage helpers ───────────────────────────────────────────────────────────


def _storage(subdir: str) -> Path:
    """Return (and create) a storage subdirectory under STORAGE_DIR."""
    path = STORAGE_DIR / subdir
    path.mkdir(parents=True, exist_ok=True)
    return path


def _project_key(project_path: str) -> str:
    """
    Derive a stable, filesystem-safe key from a project path.
    Format: {directory_name}_{sha1_prefix8}
    """
    resolved = Path(project_path).expanduser().resolve()
    h = hashlib.sha1(str(resolved).encode()).hexdigest()[:8]
    safe_name = "".join(c if c.isalnum() or c in "-_." else "_" for c in resolved.name)
    return f"{safe_name}_{h}"


def _load_registry(project_key: str) -> dict:
    registry_file = _storage("projects") / f"{project_key}.json"
    if registry_file.exists():
        return json.loads(registry_file.read_text())
    return {"conversations": []}


def _save_registry(project_key: str, registry: dict) -> None:
    (_storage("projects") / f"{project_key}.json").write_text(
        json.dumps(registry, indent=2)
    )


def _get_latest_checkpoint(project_path: str) -> dict:
    """Return the most recent checkpoint dict for a project, or {"found": False}."""
    sessions_dir = _storage("sessions")
    project_key = _project_key(project_path)
    # Filenames contain ISO-basic timestamps → reverse alpha == reverse chronological
    checkpoints = sorted(sessions_dir.glob(f"{project_key}_*.json"), reverse=True)
    if not checkpoints:
        return {"found": False, "message": f"No checkpoints found for: {project_path}"}
    checkpoint = json.loads(checkpoints[0].read_text())
    checkpoint["found"] = True
    checkpoint["total_checkpoints"] = len(checkpoints)
    return checkpoint


def _get_linked_conversations(project_key: str) -> list:
    """Return the list of conversations linked to a project."""
    return _load_registry(project_key).get("conversations", [])


def _fetch_and_cache_summary(conversation_id: str, refresh: bool = False) -> dict:
    """
    Fetch a conversation summary from cache or from the claude.ai API.

    Caches the result to ~/.claude-memory/summaries/{conversation_id}.json so
    subsequent calls are served from disk with no API call.
    Raises RuntimeError if the API call fails.
    """
    cache_file = _storage("summaries") / f"{conversation_id}.json"
    if not refresh and cache_file.exists():
        return json.loads(cache_file.read_text())

    org_id = get_organization_id()
    conversation = make_api_request(
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

    messages = [
        {
            "role": msg.get("sender"),
            "content": msg.get("text", "")[:500] + ("..." if len(msg.get("text", "")) > 500 else ""),
        }
        for msg in summary_messages
    ]
    result = {
        "id": conversation.get("uuid"),
        "name": conversation.get("name") or "Untitled",
        "total_messages": len(all_messages),
        "messages": messages,
        "cached_at": datetime.now(timezone.utc).isoformat(),
    }
    cache_file.write_text(json.dumps(result, indent=2))
    return result


# ── Claude.ai helpers ─────────────────────────────────────────────────────────


def get_all_cookies() -> str:
    """Get all Claude cookies formatted as a cookie header string."""
    try:
        cj = browser_cookie3.chrome(domain_name='.claude.ai')
        return "; ".join(f"{c.name}={c.value}" for c in cj)
    except Exception as e:
        raise RuntimeError(f"Could not get cookies from Chrome: {e}")


def make_api_request(endpoint: str) -> dict:
    """Make an authenticated request to the Claude.ai API."""
    cookie_header = get_all_cookies()
    url = f"{CLAUDE_API_BASE}/{endpoint}"
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json',
        'Accept-Language': 'en-US,en;q=0.5',
        'Referer': 'https://claude.ai/chats',
        'Content-Type': 'application/json',
        'Cookie': cookie_header,
    }
    response = requests.get(url, headers=headers, impersonate="chrome120")
    if response.status_code != 200:
        raise RuntimeError(f"API request failed: {response.status_code} - {response.text[:200]}")
    return response.json()


def get_organization_id() -> str:
    """
    Get the organisation ID that contains conversations.

    Tries each org with 'chat' capability and returns the first one that
    actually has conversations. Falls back to the first chat-capable org.
    """
    orgs = make_api_request("organizations")
    if not orgs:
        raise RuntimeError("No organizations found")

    chat_orgs = [o for o in orgs if 'chat' in o.get('capabilities', [])]
    if not chat_orgs:
        chat_orgs = orgs

    for org in chat_orgs:
        org_id = org['uuid']
        try:
            if make_api_request(f"organizations/{org_id}/chat_conversations"):
                return org_id
        except RuntimeError:
            continue

    return chat_orgs[0]['uuid']


# ── Session tools ─────────────────────────────────────────────────────────────


@mcp.tool()
def resume_session(project_path: str) -> str:
    """
    Restore full context for a project at the start of a Claude Code session.

    This is the single call you need at session start. It returns:
      - The latest session checkpoint (what was accomplished, in-progress tasks,
        key files, decisions made, open questions)
      - All conversations linked to this project with their notes

    From the notes alone you can usually decide what, if anything, to fetch.
    If a note is insufficient, use get_conversation_summary (cached, no Chrome
    needed after first fetch) before reaching for get_conversation.

    Args:
        project_path: Absolute path to the project directory

    Returns:
        JSON with "checkpoint" and "linked_conversations" keys
    """
    try:
        project_key = _project_key(project_path)
        return json.dumps({
            "checkpoint": _get_latest_checkpoint(project_path),
            "linked_conversations": _get_linked_conversations(project_key),
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def save_session_checkpoint(
    project_path: str,
    summary: str,
    current_task: str = "",
    key_files: str = "",
    open_questions: str = "",
    decisions_made: str = "",
) -> str:
    """
    Save a checkpoint of the current Claude Code session to disk.

    Call this at major milestones and always before stopping work. The next
    session recovers everything via resume_session() without re-explaining.

    Checkpoints are stored in ~/.claude-memory/sessions/, keyed by project path.

    Args:
        project_path:    Absolute path to the project directory
        summary:         What was accomplished (specific files, features, fixes)
        current_task:    What is in-progress or was interrupted. Leave empty if
                         the session ended at a clean stopping point.
        key_files:       Comma-separated paths of files created or modified
        open_questions:  Unresolved questions or blockers for next session
        decisions_made:  Architectural or design decisions and their rationale

    Returns:
        JSON with checkpoint_id and the path where it was saved
    """
    try:
        sessions_dir = _storage("sessions")
        checkpoint_id = str(uuid.uuid4())[:8]
        project_key = _project_key(project_path)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        filename = f"{project_key}_{timestamp}_{checkpoint_id}.json"

        checkpoint = {
            "checkpoint_id": checkpoint_id,
            "project_path": str(Path(project_path).expanduser().resolve()),
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "summary": summary,
            "current_task": current_task,
            "key_files": [f.strip() for f in key_files.split(",") if f.strip()],
            "open_questions": open_questions,
            "decisions_made": decisions_made,
        }

        checkpoint_path = sessions_dir / filename
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2))
        return json.dumps({"checkpoint_id": checkpoint_id, "saved_to": str(checkpoint_path)})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_latest_session_checkpoint(project_path: str) -> str:
    """
    Retrieve the most recent session checkpoint for a project.

    Prefer resume_session() at session start — it returns this plus linked
    conversations in a single call. Use this tool when you need only the
    checkpoint mid-session.

    Args:
        project_path: Absolute path to the project directory

    Returns:
        JSON with the full checkpoint, or {"found": false} if none exist
    """
    try:
        return json.dumps(_get_latest_checkpoint(project_path), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_session_checkpoints(project_path: str, limit: int = 10) -> str:
    """
    List recent session checkpoints for a project (most recent first).

    Args:
        project_path: Absolute path to the project directory
        limit:        Maximum number of checkpoints to list

    Returns:
        JSON list with id, timestamp, and summary preview for each checkpoint
    """
    try:
        sessions_dir = _storage("sessions")
        project_key = _project_key(project_path)
        checkpoints = sorted(
            sessions_dir.glob(f"{project_key}_*.json"), reverse=True
        )[:limit]
        results = [
            {
                "checkpoint_id": (cp := json.loads(f.read_text())).get("checkpoint_id"),
                "saved_at": cp.get("saved_at"),
                "summary": cp.get("summary", "")[:200],
                "current_task": cp.get("current_task", "")[:100],
            }
            for f in checkpoints
        ]
        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_all_projects() -> str:
    """
    List all projects that have stored checkpoints or linked conversations.

    Useful at the start of a session when you don't know the project path, or
    to get an overview of all projects claude-memory knows about.

    Returns:
        JSON list of projects sorted by most recently checkpointed first,
        each with project_path, last_checkpoint, checkpoint_count, and
        linked_conversations count.
    """
    try:
        sessions_dir = _storage("sessions")
        projects_dir = _storage("projects")
        projects: dict[str, dict] = {}

        # Gather from checkpoint files (reverse sort = newest first per project)
        for f in sorted(sessions_dir.glob("*.json"), reverse=True):
            m = CHECKPOINT_RE.match(f.stem)
            if not m:
                continue
            pk = m.group(1)
            if pk not in projects:
                try:
                    cp = json.loads(f.read_text())
                    projects[pk] = {
                        "project_path": cp.get("project_path"),
                        "last_checkpoint": cp.get("saved_at"),
                        "checkpoint_count": 1,
                        "linked_conversations": 0,
                    }
                except Exception:
                    continue
            else:
                projects[pk]["checkpoint_count"] += 1

        # Layer in registry data
        for reg_file in projects_dir.glob("*.json"):
            pk = reg_file.stem
            try:
                reg = json.loads(reg_file.read_text())
            except Exception:
                continue
            conv_count = len(reg.get("conversations", []))
            if pk in projects:
                projects[pk]["linked_conversations"] = conv_count
            else:
                projects[pk] = {
                    "project_path": reg.get("project_path"),
                    "last_checkpoint": None,
                    "checkpoint_count": 0,
                    "linked_conversations": conv_count,
                }

        result = sorted(
            projects.values(),
            key=lambda p: p.get("last_checkpoint") or "",
            reverse=True,
        )
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cleanup_session_checkpoints(
    project_path: str,
    keep_latest: int = 10,
    dry_run: bool = True,
) -> str:
    """
    Delete old session checkpoints, keeping only the N most recent.

    Run with dry_run=true first to preview, then dry_run=false to delete.

    Args:
        project_path: Absolute path to the project directory
        keep_latest:  Number of most-recent checkpoints to keep (default 10)
        dry_run:      If true (default), report without deleting

    Returns:
        JSON with counts and a preview of what was (or would be) deleted
    """
    try:
        sessions_dir = _storage("sessions")
        project_key = _project_key(project_path)
        all_checkpoints = sorted(
            sessions_dir.glob(f"{project_key}_*.json"), reverse=True
        )
        to_keep = all_checkpoints[:keep_latest]
        to_delete = all_checkpoints[keep_latest:]

        previews = []
        for f in to_delete:
            try:
                cp = json.loads(f.read_text())
                previews.append({
                    "checkpoint_id": cp.get("checkpoint_id"),
                    "saved_at": cp.get("saved_at"),
                    "summary": cp.get("summary", "")[:100],
                    "file": f.name,
                })
            except Exception:
                previews.append({"file": f.name})
            if not dry_run:
                f.unlink()

        return json.dumps({
            "dry_run": dry_run,
            "project_path": str(Path(project_path).expanduser().resolve()),
            "total_found": len(all_checkpoints),
            "kept": len(to_keep),
            "deleted": len(to_delete),
            "action": "would delete" if dry_run else "deleted",
            "checkpoints": previews,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Image persistence tools ───────────────────────────────────────────────────


@mcp.tool()
def save_image(
    description: str,
    source_path: str = "",
    tags: str = "",
) -> str:
    """
    Save an image to persistent storage so it survives context-window compaction.

    Call this immediately when any screenshot or image file is shared. If
    source_path is provided, the file is copied to ~/.claude-memory/images/.
    A detailed description is always stored alongside it.

    After compaction causes the image to disappear, call get_image(image_id)
    to retrieve the stored path, then use the Read tool on that path to
    re-embed the image.

    For clipboard-pasted images with no file path, omit source_path and write
    a thorough description — this is the record that survives compaction.

    Args:
        description: Everything visible in the image: UI elements, error text,
                     file paths, colours, layout. Used as fallback if file is lost.
        source_path: Path to the image file to copy (PNG, JPG, GIF, WebP…).
                     Leave empty for clipboard-pasted images.
        tags:        Comma-separated tags for filtering (e.g. "screenshot,bug,login")

    Returns:
        JSON with image_id and stored_path (if a file was saved)
    """
    try:
        images_dir = _storage("images")
        image_id = str(uuid.uuid4()).replace("-", "")[:12]

        stored_path = None
        if source_path:
            source = Path(source_path).expanduser().resolve()
            if not source.exists():
                return json.dumps({"error": f"File not found: {source_path}"})
            suffix = source.suffix.lower() or ".png"
            dest = images_dir / f"{image_id}{suffix}"
            shutil.copy2(source, dest)
            stored_path = str(dest)

        metadata = {
            "image_id": image_id,
            "stored_path": stored_path,
            "original_path": str(Path(source_path).expanduser().resolve()) if source_path else None,
            "description": description,
            "tags": [t.strip() for t in tags.split(",") if t.strip()],
            "saved_at": datetime.now(timezone.utc).isoformat(),
            "has_file": stored_path is not None,
        }
        (images_dir / f"{image_id}.json").write_text(json.dumps(metadata, indent=2))

        response: dict = {"image_id": image_id, "has_file": stored_path is not None}
        if stored_path:
            response["stored_path"] = stored_path
            response["message"] = (
                f"Image saved. After compaction: call get_image('{image_id}') "
                f"then use the Read tool on stored_path to re-embed it."
            )
        else:
            response["message"] = (
                f"Description saved (no file). After compaction: call "
                f"get_image('{image_id}') to retrieve the description."
            )
        return json.dumps(response)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_image(image_id: str) -> str:
    """
    Retrieve a saved image record by ID.

    After compaction causes an image to disappear, call this to get the stored
    file path and description. If has_file is true, use the Read tool on
    stored_path to re-embed the image. If has_file is false, read the description.

    Args:
        image_id: The image ID returned by save_image()

    Returns:
        JSON with stored_path, description, and original metadata
    """
    try:
        images_dir = _storage("images")
        meta_file = images_dir / f"{image_id}.json"
        if not meta_file.exists():
            return json.dumps({"error": f"No image found with id: {image_id}"})
        metadata = json.loads(meta_file.read_text())
        if metadata.get("stored_path"):
            metadata["file_exists"] = Path(metadata["stored_path"]).exists()
        return json.dumps(metadata, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def list_images(tags: str = "", limit: int = 20) -> str:
    """
    List saved images, optionally filtered by tag.

    Args:
        tags:  Comma-separated tags to filter by. Empty = return all.
        limit: Maximum number of results (most recently saved first)

    Returns:
        JSON list with id, description preview, stored_path, tags, and saved_at
    """
    try:
        images_dir = _storage("images")
        filter_tags = {t.strip().lower() for t in tags.split(",") if t.strip()}
        results = []
        for meta_file in sorted(
            images_dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            if len(results) >= limit:
                break
            meta = json.loads(meta_file.read_text())
            if filter_tags:
                image_tags = {t.lower() for t in meta.get("tags", [])}
                if not filter_tags & image_tags:
                    continue
            results.append({
                "image_id": meta.get("image_id"),
                "stored_path": meta.get("stored_path"),
                "has_file": meta.get("has_file", False),
                "description": meta.get("description", "")[:150],
                "tags": meta.get("tags", []),
                "saved_at": meta.get("saved_at"),
            })
        return json.dumps(results, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def cleanup_images(
    older_than_days: int = 30,
    tags: str = "",
    remove_broken_refs: bool = True,
    dry_run: bool = True,
) -> str:
    """
    Delete old images and orphaned metadata records.

    Two modes run in a single pass:
    - Age-based: removes images (file + metadata) saved more than older_than_days ago
    - Broken-ref: removes metadata where has_file=true but the file is gone

    Run with dry_run=true first to preview, then dry_run=false to delete.

    Args:
        older_than_days:    Delete images older than this many days. 0 = skip age check.
        tags:               Restrict cleanup to images with these tags. Empty = all.
        remove_broken_refs: Remove metadata whose image file is missing (default true)
        dry_run:            If true (default), report without deleting

    Returns:
        JSON summary broken down by deletion reason
    """
    try:
        images_dir = _storage("images")
        filter_tags = {t.strip().lower() for t in tags.split(",") if t.strip()}
        now = datetime.now(timezone.utc)
        age_deleted, broken_deleted = [], []

        for meta_file in list(images_dir.glob("*.json")):
            try:
                meta = json.loads(meta_file.read_text())
            except Exception:
                continue

            image_id = meta.get("image_id", meta_file.stem)
            stored_path = meta.get("stored_path")
            image_file = Path(stored_path) if stored_path else None

            if filter_tags:
                image_tags = {t.lower() for t in meta.get("tags", [])}
                if not filter_tags & image_tags:
                    continue

            if remove_broken_refs and meta.get("has_file") and (
                image_file is None or not image_file.exists()
            ):
                broken_deleted.append({
                    "image_id": image_id,
                    "description": meta.get("description", "")[:80],
                    "saved_at": meta.get("saved_at"),
                    "reason": "broken_ref",
                })
                if not dry_run:
                    meta_file.unlink()
                continue

            if older_than_days > 0:
                try:
                    saved_at = datetime.fromisoformat(meta.get("saved_at", ""))
                    age = (now - saved_at).days
                except (ValueError, TypeError):
                    continue  # unparseable date — skip safely
                if age >= older_than_days:
                    age_deleted.append({
                        "image_id": image_id,
                        "description": meta.get("description", "")[:80],
                        "saved_at": meta.get("saved_at"),
                        "age_days": age,
                        "had_file": meta.get("has_file", False),
                        "reason": "age",
                    })
                    if not dry_run:
                        meta_file.unlink()
                        if image_file and image_file.exists():
                            image_file.unlink()

        return json.dumps({
            "dry_run": dry_run,
            "older_than_days": older_than_days,
            "tag_filter": tags or "(none)",
            "action": "would delete" if dry_run else "deleted",
            "total": len(age_deleted) + len(broken_deleted),
            "by_age": {"count": len(age_deleted), "items": age_deleted},
            "broken_refs": {"count": len(broken_deleted), "items": broken_deleted},
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Project conversation registry ─────────────────────────────────────────────


@mcp.tool()
def link_conversation(
    project_path: str,
    conversation_id: str,
    note: str = "",
) -> str:
    """
    Link a Claude.ai conversation to a project.

    Call this when you find a conversation relevant to the current project.
    If note is omitted, a brief note is auto-generated from the conversation's
    name and first message (requires Chrome; gracefully skipped if unavailable).
    You can always refine the note by calling link_conversation again.

    The note is the primary decision tool for future sessions: write it so
    Claude Code can decide whether to fetch the conversation without reading it.

    Args:
        project_path:    Absolute path to the project directory
        conversation_id: UUID of the conversation (from list_conversations)
        note:            One-line description of what this conversation contains
                         and why it matters. Auto-generated if omitted.

    Returns:
        JSON confirming the link was saved, including the note that was stored
    """
    try:
        project_key = _project_key(project_path)
        resolved_path = str(Path(project_path).expanduser().resolve())
        registry = _load_registry(project_key)

        # Auto-generate note from first message excerpt if not provided
        final_note = note
        if not final_note:
            try:
                summary = _fetch_and_cache_summary(conversation_id)
                conv_name = summary.get("name", "Untitled")
                first_excerpt = ""
                for msg in summary.get("messages", []):
                    text = msg.get("content", "")
                    if text and msg.get("role") != "system":
                        first_excerpt = text[:150].rstrip()
                        break
                final_note = f"{conv_name}: {first_excerpt}" if first_excerpt else conv_name
            except Exception:
                final_note = ""  # Chrome unavailable or API failed — store without note

        # Store project_path in registry so list_all_projects can find it
        registry["project_path"] = resolved_path

        for entry in registry["conversations"]:
            if entry["conversation_id"] == conversation_id:
                entry["note"] = final_note
                entry["updated_at"] = datetime.now(timezone.utc).isoformat()
                _save_registry(project_key, registry)
                return json.dumps({"status": "updated", "conversation_id": conversation_id, "note": final_note})

        registry["conversations"].append({
            "conversation_id": conversation_id,
            "note": final_note,
            "linked_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_registry(project_key, registry)
        return json.dumps({"status": "linked", "conversation_id": conversation_id, "note": final_note})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def unlink_conversation(project_path: str, conversation_id: str) -> str:
    """
    Remove a conversation link from a project.

    Args:
        project_path:    Absolute path to the project directory
        conversation_id: UUID of the conversation to unlink

    Returns:
        JSON confirming removal, or an error if the link was not found
    """
    try:
        project_key = _project_key(project_path)
        registry = _load_registry(project_key)
        before = len(registry["conversations"])
        registry["conversations"] = [
            e for e in registry["conversations"]
            if e["conversation_id"] != conversation_id
        ]
        if len(registry["conversations"]) == before:
            return json.dumps({"error": f"Conversation {conversation_id} is not linked to this project"})
        _save_registry(project_key, registry)
        return json.dumps({"status": "unlinked", "conversation_id": conversation_id})
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_project_conversations(project_path: str) -> str:
    """
    List conversations linked to a project, with their notes.

    Prefer resume_session() at session start — it returns this plus the
    checkpoint in a single call. Use this tool when you need only the
    conversation list mid-session.

    No API calls are made. Fetch order if you need more than the note:
      1. get_conversation_summary(id) — cached after first fetch
      2. get_conversation(id) — full content, last resort

    Args:
        project_path: Absolute path to the project directory

    Returns:
        JSON list of {conversation_id, note, linked_at}
    """
    try:
        project_key = _project_key(project_path)
        return json.dumps(_get_linked_conversations(project_key), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Garbage collection tools ──────────────────────────────────────────────────


@mcp.tool()
def cleanup_summaries(
    older_than_days: int = 90,
    dry_run: bool = True,
) -> str:
    """
    Delete cached conversation summaries older than N days.

    Summaries are cheap (small JSON files) and re-fetchable, so a long
    retention window (default 90 days) is appropriate. Summaries for
    conversations that no longer exist on claude.ai are harmless but can
    be cleaned up here.

    Run with dry_run=true first to preview, then dry_run=false to delete.

    Args:
        older_than_days: Delete summaries cached more than this many days ago
        dry_run:         If true (default), report without deleting

    Returns:
        JSON with count and list of summaries that were (or would be) deleted
    """
    try:
        summaries_dir = _storage("summaries")
        now = datetime.now(timezone.utc)
        deleted = []

        for f in summaries_dir.glob("*.json"):
            try:
                data = json.loads(f.read_text())
                cached_at = datetime.fromisoformat(data.get("cached_at", ""))
                age = (now - cached_at).days
            except (ValueError, TypeError):
                continue  # unparseable date — skip safely
            if age >= older_than_days:
                deleted.append({
                    "conversation_id": f.stem,
                    "name": data.get("name"),
                    "cached_at": data.get("cached_at"),
                    "age_days": age,
                })
                if not dry_run:
                    f.unlink()

        return json.dumps({
            "dry_run": dry_run,
            "older_than_days": older_than_days,
            "action": "would delete" if dry_run else "deleted",
            "count": len(deleted),
            "summaries": deleted,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── Claude.ai conversation tools ──────────────────────────────────────────────


@mcp.tool()
def list_conversations(limit: int = 20) -> str:
    """
    List recent conversations from Claude.ai.

    Use this only when discovering new conversations to link to a project.
    For reading already-linked conversations, use get_project_conversations
    or resume_session instead.

    Requires being logged into claude.ai in Chrome.

    Args:
        limit: Maximum number of conversations to return (default 20)

    Returns:
        JSON list of conversations with id, name, and timestamps
    """
    try:
        org_id = get_organization_id()
        conversations = make_api_request(f"organizations/{org_id}/chat_conversations")
        result = [
            {
                "id": conv.get("uuid"),
                "name": conv.get("name") or "Untitled",
                "created_at": conv.get("created_at"),
                "updated_at": conv.get("updated_at"),
            }
            for conv in conversations[:limit]
        ]
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_conversation(conversation_id: str) -> str:
    """
    Get the full content of a specific conversation from Claude.ai.

    This is the most expensive call — loads all messages. Use only when
    get_conversation_summary does not contain enough detail.

    Args:
        conversation_id: The UUID of the conversation

    Returns:
        JSON with conversation details and all messages
    """
    try:
        org_id = get_organization_id()
        conversation = make_api_request(
            f"organizations/{org_id}/chat_conversations/{conversation_id}"
        )
        messages = [
            {
                "role": msg.get("sender"),
                "content": msg.get("text", ""),
                "created_at": msg.get("created_at"),
            }
            for msg in conversation.get("chat_messages", [])
        ]
        result = {
            "id": conversation.get("uuid"),
            "name": conversation.get("name") or "Untitled",
            "created_at": conversation.get("created_at"),
            "messages": messages,
        }
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def search_conversations(query: str, limit: int = 10) -> str:
    """
    Search conversations by name/title from Claude.ai.

    Client-side substring match against conversation names only (not content).
    Use this when discovering conversations to link; once linked, use
    get_project_conversations instead.

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
                    "created_at": conv.get("created_at"),
                })
                if len(matches) >= limit:
                    break
        return json.dumps(matches, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


@mcp.tool()
def get_conversation_summary(conversation_id: str, refresh: bool = False) -> str:
    """
    Get a condensed view of a conversation (first and last few messages).

    Cached to ~/.claude-memory/summaries/ on first fetch — subsequent calls
    return the cached version with no API call and no Chrome required.
    Pass refresh=true to re-fetch after a conversation has been updated.

    Use this before get_conversation — it usually contains enough context
    without loading the full message history.

    Args:
        conversation_id: The UUID of the conversation
        refresh:         Re-fetch from claude.ai and update the cache

    Returns:
        JSON with conversation name, summarised messages, and cached_at timestamp
    """
    try:
        return json.dumps(_fetch_and_cache_summary(conversation_id, refresh), indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


# ── claude.ai Project tools ───────────────────────────────────────────────────
# Guarded import: if context_bridge is not installed, project tools are skipped
# and all pre-existing tools continue to work.

try:
    from context_bridge.projects_api import ProjectsAPI
    from context_bridge.config import ProjectConfig
    from context_bridge.content_generator import ContentGenerator
    _PROJECTS_AVAILABLE = True
except ImportError:
    _PROJECTS_AVAILABLE = False

_projects_api = ProjectsAPI() if _PROJECTS_AVAILABLE else None


def _resolve_project_id(project: str = None) -> str:
    """Resolve project ID from argument, config, or cache."""
    if project:
        import re as _re
        if _re.match(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$', project, _re.I):
            return project
        resolved = _projects_api.resolve_project_id(project)
        if resolved:
            return resolved
        raise ValueError(f"Project '{project}' not found")

    config = ProjectConfig()
    if config.project_id:
        return config.project_id
    if config.cached_project_id:
        return config.cached_project_id
    if config.project_name:
        resolved = _projects_api.resolve_project_id(config.project_name)
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


if not _PROJECTS_AVAILABLE:
    import sys
    print("context_bridge package not found — project sync tools disabled", file=sys.stderr)


def list_projects() -> str:
    """
    List all claude.ai Projects in your organization.

    Returns:
        JSON list of projects with id, name, and description
    """
    return _projects_api.list_projects()


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
        return _projects_api.list_project_docs(project_id)
    except Exception as e:
        return json.dumps({"error": str(e)})


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
        return _projects_api.get_project_doc(project_id, doc_id)
    except Exception as e:
        return json.dumps({"error": str(e)})


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
        result = _projects_api.upsert_doc(project_id, doc_name, content)
        return json.dumps({
            "status": "success",
            "doc_id": result.get("uuid"),
            "file_name": doc_name,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


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
        result = _projects_api.upsert_doc(project_id, doc_name, content)
        return json.dumps({
            "status": "success",
            "doc_id": result.get("uuid"),
            "file_name": doc_name,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


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
        result = _projects_api.upsert_doc(project_id, doc_name, content)
        return json.dumps({
            "status": "success",
            "doc_id": result.get("uuid"),
            "file_name": doc_name,
        }, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)})


if _PROJECTS_AVAILABLE:
    mcp.tool()(list_projects)
    mcp.tool()(list_project_docs)
    mcp.tool()(get_project_doc)
    mcp.tool()(push_to_project)
    mcp.tool()(push_session_summary)
    mcp.tool()(push_todos)


if __name__ == "__main__":
    mcp.run()
