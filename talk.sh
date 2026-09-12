#!/bin/sh
# Run this ON Rocky, from a shell on the board itself.
# From the laptop, use chat.sh instead; it opens a terminal here and runs this.
set -eu

ROCKY_DIR=${ROCKY_DIR:-/home/arduino/rocky-bench}
ROCKY_VENV=${ROCKY_VENV:-/home/arduino/rocky-venv}
ROCKY_BACKEND=${ROCKY_BACKEND:-claude}
ROCKY_MODEL=${ROCKY_MODEL:-qwen2.5:0.5b}
ROCKY_CLAUDE_MODEL=${ROCKY_CLAUDE_MODEL:-claude-haiku-4-5}

# The API key is not in the environment of a non-interactive shell.
if [ -f "$HOME/.rocky-env" ]; then
  set -a
  . "$HOME/.rocky-env"
  set +a
fi

cd "$ROCKY_DIR"

case "$ROCKY_BACKEND" in
  claude)
    if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
      echo "talk.sh: no ANTHROPIC_API_KEY. Put it in ~/.rocky-env, or run" >&2
      echo "         ROCKY_BACKEND=ollama talk.sh to use the local model." >&2
      exit 1
    fi
    exec "$ROCKY_VENV/bin/python" rocky.py --claude "$ROCKY_CLAUDE_MODEL"
    ;;
  ollama) exec python3 rocky.py --model "$ROCKY_MODEL" ;;
  *)
    echo "talk.sh: ROCKY_BACKEND must be 'claude' or 'ollama', got '$ROCKY_BACKEND'" >&2
    exit 2
    ;;
esac
