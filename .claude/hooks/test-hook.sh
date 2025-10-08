#!/bin/bash

# Test script for Graphiti hooks

echo "Testing Graphiti Hooks for Claude Code"
echo "======================================="
echo ""

# Test 1: UserPromptSubmit with knowledge question
echo "Test 1: UserPromptSubmit with knowledge question"
echo '{"hook_event_name":"UserPromptSubmit","prompt":"What do you know about GraphCanvas component?","session_id":"test123","transcript_path":"/tmp/test.jsonl","cwd":"/opt/stacks/graphiti"}' | \
  python3 graphiti-retrieval.py
echo ""

# Test 2: UserPromptSubmit with search request
echo "Test 2: UserPromptSubmit with explicit search"
echo '{"hook_event_name":"UserPromptSubmit","prompt":"Search the knowledge graph for WebSocket implementation","session_id":"test123","transcript_path":"/tmp/test.jsonl","cwd":"/opt/stacks/graphiti"}' | \
  python3 graphiti-retrieval.py
echo ""

# Test 3: PreToolUse for Task tool
echo "Test 3: PreToolUse for Task tool"
echo '{"hook_event_name":"PreToolUse","tool_name":"Task","tool_input":{"description":"Research WebSocket","prompt":"Find information about WebSocket real-time updates"},"session_id":"test123","transcript_path":"/tmp/test.jsonl","cwd":"/opt/stacks/graphiti"}' | \
  python3 graphiti-retrieval.py
echo ""

# Test 4: SessionStart for resume
echo "Test 4: SessionStart for resume"
echo '{"hook_event_name":"SessionStart","source":"resume","session_id":"test123","transcript_path":"/tmp/test.jsonl","cwd":"/opt/stacks/graphiti"}' | \
  python3 graphiti-retrieval.py
echo ""

# Test 5: Bash hook with keywords
echo "Test 5: Bash hook with Graphiti keywords"
echo '{"hook_event_name":"UserPromptSubmit","prompt":"What did we discuss earlier about the knowledge graph?","session_id":"test123","transcript_path":"/tmp/test.jsonl","cwd":"/opt/stacks/graphiti"}' | \
  bash graphiti-search.sh
echo ""

echo "Tests completed!"