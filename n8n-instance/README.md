# n8n instance

- `data/` is the bind-mounted n8n home (SQLite database, encryption key, credentials). Not
  version-controlled.
- `prompts/system_prompt.md` is the source of truth for the agent's system message.
- `sync_prompt.py` copies that file into the exported workflow JSON.

## Editing the agent's system prompt

The running agent reads its system message from the `AI Agent` node's own `systemMessage`
parameter; there is no lookup at runtime. The markdown file exists so the prompt is reviewable
in version control with readable diffs instead of being buried in a JSON string, and the script
is what keeps the two identical.

1. Edit `prompts/system_prompt.md`.
2. Run the sync script from this directory:

   ```
   python3 sync_prompt.py [path/to/main-workflow.json]
   ```

   Without an argument it writes to `~/windows/n8n/main-workflow.json`. It rewrites only the
   `AI Agent` node's `systemMessage`, leaves the rest of the JSON untouched, is safe to run
   twice, and exits with an error if either the prompt file or the node is missing.

3. Load the updated JSON into n8n, either by importing it in the editor (Workflows, Import from
   file) or from the command line:

   ```
   docker compose exec n8n n8n import:workflow --input=/path/inside/container/main-workflow.json
   docker compose exec n8n n8n publish:workflow --id=<workflow id>
   docker compose restart n8n
   ```

   Keeping the `id` field in the JSON is what makes the import update the existing workflow
   instead of creating a duplicate.

Never edit the system message directly in the n8n editor: the next sync run overwrites it.
