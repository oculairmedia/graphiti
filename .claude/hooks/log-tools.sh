#!/bin/bash

# Simple logging hook for Claude Code tool usage
# Logs all tool usage to a file for tracking

LOG_FILE="$HOME/.claude/tool-usage.log"

# Read JSON from stdin
input=$(cat)

# Extract relevant fields
hook_event=$(echo "$input" | jq -r '.hook_event_name // ""')
tool_name=$(echo "$input" | jq -r '.tool_name // ""')
timestamp=$(date '+%Y-%m-%d %H:%M:%S')

# Log based on event type
case "$hook_event" in
    "PreToolUse")
        # Log tool that's about to be used
        echo "[$timestamp] PRE  $tool_name" >> "$LOG_FILE"
        
        # For Bash commands, log the actual command
        if [ "$tool_name" = "Bash" ]; then
            command=$(echo "$input" | jq -r '.tool_input.command // ""')
            echo "[$timestamp]      Command: $command" >> "$LOG_FILE"
        fi
        
        # For file operations, log the file path
        if [[ "$tool_name" =~ ^(Read|Write|Edit|MultiEdit)$ ]]; then
            file_path=$(echo "$input" | jq -r '.tool_input.file_path // ""')
            echo "[$timestamp]      File: $file_path" >> "$LOG_FILE"
        fi
        ;;
        
    "PostToolUse")
        # Log tool completion
        success=$(echo "$input" | jq -r '.tool_response.success // "unknown"')
        echo "[$timestamp] POST $tool_name (success: $success)" >> "$LOG_FILE"
        ;;
        
    "UserPromptSubmit")
        # Log user prompts
        prompt=$(echo "$input" | jq -r '.prompt // ""' | head -c 100)
        echo "[$timestamp] PROMPT: $prompt..." >> "$LOG_FILE"
        ;;
esac

# Always exit successfully
exit 0