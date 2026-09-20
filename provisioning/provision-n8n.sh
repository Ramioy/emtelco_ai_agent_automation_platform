#!/bin/sh
# Imports the two credentials and the agent workflow, then publishes it. Runs on every boot and
# only creates what is missing, so restarts and already-provisioned instances are no-ops.
set -e

WORKFLOW_FILE="/workflows/agente-retail-electronica.json"
WORKFLOW_ID="drK12CNSD8aZJyYl"
TOOLS_CREDENTIAL_ID="ToolsApiKey00001"
DEEPSEEK_CREDENTIAL_ID="KNq4cJ0ct3cSwa6L"
WORK_DIR="/tmp/provisioning"

log() {
  echo "[provision] $*"
}

if [ -z "${DEEPSEEK_API_KEY}" ]; then
  echo ""
  echo "================================================================================"
  echo " DEEPSEEK_API_KEY is empty, so the agent would have no language model."
  echo ""
  echo " Fix it in the .env file next to docker-compose.yml:"
  echo ""
  echo "     DEEPSEEK_API_KEY=sk-your-key-here"
  echo ""
  echo " If you have no .env yet:  cp .env.example .env"
  echo " Then:                     docker compose up -d"
  echo "================================================================================"
  echo ""
  exit 1
fi

mkdir -p "$WORK_DIR"
rm -f "$WORK_DIR"/*.json

# --- credentials ---------------------------------------------------------------------------
# The environment file is the source of truth for both keys, so a stored credential whose value
# has drifted from it gets rewritten. Skipping that would strand a corrected key: the credential
# would keep the value it was first provisioned with and every call would fail authentication
# with no hint that the environment file was already right.
n8n export:credentials --decrypted --all --output="$WORK_DIR/existing-credentials.json" >/dev/null 2>&1 || true

# Prints "missing" when no credential carries this id, "current" when its stored secret already
# equals the expected one, and "stale" otherwise.
credential_state() {
  node -e '
    const fs = require("node:fs");
    const [file, id, field, expected] = process.argv.slice(1);
    let stored;
    try {
      stored = JSON.parse(fs.readFileSync(file, "utf8")).find((c) => c.id === id);
    } catch {}
    if (!stored) process.stdout.write("missing");
    else process.stdout.write(stored?.data?.[field] === expected ? "current" : "stale");
  ' "$WORK_DIR/existing-credentials.json" "$1" "$2" "$3"
}

write_credential_file() {
  node -e '
    const fs = require("node:fs");
    const [file, id, name, type, field, value] = process.argv.slice(1);
    const data = field === "value" ? { name: "X-API-Key", value } : { apiKey: value };
    fs.writeFileSync(file, JSON.stringify([{ id, name, type, data }]));
  ' "$@"
}

sync_credential() {
  local id="$1" name="$2" type="$3" field="$4" value="$5" file="$6"
  case "$(credential_state "$id" "$field" "$value")" in
    current)
      log "credential '$name' already matches the environment file"
      return
      ;;
    stale)
      log "credential '$name' differs from the environment file, updating it"
      ;;
    *)
      log "creating credential '$name'"
      ;;
  esac
  write_credential_file "$file" "$id" "$name" "$type" "$field" "$value"
  n8n import:credentials --input="$file"
}

sync_credential "$TOOLS_CREDENTIAL_ID" "Tools API Key" "httpHeaderAuth" "value" \
  "$TOOLS_API_KEY" "$WORK_DIR/tools-credential.json"

sync_credential "$DEEPSEEK_CREDENTIAL_ID" "DeepSeek account" "deepSeekApi" "apiKey" \
  "$DEEPSEEK_API_KEY" "$WORK_DIR/deepseek-credential.json"

rm -f "$WORK_DIR"/*.json

# --- workflow ------------------------------------------------------------------------------
# The export keeps its id, so a re-import would update rather than duplicate; it is skipped
# anyway so that edits made in the n8n editor survive a restart.
if n8n list:workflow --onlyId 2>/dev/null | grep -qx "$WORKFLOW_ID"; then
  log "workflow already imported"
else
  log "importing workflow"
  n8n import:workflow --input="$WORKFLOW_FILE"
fi

if n8n list:workflow --active=true --onlyId 2>/dev/null | grep -qx "$WORKFLOW_ID"; then
  log "workflow already published"
else
  log "publishing workflow"
  n8n publish:workflow --id="$WORKFLOW_ID"
fi

log "done"
