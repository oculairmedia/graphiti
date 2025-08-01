#!/usr/bin/env python
"""
Script to analyze duplicate entities in the FalkorDB graph that might not be caught
by the deduplication script.
"""

import os
import re
from collections import defaultdict
import logging

# Set up environment for FalkorDB
os.environ['USE_FALKORDB'] = 'true'
os.environ['FALKORDB_HOST'] = os.getenv('FALKORDB_HOST', 'falkordb')
os.environ['FALKORDB_PORT'] = os.getenv('FALKORDB_PORT', '6379')

from graphiti_core import Graphiti

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def analyze_duplicates():
    """Analyze potential duplicate entities in the graph."""
    
    # Initialize Graphiti with FalkorDB
    graphiti = Graphiti(
        uri=os.getenv('FALKORDB_URI', 'redis://falkordb:6379'),
        llm_client=None,  # We don't need LLM for querying
        embedder=None     # We don't need embeddings for querying
    )

    # Query all entity names with their IDs and created dates
    query = '''
    MATCH (n:Entity)
    RETURN n.uuid AS id, n.name AS name, n.created_at AS created_at
    ORDER BY n.name
    '''

    logger.info("Querying all entities from the graph...")
    result = graphiti.driver.query(query)
    entities = [(row['id'], row['name'], row.get('created_at', '')) for row in result]
    logger.info(f"Found {len(entities)} total entities")

    # Different grouping strategies
    exact_groups = defaultdict(list)
    lower_groups = defaultdict(list)
    similar_groups = defaultdict(list)
    
    # Patterns for cleaning entity names
    file_extensions = re.compile(r'\.(ts|tsx|js|jsx|py|sh|log|md|json|yaml|yml)$', re.IGNORECASE)
    path_pattern = re.compile(r'^.*/([^/]+)$')
    
    for entity_id, name, created_at in entities:
        # Exact match
        exact_groups[name].append((entity_id, name, created_at))
        
        # Case-insensitive
        lower_groups[name.lower()].append((entity_id, name, created_at))
        
        # Similar names (for analysis)
        cleaned = name
        
        # Remove file extensions
        cleaned = file_extensions.sub('', cleaned)
        
        # Extract filename from path
        path_match = path_pattern.match(cleaned)
        if path_match:
            cleaned = path_match.group(1)
        
        # Remove quotes and extra spaces
        cleaned = cleaned.strip('"\'`').strip()
        
        # Only add to similar groups if it's different from original
        if cleaned and cleaned.lower() != name.lower():
            similar_groups[cleaned.lower()].append((entity_id, name, created_at))

    # Print analysis results
    print('\n' + '=' * 80)
    print('DUPLICATE ENTITY ANALYSIS')
    print('=' * 80)
    
    # Exact duplicates
    print('\n=== EXACT DUPLICATES ===')
    print('(Same name, multiple entities)\n')
    
    exact_dupes = 0
    for name, entries in sorted(exact_groups.items()):
        if len(entries) > 1:
            print(f'"{name}" appears {len(entries)} times:')
            for entity_id, _, created_at in entries[:5]:  # Show first 5
                print(f'  - ID: {entity_id} (created: {created_at[:19] if created_at else "unknown"})')
            if len(entries) > 5:
                print(f'  ... and {len(entries) - 5} more')
            print()
            exact_dupes += 1

    print(f'Total exact duplicate groups: {exact_dupes}')

    # Case variations
    print('\n\n=== CASE VARIATIONS ===')
    print('(Different capitalizations of the same name)\n')
    
    case_dupes = 0
    shown = 0
    for lower_name, entries in sorted(lower_groups.items()):
        unique_names = list(set(e[1] for e in entries))
        if len(unique_names) > 1:  # Different cases
            if shown < 20:  # Limit output
                print(f'Variations of "{lower_name}":')
                for name in unique_names[:5]:
                    count = sum(1 for e in entries if e[1] == name)
                    print(f'  - "{name}" ({count} occurrences)')
                if len(unique_names) > 5:
                    print(f'  ... and {len(unique_names) - 5} more variations')
                print()
                shown += 1
            case_dupes += 1

    if case_dupes > shown:
        print(f'... and {case_dupes - shown} more case-variant groups\n')
    
    print(f'Total case-variant groups: {case_dupes}')

    # Similar entities
    print('\n\n=== SIMILAR ENTITIES ===')
    print('(Potentially the same entity with different representations)\n')
    
    similar_dupes = 0
    shown = 0
    for cleaned, entries in sorted(similar_groups.items(), key=lambda x: -len(x[1])):
        if len(entries) > 1:
            if shown < 15:  # Limit output
                print(f'Similar to "{cleaned}":')
                unique_names = list(set(e[1] for e in entries))
                for name in unique_names[:5]:
                    print(f'  - "{name}"')
                if len(unique_names) > 5:
                    print(f'  ... and {len(unique_names) - 5} more')
                print()
                shown += 1
            similar_dupes += 1

    if similar_dupes > shown:
        print(f'... and {similar_dupes - shown} more similar groups\n')
    
    print(f'Total similar groups: {similar_dupes}')
    
    # Summary statistics
    print('\n\n=== SUMMARY ===')
    print(f'Total entities: {len(entities)}')
    print(f'Total unique names: {len(exact_groups)}')
    print(f'Exact duplicate groups: {exact_dupes}')
    print(f'Case-variant groups: {case_dupes}')
    print(f'Similar entity groups: {similar_dupes}')
    
    # Analysis of why duplicates might be missed
    print('\n\n=== WHY DUPLICATES MIGHT BE MISSED ===')
    print('The deduplication script uses embedding similarity with a threshold of 0.8.')
    print('Duplicates might be missed because:')
    print('1. Embedding similarity < 0.8 threshold (semantically different)')
    print('2. Different entity types or contexts')
    print('3. Significant timestamp differences')
    print('4. Special characters or formatting differences')
    print('\nConsider:')
    print('- Lowering the similarity threshold (currently 0.8)')
    print('- Adding exact name matching as a pre-filter')
    print('- Normalizing names before embedding comparison')


if __name__ == "__main__":
    analyze_duplicates()