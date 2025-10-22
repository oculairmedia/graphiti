#!/usr/bin/env python3
"""Debug version of ingestion hook"""

import json
import sys
import os

# Log everything for debugging
with open('/tmp/ingest-debug.log', 'a') as debug:
    debug.write("\n=== Ingestion Debug ===\n")
    
    # Read input
    input_data = json.load(sys.stdin)
    debug.write(f"Input: {json.dumps(input_data, indent=2)}\n")
    
    transcript_path = input_data.get("transcript_path", "")
    debug.write(f"Transcript path: {transcript_path}\n")
    
    if os.path.exists(transcript_path):
        debug.write("Transcript exists\n")
        
        # Read last few lines
        with open(transcript_path, 'r') as f:
            lines = f.readlines()
            debug.write(f"Total lines: {len(lines)}\n")
            
            # Get last 3 entries
            for i in range(max(0, len(lines)-3), len(lines)):
                entry = json.loads(lines[i])
                debug.write(f"Entry {i}: type={entry.get('type')}, ")
                if entry.get('type') == 'user':
                    debug.write(f"content={entry.get('content', '')[:50]}...\n")
                elif entry.get('type') == 'assistant':
                    content = entry.get('content', '')
                    if isinstance(content, str):
                        debug.write(f"content={content[:50]}...\n")
                    else:
                        debug.write(f"content=<structured>\n")
    else:
        debug.write(f"Transcript NOT found at {transcript_path}\n")