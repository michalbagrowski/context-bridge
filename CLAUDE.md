# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

**claude-memory** — an MCP server (`server.py` + `context_bridge/` package) that gives Claude Code persistent memory across terminal restarts and context-window compaction, targeted access to relevant claude.ai conversations, and bidirectional sync with claude.ai Projects.

## Commands

```bash
# Install dependencies
pip install -r requirements.txt

# Run the server directly (smoke-test)
python3 server.py

# Test tools interactively
python3 -m mcp dev server.py

# Run all tests
pytest test_server.py tests/ -v

# Run project sync CLI
python -m context_bridge --auto
```

Core server is `server.py`. Project sync lives in `context_bridge/` package. Tests in `test_server.py` (local storage) and `tests/` (project sync).

## Hard constraint — no LLM inference in server.py

`server.py` must never import `anthropic` or call any inference API. All summarisation and reasoning is performed by Claude Code itself (subscription), not programmatic API calls. The server is a dumb data layer: fetch, store, return raw content. Claude Code does the thinking.

## Architecture

Three independent feature areas share `server.py`.

### 1. Local storage tools — no network, no Chrome required

Storage root: `~/.claude-memory/`

```
~/.claude-memory/
├── sessions/    {project_name}_{sha1[:8]}_{YYYYMMDDTHHMMSSZ}_{id8}.json
├── images/      {image_id12}.{ext}  +  {image_id12}.json (metadata)
├── projects/    {project_key}.json  (conversation registry, includes project_path)
└── summaries/   {conversation_id}.json  (cached conversation summaries)
```

**Private helpers (shared across tools):**
- `_storage(subdir)` — mkdir + return Path under `~/.claude-memory/`
- `_project_key(path)` — `{dirname}_{sha1[:8]}`, stable and filesystem-safe
- `_load_registry(pk)` / `_save_registry(pk, reg)` — read/write `projects/{pk}.json`
- `_get_latest_checkpoint(project_path)` — returns checkpoint dict or `{"found": False}`; used by both `resume_session` and `get_latest_session_checkpoint`
- `_get_linked_conversations(project_key)` — returns conversations list from registry; used by both `resume_session` and `get_project_conversations`
- `_fetch_and_cache_summary(conv_id, refresh)` — fetch from cache or API, always caches result; used by `get_conversation_summary` and `link_conversation` auto-note generation; raises `RuntimeError` on API failure

**Timestamp format in filenames:** `20260310T143022Z` (ISO 8601 basic). Alphabetical descending = chronological descending — no date parsing needed for sorting.

**`CHECKPOINT_RE`:** `^(.+)_(\d{8}T\d{6}Z)_([0-9a-f]{8})$` — used by `list_all_projects` to extract project_key from checkpoint filenames. Greedy `.+` correctly captures keys containing underscores because the timestamp `\d{8}T\d{6}Z` is lexically distinct.

**Session tools:** `resume_session` ← primary session entry point; `save_session_checkpoint`, `get_latest_session_checkpoint`, `list_session_checkpoints`, `cleanup_session_checkpoints`, `list_all_projects`

**Image tools:** `save_image`, `get_image`, `list_images`, `cleanup_images`

**Registry tools:** `link_conversation` (note auto-generated from first message if omitted; `project_path` stored in registry), `unlink_conversation`, `get_project_conversations`

**GC tools:** `cleanup_session_checkpoints`, `cleanup_images`, `cleanup_summaries` — all default to `dry_run=True`

### 2. Claude.ai conversation tools — requires Chrome + claude.ai login

Request flow on every call:
1. `get_all_cookies()` — reads Chrome's cookie store via `browser_cookie3` for `.claude.ai`
2. `get_organization_id()` — `GET /api/organizations`, selects first org with `'chat'` capability that has actual conversations
3. Tool-specific API call via `curl_cffi` with `impersonate="chrome120"` (plain `requests` is blocked by TLS fingerprinting)

**Tools:** `list_conversations`, `get_conversation`, `search_conversations`, `get_conversation_summary`

`get_conversation_summary` is a thin wrapper over `_fetch_and_cache_summary`.

**Constraints:**
- Chrome only — `browser_cookie3` is hardcoded to Chrome
- Cookies and org ID are re-fetched on every call (no in-memory cache)
- `search_conversations` is client-side only: fetches all, filters by name substring
- `link_conversation` with no note attempts auto-generation via `_fetch_and_cache_summary`; silently stores empty note if Chrome is unavailable

### 3. claude.ai Project sync tools — requires Chrome + claude.ai login

Self-contained `context_bridge/` package with its own auth layer:

```
context_bridge/
├── auth.py                # Cookie auth + HTTP client (GET/POST/DELETE), 5-min cookie cache
├── projects_api.py        # Projects CRUD: list projects, list/get/create/delete docs
├── config.py              # Parse <!-- claude-project: Name --> from CLAUDE.md, UUID cache
├── content_generator.py   # Generate status/TODOs/session logs from git state
├── conversations_api.py   # Conversation read tools (not used by server.py, standalone)
├── push.py                # CLI entry point: python -m context_bridge --auto
└── __main__.py            # Package runner
```

**Tools (registered in server.py):** `list_projects`, `list_project_docs`, `get_project_doc`, `push_to_project`, `push_session_summary`, `push_todos`

**Project mapping:** `<!-- claude-project: Name -->` HTML comment in a repo's `CLAUDE.md`. Resolved name → UUID cached in `.claude-project-cache` (gitignored).

**Auto-push:** `hooks/post_push.sh` calls `python -m context_bridge.push --auto` with a 2-minute cooldown.

**Doc naming convention:** `[cli] <Type> - <repo-name>.md` — prevents collisions when multiple repos push to one Project.

**Update strategy:** Upsert = delete existing doc by filename + create new (no PATCH endpoint). Status and TODOs are upserted; session logs are append-only per day.

## Testing

`test_server.py` covers all local storage tools. The `isolated_storage` fixture (`autouse=True`) monkeypatches `server.STORAGE_DIR` to `tmp_path` for every test — no real `~/.claude-memory/` is touched.

`tests/` covers the `context_bridge` package: auth, config parsing, projects API, content generation, and integration tests. All use mocked HTTP — no live Chrome needed.

Claude.ai API tools are not tested (require a live Chrome session). `get_conversation_summary` is tested via `patch.object(server, "make_api_request", ...)`.

## Dependencies

- `mcp[cli]` — FastMCP, stdio transport, `@mcp.tool()` decorator
- `browser_cookie3` — Chrome cookie extraction (conversation + project tools)
- `curl_cffi` — browser-impersonating HTTP client (conversation + project tools)
- `pytest` — test runner
- stdlib — `hashlib`, `re`, `shutil`, `uuid`, `pathlib`, `datetime` (all local tools)
