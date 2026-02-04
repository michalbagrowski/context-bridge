# Context Bridge

An MCP server that lets Claude Code read conversations from Claude Desktop and claude.ai.

## Why Use This?

### 1. Conversations are richer than documents

When Claude Code reads a conversation, it doesn't just get the final spec—it gets the **entire thought process**:

- Questions that were asked and clarified
- - Alternatives that were considered and rejected
  - - Trade-offs that were discussed
    - - The reasoning behind each decision
      - - Failed approaches and why they didn't work
       
        - This helps Claude Code understand not just *what* to build but *why*, leading to better implementation choices.
       
        - ### 2. No context window waste
       
        - Instead of re-explaining your project, domain, and constraints to Claude Code every session, it can read the conversation where you already explained everything. Your accumulated context is preserved.
       
        - ### 3. Claude Desktop as your "context hub"
       
        - Instead of configuring many MCP servers in Claude Code (Confluence, Jira, Slack, browser extensions...), you can:
       
        - - Configure all integrations in **Claude Desktop**
          - - Have conversations that use those tools
            - - **Claude Code reads those conversations** → indirect access to all that context
             
              - This keeps Claude Code lightweight and fast, while Claude Desktop handles deep integrations.
             
              - ### 4. Async workflow
             
              - Design and discuss in Claude Desktop during a meeting or brainstorm. Later, Claude Code picks up that conversation and implements it—no manual handoff needed.
             
              - ### 5. Artifacts and iterations included
             
              - Conversations often contain code snippets, structured outputs, and multiple iterations. Claude Code sees what was tried, what worked, and the final version—not just the end result.
             
              - ### 6. Bridge your knowledge
             
              - Search past conversations where you solved similar problems. Your conversation history becomes a searchable knowledge base.
             
              - ## Features
             
              - - **list_conversations** - List recent conversations with names and timestamps
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
                               git clone https://github.com/ammardoosh/context-bridge.git
                               cd context-bridge
                               ```

                               2. Install dependencies:
                              
                               3. ```bash
                                  pip install -r requirements.txt
                                  ```

                                  3. Add to your Claude Code MCP settings (`~/.claude.json`):
                                 
                                  4. ```json
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

                                     ### For Claude Desktop

                                     Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json` on macOS):

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

                                     ## Usage

                                     ```python
                                     # List recent conversations
                                     list_conversations(limit=10)

                                     # Get full conversation
                                     get_conversation("conversation-uuid")

                                     # Search by name
                                     search_conversations("project planning")

                                     # Get summary (first/last messages)
                                     get_conversation_summary("conversation-uuid")
                                     ```

                                     ## How It Works

                                     The server reads Chrome's cookies to authenticate with claude.ai's API:

                                     1. You must be logged into claude.ai in Chrome
                                     2. 2. Conversations from both Claude Desktop and claude.ai web are accessible
                                        3. 3. No API keys needed
                                          
                                           4. ## Limitations
                                          
                                           5. - **Read-only** - Only reads conversations (no writing/modifying)
                                              - - **Chrome only** - Requires Chrome (Safari/Firefox not supported)
                                                - - **Session expiry** - Re-login to Chrome when session expires
                                                 
                                                  - ## License
                                                 
                                                  - MIT
