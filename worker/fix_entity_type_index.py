#!/usr/bin/env python3
"""
Fix the entity_type_id index out of range error in node_operations.py
"""

import re

NODE_OPS_FILE = '/opt/stacks/graphiti/graphiti_core/utils/maintenance/node_operations.py'


def fix_entity_type_index():
    with open(NODE_OPS_FILE, 'r') as f:
        content = f.read()

    # Find and replace the problematic code (around line 333)
    old_code = """    extracted_nodes = []
    for extracted_entity in filtered_extracted_entities:
        entity_type_name = entity_types_context[extracted_entity.entity_type_id].get(
            'entity_type_name'
        )"""

    new_code = """    extracted_nodes = []
    for extracted_entity in filtered_extracted_entities:
        # Defensive check for entity_type_id
        entity_type_id = extracted_entity.entity_type_id
        if entity_type_id < 0 or entity_type_id >= len(entity_types_context):
            logger.warning(
                f"Invalid entity_type_id {entity_type_id} for entity '{extracted_entity.name}'. "
                f"Valid range: 0-{len(entity_types_context)-1}. Defaulting to 0 (Entity)."
            )
            entity_type_id = 0
        
        entity_type_name = entity_types_context[entity_type_id].get(
            'entity_type_name'
        )"""

    if old_code in content:
        content = content.replace(old_code, new_code)

        with open(NODE_OPS_FILE, 'w') as f:
            f.write(content)

        print('✅ Fixed entity_type_id index out of range issue')
        print('   - Added defensive check for entity_type_id bounds')
        print('   - Invalid IDs will default to 0 (Entity type)')
    else:
        print('❌ Could not find the exact code pattern to replace')
        print('   The code may have already been modified')


if __name__ == '__main__':
    fix_entity_type_index()
