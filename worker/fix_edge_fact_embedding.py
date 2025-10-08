#!/usr/bin/env python3
"""
Fix edge fact_embedding to use Vectorf32 format for FalkorDB
"""

BULK_UTILS_FILE = '/opt/stacks/graphiti/graphiti_core/utils/bulk_utils.py'


def fix_edge_fact_embedding():
    with open(BULK_UTILS_FILE, 'r') as f:
        content = f.read()

    # Add import at the top of the file if not already there
    if 'from falkordb import Vectorf32' not in content:
        # Find the imports section and add Vectorf32 import
        import_line = 'from graphiti_core.nodes import EntityNode, EpisodicNode'
        if import_line in content:
            content = content.replace(
                import_line,
                import_line
                + '\n\ntry:\n    from falkordb import Vectorf32\nexcept ImportError:\n    Vectorf32 = None',
            )
            print('✅ Added Vectorf32 import')

    # Fix the edge_data dictionary to convert fact_embedding
    old_code = """        edge_data: dict[str, Any] = {
            'uuid': edge.uuid,
            'source_node_uuid': edge.source_node_uuid,
            'target_node_uuid': edge.target_node_uuid,
            'name': edge.name,
            'fact': edge.fact,
            'fact_embedding': edge.fact_embedding,
            'group_id': edge.group_id,
            'episodes': edge.episodes,
            'created_at': edge.created_at,
            'expired_at': edge.expired_at,
            'valid_at': edge.valid_at,
            'invalid_at': edge.invalid_at,
        }"""

    new_code = """        # Convert fact_embedding to Vectorf32 for FalkorDB compatibility
        fact_embedding = edge.fact_embedding
        if fact_embedding is not None and Vectorf32 is not None:
            if isinstance(fact_embedding, list):
                fact_embedding = Vectorf32(fact_embedding)
        
        edge_data: dict[str, Any] = {
            'uuid': edge.uuid,
            'source_node_uuid': edge.source_node_uuid,
            'target_node_uuid': edge.target_node_uuid,
            'name': edge.name,
            'fact': edge.fact,
            'fact_embedding': fact_embedding,
            'group_id': edge.group_id,
            'episodes': edge.episodes,
            'created_at': edge.created_at,
            'expired_at': edge.expired_at,
            'valid_at': edge.valid_at,
            'invalid_at': edge.invalid_at,
        }"""

    if old_code in content:
        content = content.replace(old_code, new_code)

        with open(BULK_UTILS_FILE, 'w') as f:
            f.write(content)

        print('✅ Fixed edge fact_embedding to use Vectorf32')
        print('   - Added conversion from list to Vectorf32 before query')
        print('   - Ensures FalkorDB receives proper vector type')
    else:
        print('❌ Could not find the exact code pattern to replace')
        print('   The code may have already been modified')


if __name__ == '__main__':
    fix_edge_fact_embedding()
