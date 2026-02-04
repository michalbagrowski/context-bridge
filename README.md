# Claude Desktop Reader MCP Server

An MCP (Model Context Protocol) server that allows Claude Code to access and read conversations from Claude Desktop and claude.ai.

## Features

- **list_conversations** - List recent conversations with names and timestamps
- - **get_conversation** - Get full content of a specific conversation
  - - **search_conversations** - Search conversations by name/title
    - - **get_conversation_summary** - Get first/last messages for quick context
     
      - ## Requirements
     
      - - Python 3.10+
        - - Chrome browser logged into claude.ai
         
          - ## Installation
         
          - ### For Claude Code
         
          - 1. Clone this repository:
            2. ```bash
               git clone https://github.com/ammardoosh/claude-desktop-reader-mcp.git
               cd claude-desktop-reader-mcp
               ```

               2. Install dependencies:
               3. ```bash
                  pip install -r requirements.txt
                  ```

                  3. Add to your Claude Code MCP settings (`~/.claude.json`):
                  4. ```json
                     {
                       "mcpServers": {
                         "claude-desktop-reader": {
                           "type": "stdio",
                           "command": "python3",
                           "args": ["/path/to/claude-desktop-reader-mcp/server.py"]
                         }
                       }
                     }
                     ```

                     ### For Claude Desktop

                     Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

                     ```json
                     {
                       "mcpServers": {
                         "claude-desktop-reader": {
                           "command": "python3",
                           "args": ["/path/to/claude-desktop-reader-mcp/server.py"]
                         }
                       }
                     }
                     ```

                     ## Usage

                     Once installed, the tools are available automatically in Claude Code or Claude Desktop:

                     ```
                     # List your recent Claude conversations
                     list_conversations(limit=10)

                     # Get a specific conversation by ID
                     get_conversation("conversation-uuid")

                     # Search by name
                     search_conversations("project planning")

                     # Get a summary (first/last messages)
                     get_conversation_summary("conversation-uuid")
                     ```

                     ## How It Works

                     The server reads Chrome's cookies to authenticate with claude.ai's API. This means:

                     1. You must be logged into claude.ai in Chrome
                     2. 2. Conversations from both Claude Desktop and claude.ai web are accessible
                        3. 3. No API keys or manual authentication needed
                          
                           4. ## Limitations
                          
                           5. - **Read-only** - Only reads conversations (no writing/modifying)
                              - - **Chrome only** - Requires Chrome browser (Safari/Firefox not supported)
                                - - **Session expiry** - Session cookie expires periodically (re-login to Chrome when needed)
                                 
                                  - ## License
                                 
                                  - MIT
