# n8n instance

- `workflows/agente-retail-electronica.json` is the workflow export. `docker compose up`
  imports and publishes it automatically on a fresh instance.
- `prompts/system_prompt.md` is the source of truth for the agent's system message.
- `sync_prompt.py` copies that file into the exported workflow JSON.

n8n's own state (SQLite database, encryption key, credentials) lives on the `n8n-data` Docker
volume, not in this directory.

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
   docker compose cp workflows/agente-retail-electronica.json n8n:/tmp/workflow.json
   docker compose exec n8n n8n import:workflow --input=/tmp/workflow.json
   docker compose exec n8n n8n publish:workflow --id=drK12CNSD8aZJyYl
   docker compose restart n8n
   ```

   Keeping the `id` field in the JSON is what makes the import update the existing workflow
   instead of creating a duplicate. The restart is what re-registers the production webhook;
   n8n says so itself when publishing. Automatic provisioning skips the import when the
   workflow is already there, so it never undoes this.

Never edit the system message directly in the n8n editor: the next sync run overwrites it.
