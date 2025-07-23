#!/usr/bin/env python3
"""
Temporary fix for FalkorDB compatibility by patching the helpers.py file.
This removes the Neo4j-specific CYPHER runtime hints.
"""

import os
import shutil

helpers_path = "/opt/stacks/graphiti/graphiti_core/helpers.py"
backup_path = "/opt/stacks/graphiti/graphiti_core/helpers.py.backup"

# Create backup
if not os.path.exists(backup_path):
    shutil.copy(helpers_path, backup_path)
    print(f"✅ Created backup at {backup_path}")

# Read the file
with open(helpers_path, 'r') as f:
    content = f.read()

# Replace the RUNTIME_QUERY line
original_line = "RUNTIME_QUERY: LiteralString = (\n    'CYPHER runtime = parallel parallelRuntimeSupport=all\\n' if USE_PARALLEL_RUNTIME else ''\n)"
new_line = "RUNTIME_QUERY: LiteralString = ''"  # Always empty for FalkorDB

if original_line in content:
    content = content.replace(original_line, new_line)
    print("✅ Found and replaced RUNTIME_QUERY definition")
else:
    # Try a simpler pattern
    import re
    pattern = r"RUNTIME_QUERY.*?=.*?\n.*?\n\)"
    replacement = "RUNTIME_QUERY: LiteralString = ''"
    content = re.sub(pattern, replacement, content, flags=re.DOTALL)
    print("✅ Replaced RUNTIME_QUERY using regex")

# Write the modified content back
with open(helpers_path, 'w') as f:
    f.write(content)

print("✅ Applied FalkorDB compatibility fix to helpers.py")
print("\nTo restore the original file, run:")
print(f"  cp {backup_path} {helpers_path}")