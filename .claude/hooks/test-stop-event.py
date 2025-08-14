#!/usr/bin/env python3
"""Test script to see what data the Stop event provides"""

import json
import sys
from datetime import datetime

# Log the raw input data
with open('/tmp/stop-event-test.log', 'a') as f:
    input_data = json.load(sys.stdin)
    f.write(f"\n=== Stop Event at {datetime.now().isoformat()} ===\n")
    f.write(json.dumps(input_data, indent=2))
    f.write("\n")
    
    # Try to extract useful fields
    f.write("\nExtracted fields:\n")
    f.write(f"- hook_event_name: {input_data.get('hook_event_name')}\n")
    f.write(f"- Fields available: {list(input_data.keys())}\n")

print("Stop event logged to /tmp/stop-event-test.log")