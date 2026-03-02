#!/bin/bash
# PreToolUse hook for Bash permission gating via Telegram bot.
# Reads tool info from stdin, writes request to temp file,
# polls for response from the bot process.

INPUT=$(cat)
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // empty')

# Only gate Bash commands
if [ "$TOOL_NAME" != "Bash" ]; then
  exit 0
fi

GATE_ID="${PERM_GATE_ID:-}"
if [ -z "$GATE_ID" ]; then
  exit 0  # No gate ID, allow
fi

REQ_FILE="/tmp/claude_perm_${GATE_ID}.req"
RESP_FILE="/tmp/claude_perm_${GATE_ID}.resp"

# Write request (tool_input contains the command)
echo "$INPUT" > "$REQ_FILE"

# Poll for response (max 120s)
for i in $(seq 1 240); do
  if [ -f "$RESP_FILE" ]; then
    DECISION=$(cat "$RESP_FILE")
    rm -f "$REQ_FILE" "$RESP_FILE"
    if [ "$DECISION" = "allow" ]; then
      exit 0
    else
      jq -n '{
        hookSpecificOutput: {
          hookEventName: "PreToolUse",
          permissionDecision: "deny",
          permissionDecisionReason: "User denied via Telegram"
        }
      }'
      exit 0
    fi
  fi
  sleep 0.5
done

# Timeout
rm -f "$REQ_FILE"
jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "deny",
    permissionDecisionReason: "Permission request timed out"
  }
}'
exit 0
