#!/bin/bash

echo "Testing Claude Code Hooks"
echo "========================"
echo ""

# Test 1: UserPromptSubmit hook with knowledge keywords
echo "Test 1: UserPromptSubmit with knowledge keywords"
echo "Input:"
cat << 'EOF' | tee /tmp/test-input.json
{
  "hook_event_name": "UserPromptSubmit",
  "prompt": "What do we know from the knowledge graph about WebSocket?",
  "session_id": "test123",
  "transcript_path": "/tmp/test.jsonl",
  "cwd": "/opt/stacks/graphiti"
}
EOF

echo -e "\nOutput:"
cat /tmp/test-input.json | python3 /opt/stacks/graphiti/.claude/hooks/graphiti-context.py
echo -e "\n---\n"

# Test 2: PreToolUse logging for Bash
echo "Test 2: PreToolUse logging for Bash"
echo "Input:"
cat << 'EOF' | tee /tmp/test-input.json
{
  "hook_event_name": "PreToolUse",
  "tool_name": "Bash",
  "tool_input": {
    "command": "ls -la",
    "description": "List files"
  },
  "session_id": "test123"
}
EOF

echo -e "\nOutput:"
cat /tmp/test-input.json | bash /opt/stacks/graphiti/.claude/hooks/log-tools.sh
echo "Check log file:"
tail -n 2 ~/.claude/tool-usage.log
echo -e "\n---\n"

# Test 3: PostToolUse logging
echo "Test 3: PostToolUse logging"
echo "Input:"
cat << 'EOF' | tee /tmp/test-input.json
{
  "hook_event_name": "PostToolUse",
  "tool_name": "Write",
  "tool_input": {
    "file_path": "/tmp/test.txt",
    "content": "test"
  },
  "tool_response": {
    "success": true
  },
  "session_id": "test123"
}
EOF

echo -e "\nOutput:"
cat /tmp/test-input.json | bash /opt/stacks/graphiti/.claude/hooks/log-tools.sh
echo "Check log file:"
tail -n 1 ~/.claude/tool-usage.log
echo -e "\n---\n"

echo "Tests completed!"
echo "Log file contents:"
echo ""
tail -n 10 ~/.claude/tool-usage.log