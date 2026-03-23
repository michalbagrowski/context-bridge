# Context Bridge

A bidirectional MCP server that connects Claude Code with claude.ai conversations and Projects. Read conversations, search your history, and push context back to claude.ai Projects as knowledge documents.

## Why Use This?

### 1. Conversations are richer than documents

Let Claude Code read a conversation including the entire thought process + back-and-forth instead of just a copy/pasted final spec:

- Questions that were asked and clarified
- Alternatives that were considered and rejected
- Trade-offs that were discussed
- The reasoning behind each decision
- Failed approaches and why they didn't work

This helps Claude Code understand not just *what* to build but *why*, leading to better implementation choices.

### 2. No context window waste

Instead of re-explaining your project, domain, and constraints to Claude Code every session, it can read the conversation where you already explained everything. Your accumulated context is preserved.

### 3. Claude Desktop as your "context hub"

Instead of configuring many MCP servers in Claude Code (Confluence, Jira, Slack, browser extensions...), you can:

- Configure all integrations in **Claude Desktop**
- Have conversations that use those tools
- **Claude Code reads those conversations** — indirect access to all that context

This keeps Claude Code lightweight and fast, while Claude Desktop handles deep integrations.

### 4. Bidirectional sync with Projects

Push status summaries, TODO lists, and session logs from Claude Code back to claude.ai Projects. Your Claude Desktop conversations automatically have access to the latest project state.

### 5. Async workflow

Design and discuss in Claude Desktop during a meeting or brainstorm. Later, Claude Code picks up that conversation and implements it—no manual handoff needed. Push results back so the next Desktop session sees what was done.

### 6. Bridge your knowledge

Search past conversations where you solved similar problems. Your conversation history becomes a searchable knowledge base.

## Features

### Read (conversations)

- **list_conversations** - List recent conversations with names and timestamps
- **get_conversation** - Get full content of a specific conversation
- **search_conversations** - Search conversations by name/title
- **get_conversation_summary** - Get first/last messages for quick context

### Read/Write (Projects)

- **list_projects** - List all claude.ai Projects in your organization
- **list_project_docs** - List knowledge documents in a Project
- **get_project_doc** - Read a specific knowledge document
- **list_project_conversations** - List conversations within a Project
- **push_to_project** - Push arbitrary content as a knowledge document
- **push_session_summary** - Auto-generate and push a status summary (git state, recent changes)
- **push_todos** - Push a TODO list as a knowledge document

## Requirements

- Python 3.10+
- Chrome browser logged into claude.ai

## Installation

1. Clone this repository:

```bash
git clone https://github.com/ammardoosh/context-bridge.git
cd context-bridge
```

2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Add to your Claude Code MCP settings (`~/.claude.json`):

```json
{
  "mcpServers": {
    "context-bridge": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/context-bridge/server.py"]
    }
  }
}
```

For Claude Desktop, add to `~/Library/Application Support/Claude/claude_desktop_config.json` (macOS):

```json
{
  "mcpServers": {
    "context-bridge": {
      "command": "python3",
      "args": ["/path/to/context-bridge/server.py"]
    }
  }
}
```

## Project Mapping

To enable push features, map your repository to a claude.ai Project by adding an HTML comment to your `CLAUDE.md`:

```markdown
<!-- claude-project: My App Name -->
```

The server resolves the project name to a project ID on first use and caches it in `.claude-project-cache` (add this to `.gitignore`).

You can also set the project ID directly if you know it:

```markdown
<!-- claude-project-id: your-project-uuid -->
```

Multiple repositories can map to the same Project — documents are prefixed with the repo name to avoid collisions.

## Automation (Hooks)

Auto-push a status summary after each Claude Code session using the push CLI:

```bash
python -m context_bridge.push --auto
```

This generates a summary from your git state (branch, recent commits, modified files) and pushes it to the configured Project. A cooldown mechanism prevents excessive pushes.

To wire this into Claude Code's `SessionEnd` hook, add to `.claude/hooks.json`:

```json
{
  "hooks": {
    "SessionEnd": [
      {
        "command": "python -m context_bridge.push --auto",
        "timeout": 10000
      }
    ]
  }
}
```

## Usage

```python
# Read conversations
list_conversations(limit=10)
get_conversation("conversation-uuid")
search_conversations("project planning")

# Browse Projects
list_projects()
list_project_docs(project="My App")
get_project_doc(doc_id="doc-uuid")

# Push context back
push_to_project(content="# Design Notes\n...", doc_name="design-notes")
push_session_summary()
push_todos(todos=["Fix auth bug", "Add tests", "Update docs"])
```

## How It Works

The server reads Chrome's cookies to authenticate with claude.ai's API:

1. You must be logged into claude.ai in Chrome
2. Conversations from both Claude Desktop and claude.ai web are accessible
3. No API keys needed

## Limitations

- **Chrome only** - Requires Chrome (Safari/Firefox not supported)
- **Session expiry** - Re-login to Chrome when session expires

## License

MIT
