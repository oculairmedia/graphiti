#!/usr/bin/env python3
"""
Find where "CYPHER params" is coming from in the codebase.
"""

import os
import re

def search_for_cypher_params(directory):
    """Search for files containing 'CYPHER params' or similar patterns."""
    patterns = [
        r'CYPHER\s+params',
        r'"CYPHER\s+params"',
        r"'CYPHER\s+params'",
        r'CYPHER.*params.*=',
        r'params.*CYPHER'
    ]
    
    results = []
    
    for root, dirs, files in os.walk(directory):
        # Skip __pycache__ directories
        if '__pycache__' in root:
            continue
            
        for file in files:
            if file.endswith('.py'):
                filepath = os.path.join(root, file)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        content = f.read()
                        for i, line in enumerate(content.splitlines(), 1):
                            for pattern in patterns:
                                if re.search(pattern, line, re.IGNORECASE):
                                    results.append((filepath, i, line.strip()))
                except Exception as e:
                    print(f"Error reading {filepath}: {e}")
    
    return results

# Search in graphiti_core directory
print("Searching for 'CYPHER params' in graphiti_core...")
results = search_for_cypher_params('/opt/stacks/graphiti/graphiti_core')

if results:
    print(f"\nFound {len(results)} occurrences:")
    for filepath, line_num, line in results:
        print(f"\n{filepath}:{line_num}")
        print(f"  {line}")
else:
    print("\nNo occurrences of 'CYPHER params' found in the code.")
    
# Also check if there's any query construction that might produce this
print("\n\nSearching for query construction patterns...")
query_patterns = [
    r'query\s*=.*CYPHER',
    r'CYPHER.*\+.*params',
    r'f.*CYPHER.*params',
    r'\.format.*CYPHER.*params'
]

for root, dirs, files in os.walk('/opt/stacks/graphiti/graphiti_core'):
    if '__pycache__' in root:
        continue
        
    for file in files:
        if file.endswith('.py'):
            filepath = os.path.join(root, file)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    for i, line in enumerate(content.splitlines(), 1):
                        for pattern in query_patterns:
                            if re.search(pattern, line, re.IGNORECASE):
                                print(f"\n{filepath}:{i}")
                                print(f"  {line.strip()}")
            except Exception as e:
                pass