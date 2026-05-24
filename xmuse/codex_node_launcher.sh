#!/bin/bash
set -euo pipefail

cd /home/iiyatu/projects/python/memoryOS

LOOP_ROOT="${XMUSE_LOOP_ROOT:-xmuse}"
NODE_TYPE="${1:?usage: xmuse/codex_node_launcher.sh <master|slave|plan|execute|review> <prompt-file>}"
PROMPT_FILE="${2:?usage: xmuse/codex_node_launcher.sh <master|slave|plan|execute|review> <prompt-file>}"
MODEL="${XMUSE_CODEX_MODEL:-gpt-5.5}"
EFFORT="${XMUSE_CODEX_REASONING_EFFORT:-xhigh}"

case "$NODE_TYPE" in
    master|slave|plan|execute|review)
        ;;
    *)
        echo "unsupported xmuse node type: $NODE_TYPE" >&2
        exit 2
        ;;
esac

if [ ! -f "$PROMPT_FILE" ]; then
    echo "missing prompt file: $PROMPT_FILE" >&2
    exit 2
fi

echo "===== xmuse_node node=$NODE_TYPE prompt=$PROMPT_FILE loop=$LOOP_ROOT $(date -Iseconds) ====="
codex exec --yolo -m "$MODEL" -c model_reasoning_effort="$EFFORT" -c approval_policy=never "$(< "$PROMPT_FILE")"
