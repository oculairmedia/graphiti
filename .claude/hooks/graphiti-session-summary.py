#!/usr/bin/env python3
"""
Graphiti Session Summary Hook for Claude Code

Lightweight session-based ingestion:
- Buffers events during session (no network calls)
- Sends single summary episode on session end
- Tracks files modified, tools used, user requests
"""

import json
import os
import sys
import hashlib
from datetime import datetime
from pathlib import Path

# Configuration
GRAPHITI_API_URL = os.environ.get("GRAPHITI_API_URL", "http://192.168.50.90:8003")
ENABLED = os.environ.get("GRAPHITI_AUTO_COLLECT", "true").lower() != "false"
STATE_FILE = Path("/tmp/claude-graphiti-session.json")
MAX_SUMMARY_LENGTH = 3000

def get_group_id():
    """Generate group_id from project directory."""
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd())
    project_name = Path(project_dir).name
    return f"claude-{project_name}"

def load_state():
    """Load session state from temp file."""
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except:
            pass
    return {
        "start_time": datetime.now().isoformat(),
        "user_requests": [],
        "files_modified": [],
        "files_read": [],
        "tools_used": {},
        "git_branch": None,
    }

def save_state(state):
    """Save session state to temp file."""
    STATE_FILE.write_text(json.dumps(state, indent=2))

def clear_state():
    """Clear session state."""
    if STATE_FILE.exists():
        STATE_FILE.unlink()

def extract_file_from_input(tool_input):
    """Extract file path from tool input."""
    if not tool_input:
        return None
    if isinstance(tool_input, str):
        try:
            tool_input = json.loads(tool_input)
        except:
            return None
    for key in ["file_path", "filePath", "path", "target_filepath"]:
        if key in tool_input:
            return tool_input[key]
    return None

def build_summary(state):
    """Build a concise session summary."""
    parts = []
    start = state.get("start_time", "unknown")
    parts.append(f"Session: {start[:19]}")

    if state.get("git_branch"):
        parts.append(f"Branch: {state['git_branch']}")

    requests = state.get("user_requests", [])
    if requests:
        unique = list(dict.fromkeys(requests))[-5:]
        parts.append(f"Requests: {'; '.join(r[:100] for r in unique)}")

    files_mod = state.get("files_modified", [])
    if files_mod:
        unique_files = list(dict.fromkeys(files_mod))[:10]
        parts.append(f"Files modified ({len(files_mod)}): {', '.join(Path(f).name for f in unique_files)}")

    tools = state.get("tools_used", {})
    if tools:
        tool_summary = ", ".join(f"{t}:{c}" for t, c in sorted(tools.items(), key=lambda x: -x[1])[:8])
        parts.append(f"Tools: {tool_summary}")

    return "\n".join(parts)

def send_summary(state):
    """Send session summary to Graphiti."""
    import urllib.request

    summary = build_summary(state)
    if len(summary) < 50:
        return

    content_hash = hashlib.md5(summary.encode()).hexdigest()
    episode_uuid = f"{content_hash[:8]}-{content_hash[8:12]}-{content_hash[12:16]}-{content_hash[16:20]}-{content_hash[20:32]}"

    payload = {
        "group_id": get_group_id(),
        "messages": [{
            "content": summary[:MAX_SUMMARY_LENGTH],
            "uuid": episode_uuid,
            "name": f"Claude session: {state.get('git_branch', 'main')}",
            "role_type": "system",
            "role": "session-summary",
            "timestamp": datetime.now().isoformat(),
            "source_description": "claude-code-session"
        }]
    }

    try:
        req = urllib.request.Request(
            f"{GRAPHITI_API_URL}/messages",
            data=json.dumps(payload).encode(),
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status in (200, 201, 202):
                print(f"[Graphiti] Session summary sent", file=sys.stderr)
    except Exception as e:
        print(f"[Graphiti] Failed: {e}", file=sys.stderr)

def handle_user_prompt(hook_input):
    """Capture user request."""
    state = load_state()
    message = hook_input.get("message", "")
    if isinstance(message, dict):
        message = message.get("content", "")
    if message and len(message) > 10:
        state["user_requests"].append(message[:200])
        state["user_requests"] = state["user_requests"][-10:]
    save_state(state)

def handle_tool_use(hook_input):
    """Track tools and files."""
    state = load_state()
    tool_name = hook_input.get("tool_name", "")
    tool_input = hook_input.get("tool_input", {})

    if tool_name:
        state["tools_used"][tool_name] = state["tools_used"].get(tool_name, 0) + 1

    file_path = extract_file_from_input(tool_input)
    if file_path:
        if tool_name in ("Write", "Edit", "NotebookEdit"):
            if file_path not in state["files_modified"]:
                state["files_modified"].append(file_path)
        elif tool_name == "Read":
            if file_path not in state["files_read"]:
                state["files_read"].append(file_path)
    save_state(state)

def handle_stop():
    """Send summary and clear state."""
    state = load_state()
    if state.get("tools_used") or state.get("user_requests"):
        send_summary(state)
    clear_state()

def main():
    if not ENABLED:
        return

    try:
        hook_input = json.load(sys.stdin)
    except:
        hook_input = {}

    hook_event = os.environ.get("CLAUDE_HOOK_EVENT", "")

    if "UserPromptSubmit" in hook_event:
        handle_user_prompt(hook_input)
    elif "Stop" in hook_event:
        handle_stop()
    elif "ToolUse" in hook_event:
        handle_tool_use(hook_input)

if __name__ == "__main__":
    main()
