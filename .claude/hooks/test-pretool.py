#!/usr/bin/env python3
import json
import sys

try:
    input_data = json.load(sys.stdin)
    if input_data.get("hook_event_name") == "PreToolUse":
        tool_name = input_data.get("tool_name", "unknown")
        print(f"<!-- PRETOOL HOOK WORKING: About to use {tool_name} -->")
except:
    pass
sys.exit(0)