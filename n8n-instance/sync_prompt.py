#!/usr/bin/env python3
"""Inject prompts/system_prompt.md into the AI Agent node of the exported workflow JSON."""
import json
import sys
from pathlib import Path

PROMPT_PATH = Path(__file__).parent / "prompts" / "system_prompt.md"
DEFAULT_WORKFLOW_PATH = Path.home() / "windows" / "n8n" / "main-workflow.json"
AGENT_NODE_NAME = "AI Agent"


def main() -> int:
    workflow_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_WORKFLOW_PATH

    if not PROMPT_PATH.is_file():
        print(f"ERROR: prompt file not found: {PROMPT_PATH}", file=sys.stderr)
        return 1
    if not workflow_path.is_file():
        print(f"ERROR: workflow file not found: {workflow_path}", file=sys.stderr)
        return 1

    prompt = PROMPT_PATH.read_text(encoding="utf-8").rstrip("\n")
    workflow = json.loads(workflow_path.read_text(encoding="utf-8"))

    agent = next(
        (node for node in workflow.get("nodes", []) if node.get("name") == AGENT_NODE_NAME),
        None,
    )
    if agent is None:
        print(
            f"ERROR: no node named {AGENT_NODE_NAME!r} in {workflow_path}", file=sys.stderr
        )
        return 1

    options = agent.setdefault("parameters", {}).setdefault("options", {})
    if options.get("systemMessage") == prompt:
        print(f"Already in sync: {workflow_path} ({len(prompt)} characters)")
        return 0

    options["systemMessage"] = prompt
    workflow_path.write_text(
        json.dumps(workflow, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    print(f"Updated {AGENT_NODE_NAME} system message in {workflow_path} ({len(prompt)} characters)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
