#!/usr/bin/env python3
"""
Merge all emmanuel/unknown_user entity variants into a single 'Emmanuel Umukoro' entity.

This script:
1. Creates or identifies the target entity 'Emmanuel Umukoro'
2. Re-points all MENTIONS edges from duplicate entities to the target
3. Re-points all RELATES_TO edges from duplicate entities to the target
4. Merges summaries from duplicates into the target
5. Deletes the duplicate entity nodes

Run with: python scripts/merge_emmanuel_entities.py [--dry-run]
"""

import argparse
import sys
from typing import Optional
from redis import Redis
from falkordb import FalkorDB

# Target entity details
TARGET_NAME = 'Emmanuel Umukoro'
TARGET_SUMMARY = """Emmanuel Umukoro is the infrastructure operations manager and primary user of the Graphiti knowledge graph system. 
He manages infrastructure reliability across Houdini MCP, Graphiti, and Matrix/Synapse systems.

Key accomplishments include:
- Completed major Graphiti frontend refactoring achieving 26% code reduction (74K → 55K lines)
- Fixed critical MCP set_parameter validation for proper JSON Schema serialization
- Manages Letta agent infrastructure and AI integration projects
- Coordinates creative Houdini projects with Meridian and other agents
- Expert in distributed systems troubleshooting and service recovery

Emmanuel is the sole human user currently interacting with the agent system."""

# Entities to merge (names that should all become Emmanuel Umukoro)
MERGE_NAMES = ['emmanuel', 'unknown_user', 'unknown_useruser', 'Emmanuel']


def get_db():
    """Connect to FalkorDB"""
    db = FalkorDB(host='localhost', port=6379)
    return db.select_graph('graphiti_migration')


def get_all_source_entities(graph) -> list[dict]:
    """Get all entities that should be merged"""
    query = """
    MATCH (n:Entity)
    WHERE toLower(n.name) IN ['emmanuel', 'unknown_user', 'unknown_useruser'] 
       OR n.name = 'Emmanuel'
    RETURN n.uuid as uuid, n.name as name, n.group_id as group_id, n.summary as summary
    ORDER BY n.name
    """
    result = graph.query(query)
    entities = []
    for row in result.result_set:
        entities.append({'uuid': row[0], 'name': row[1], 'group_id': row[2], 'summary': row[3]})
    return entities


def get_entity_stats(graph, uuid: str) -> dict:
    """Get MENTIONS and RELATES_TO counts for an entity"""
    mentions_query = f"""
    MATCH (n:Entity {{uuid: '{uuid}'}})-[m:MENTIONS]-()
    RETURN count(m) as count
    """
    relates_query = f"""
    MATCH (n:Entity {{uuid: '{uuid}'}})-[r:RELATES_TO]-()
    RETURN count(r) as count
    """
    mentions = (
        graph.query(mentions_query).result_set[0][0]
        if graph.query(mentions_query).result_set
        else 0
    )
    relates = (
        graph.query(relates_query).result_set[0][0] if graph.query(relates_query).result_set else 0
    )
    return {'mentions': mentions, 'relates_to': relates}


def find_or_create_target(graph, dry_run: bool) -> Optional[str]:
    """Find existing Emmanuel Umukoro or pick the entity with most connections as target"""
    # Check if Emmanuel Umukoro already exists
    check_query = f"""
    MATCH (n:Entity)
    WHERE n.name = '{TARGET_NAME}'
    RETURN n.uuid
    """
    result = graph.query(check_query)
    if result.result_set:
        return result.result_set[0][0]

    # Find the entity with the most connections to use as target
    # We'll rename it to Emmanuel Umukoro
    entities = get_all_source_entities(graph)
    if not entities:
        print('No source entities found!')
        return None

    # Find entity with most connections
    best_entity = None
    best_count = -1
    for entity in entities:
        stats = get_entity_stats(graph, entity['uuid'])
        total = stats['mentions'] + stats['relates_to']
        if total > best_count:
            best_count = total
            best_entity = entity

    if best_entity:
        print(
            f'Selected target entity: {best_entity["name"]} ({best_entity["uuid"]}) with {best_count} connections'
        )
        if not dry_run:
            # Rename to Emmanuel Umukoro
            rename_query = f"""
            MATCH (n:Entity {{uuid: '{best_entity['uuid']}'}})
            SET n.name = '{TARGET_NAME}', n.summary = $summary
            RETURN n.uuid
            """
            graph.query(rename_query, {'summary': TARGET_SUMMARY})
            print(f"Renamed entity to '{TARGET_NAME}'")
        return best_entity['uuid']

    return None


