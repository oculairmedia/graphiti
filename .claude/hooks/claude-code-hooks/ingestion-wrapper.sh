#!/bin/bash
date >> /tmp/stop-hook-fired.log
echo "Stop hook fired with args: $@" >> /tmp/stop-hook-fired.log
echo "CLAUDE_PROJECT_DIR: $CLAUDE_PROJECT_DIR" >> /tmp/stop-hook-fired.log
echo "About to run Python script..." >> /tmp/stop-hook-fired.log
# Capture stdin for debugging
tee /tmp/stop-hook-stdin.json | python3 /opt/stacks/graphiti/.claude/hooks/graphiti-ingest-v3.py >> /tmp/stop-hook-fired.log 2>&1
echo "Python script exit code: $?" >> /tmp/stop-hook-fired.log
