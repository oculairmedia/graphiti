#!/usr/bin/env python3
"""
Fix the dedupe_extracted_nodes import errors in worker.py
"""

import re

WORKER_FILE = '/opt/stacks/graphiti/graphiti_core/ingestion/worker.py'


def fix_worker_file():
    with open(WORKER_FILE, 'r') as f:
        content = f.read()

    # Fix 1: Change import from dedupe_extracted_nodes to dedupe_node_list (both occurrences)
    content = content.replace(
        'from graphiti_core.utils.maintenance.node_operations import dedupe_extracted_nodes',
        'from graphiti_core.utils.maintenance.node_operations import dedupe_node_list',
    )

    # Fix 2: Change function call in background dedup (around line 450)
    # Pattern: deduped_entities, uuid_map = await dedupe_extracted_nodes(
    #             llm_client=self.graphiti.llm_client,
    #             embedder=self.graphiti.embedder,
    #             extracted_nodes=entities,
    #             threshold=similarity_threshold
    #         )

    pattern1 = r"""similarity_threshold = float\(os\.getenv\('DEDUP_SIMILARITY_THRESHOLD', '0\.6'\)\)
            
            deduped_entities, uuid_map = await dedupe_extracted_nodes\(
                llm_client=self\.graphiti\.llm_client,
                embedder=self\.graphiti\.embedder,
                extracted_nodes=entities,
                threshold=similarity_threshold
            \)"""

    replacement1 = """deduped_entities, uuid_map = await dedupe_node_list(
                llm_client=self.graphiti.llm_client,
                nodes=entities
            )"""

    content = re.sub(pattern1, replacement1, content)

    # Fix 3: Change function call in manual dedup task (around line 672)
    pattern2 = r"""deduped_nodes, uuid_map = await dedupe_extracted_nodes\(
                        llm_client=self\.graphiti\.llm_client,
                        embedder=self\.graphiti\.embedder,
                        extracted_nodes=nodes,
                        threshold=payload\.get\('similarity_threshold', float\(os\.getenv\('DEDUP_SIMILARITY_THRESHOLD', '0\.6'\)\)\)
                    \)"""

    replacement2 = """deduped_nodes, uuid_map = await dedupe_node_list(
                        llm_client=self.graphiti.llm_client,
                        nodes=nodes
                    )"""

    content = re.sub(pattern2, replacement2, content)

    # Write back
    with open(WORKER_FILE, 'w') as f:
        f.write(content)

    print('✅ Fixed worker.py dedupe imports and function calls')
    print('   - Changed dedupe_extracted_nodes → dedupe_node_list (2 imports)')
    print('   - Fixed function call parameters (2 occurrences)')


if __name__ == '__main__':
    fix_worker_file()