def merge_mentions_edges(graph, source_uuid: str, target_uuid: str, dry_run: bool) -> int:
    """Re-point MENTIONS edges from source to target"""
    # Get count first
    count_query = f"""
    MATCH (source:Entity {{uuid: '{source_uuid}'}})-[m:MENTIONS]-(e:Episodic)
    RETURN count(m) as count
    """
    count = graph.query(count_query).result_set[0][0] if graph.query(count_query).result_set else 0

    if count == 0:
        return 0

    if dry_run:
        print(f'  Would re-point {count} MENTIONS edges')
        return count

    # Delete old edges and create new ones pointing to target
    # FalkorDB doesn't support edge re-pointing, so we need to:
    # 1. Get all episodic nodes connected via MENTIONS with their edge properties
    # 2. Create new MENTIONS edges to target with same properties
    # 3. Delete old MENTIONS edges

    # MENTIONS edges have: uuid, group_id, created_at, updated_at
    migrate_query = f"""
    MATCH (source:Entity {{uuid: '{source_uuid}'}})-[m:MENTIONS]-(e:Episodic)
    WITH source, e, m, properties(m) as props
    MATCH (target:Entity {{uuid: '{target_uuid}'}})
    CREATE (target)-[new:MENTIONS {{uuid: props.uuid, group_id: props.group_id, created_at: props.created_at, updated_at: props.updated_at}}]->(e)
    DELETE m
    RETURN count(*) as migrated
    """
    result = graph.query(migrate_query)
    migrated = result.result_set[0][0] if result.result_set else 0
    print(f'  Migrated {migrated} MENTIONS edges')
    return migrated


def merge_relates_to_edges(graph, source_uuid: str, target_uuid: str, dry_run: bool) -> int:
    """Re-point RELATES_TO edges from source to target"""
    # Handle outgoing edges
    out_query = f"""
    MATCH (source:Entity {{uuid: '{source_uuid}'}})-[r:RELATES_TO]->(other:Entity)
    WHERE other.uuid <> '{target_uuid}'
    RETURN count(r) as count
    """
    out_count = graph.query(out_query).result_set[0][0] if graph.query(out_query).result_set else 0

    # Handle incoming edges
    in_query = f"""
    MATCH (other:Entity)-[r:RELATES_TO]->(source:Entity {{uuid: '{source_uuid}'}})
    WHERE other.uuid <> '{target_uuid}'
    RETURN count(r) as count
    """
    in_count = graph.query(in_query).result_set[0][0] if graph.query(in_query).result_set else 0

    total = out_count + in_count
    if total == 0:
        return 0

    if dry_run:
        print(
            f'  Would re-point {total} RELATES_TO edges ({out_count} outgoing, {in_count} incoming)'
        )
        return total

    # Migrate outgoing edges - copy all properties explicitly
    if out_count > 0:
        migrate_out = f"""
        MATCH (source:Entity {{uuid: '{source_uuid}'}})-[r:RELATES_TO]->(other:Entity)
        WHERE other.uuid <> '{target_uuid}'
        WITH source, other, r
        MATCH (target:Entity {{uuid: '{target_uuid}'}})
        CREATE (target)-[new:RELATES_TO {{
            uuid: r.uuid,
            group_id: r.group_id,
            name: r.name,
            fact: r.fact,
            episodes: r.episodes,
            created_at: r.created_at,
            valid_at: r.valid_at,
            invalid_at: r.invalid_at,
            expired_at: r.expired_at,
            fact_embedding: r.fact_embedding,
            updated_at: r.updated_at
        }}]->(other)
        DELETE r
        RETURN count(*) as migrated
        """
        graph.query(migrate_out)

    # Migrate incoming edges - copy all properties explicitly
    if in_count > 0:
        migrate_in = f"""
        MATCH (other:Entity)-[r:RELATES_TO]->(source:Entity {{uuid: '{source_uuid}'}})
        WHERE other.uuid <> '{target_uuid}'
        WITH source, other, r
        MATCH (target:Entity {{uuid: '{target_uuid}'}})
        CREATE (other)-[new:RELATES_TO {{
            uuid: r.uuid,
            group_id: r.group_id,
            name: r.name,
            fact: r.fact,
            episodes: r.episodes,
            created_at: r.created_at,
            valid_at: r.valid_at,
            invalid_at: r.invalid_at,
            expired_at: r.expired_at,
            fact_embedding: r.fact_embedding,
            updated_at: r.updated_at
        }}]->(target)
        DELETE r
        RETURN count(*) as migrated
        """
        graph.query(migrate_in)

    print(f'  Migrated {total} RELATES_TO edges')
    return total


def delete_source_entity(graph, uuid: str, dry_run: bool) -> bool:
    """Delete the source entity node after edges are migrated"""
    if dry_run:
        print(f'  Would delete entity node')
        return True

    # First check if any edges remain
    check_query = f"""
    MATCH (n:Entity {{uuid: '{uuid}'}})-[r]-()
    RETURN count(r) as remaining
    """
    remaining = (
        graph.query(check_query).result_set[0][0] if graph.query(check_query).result_set else 0
    )

    if remaining > 0:
        print(f'  WARNING: {remaining} edges still connected, not deleting')
        return False

    delete_query = f"""
    MATCH (n:Entity {{uuid: '{uuid}'}})
    DELETE n
    RETURN count(*) as deleted
    """
    result = graph.query(delete_query)
    deleted = result.result_set[0][0] if result.result_set else 0
    print(f'  Deleted entity node')
    return deleted > 0


def main():
    parser = argparse.ArgumentParser(
        description='Merge emmanuel/unknown_user entities into Emmanuel Umukoro'
    )
    parser.add_argument(
        '--dry-run', action='store_true', help='Show what would be done without making changes'
    )
    args = parser.parse_args()

    print(f"{'DRY RUN - ' if args.dry_run else ''}Merging entities into '{TARGET_NAME}'")
    print('=' * 60)

    graph = get_db()

    # Get all source entities
    entities = get_all_source_entities(graph)
    print(f'Found {len(entities)} entities to process:')
    for e in entities:
        stats = get_entity_stats(graph, e['uuid'])
        print(
            f'  - {e["name"]} ({e["uuid"][:8]}...): {stats["mentions"]} mentions, {stats["relates_to"]} relations'
        )
    print()

    # Find or create target
    target_uuid = find_or_create_target(graph, args.dry_run)
    if not target_uuid:
        print('ERROR: Could not find or create target entity')
        sys.exit(1)

    print(f'\nTarget entity UUID: {target_uuid}')
    print()

    # Merge each source entity into target
    total_mentions = 0
    total_relates = 0
    merged_count = 0

    for entity in entities:
        if entity['uuid'] == target_uuid:
            print(f'Skipping target entity: {entity["name"]}')
            continue

        print(f'\nMerging: {entity["name"]} ({entity["uuid"][:8]}...)')

        # Merge edges
        mentions = merge_mentions_edges(graph, entity['uuid'], target_uuid, args.dry_run)
        relates = merge_relates_to_edges(graph, entity['uuid'], target_uuid, args.dry_run)

        total_mentions += mentions
        total_relates += relates

        # Delete source entity
        if delete_source_entity(graph, entity['uuid'], args.dry_run):
            merged_count += 1

    print()
    print('=' * 60)
    print(
        f"{'Would merge' if args.dry_run else 'Merged'} {merged_count} entities into '{TARGET_NAME}'"
    )
    print(f'Total edges migrated: {total_mentions} MENTIONS, {total_relates} RELATES_TO')

    if args.dry_run:
        print('\nRun without --dry-run to apply changes')


if __name__ == '__main__':
    main()
