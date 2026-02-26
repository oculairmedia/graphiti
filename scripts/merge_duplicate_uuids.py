#!/usr/bin/env python3
"""
Merge duplicate-UUID nodes in FalkorDB.

FalkorDB doesn't enforce UUID uniqueness — re-ingestion with different entity type
labels can create multiple nodes with the same uuid property. This crashes the
visualizer (DuckDB PRIMARY KEY violation).

Strategy per duplicate group:
1. Pick canonical: most edges → longest summary → earliest created_at
2. Transfer all edges (RELATES_TO, MENTIONS) from duplicates to canonical
3. Merge labels onto canonical
4. Delete duplicate nodes

Usage:
    python3 scripts/merge_duplicate_uuids.py           # Dry run (report only)
    python3 scripts/merge_duplicate_uuids.py --fix     # Execute merges
"""

import argparse
import sys
import redis


GRAPH = 'graphiti_migration'


def query(r, cypher):
    """Execute a FalkorDB GRAPH.QUERY and return parsed rows."""
    result = r.execute_command('GRAPH.QUERY', GRAPH, cypher)
    # result[0] = header, result[1] = rows, result[2] = stats
    if len(result) < 2 or not result[1]:
        return []
    return result[1]


def query_with_stats(r, cypher):
    """Execute a query and return (rows, stats_strings)."""
    result = r.execute_command('GRAPH.QUERY', GRAPH, cypher)
    rows = result[1] if len(result) > 1 and result[1] else []
    stats = result[-1] if result else []
    return rows, stats


def find_duplicate_uuids(r):
    """Find all UUIDs that appear on more than one node."""
    rows = query(
        r,
        """
        MATCH (n)
        WITH n.uuid AS uuid, count(n) AS cnt
        WHERE cnt > 1
        RETURN uuid, cnt
        ORDER BY cnt DESC
    """,
    )
    return [(row[0], int(row[1])) for row in rows]


def get_node_details(r, uuid):
    """Get all nodes with this UUID, with internal IDs and edge counts."""
    rows = query(
        r,
        f"""
        MATCH (n {{uuid: '{uuid}'}})
        OPTIONAL MATCH (n)-[r]-()
        WITH n, count(r) AS edge_count
        RETURN id(n) AS nid,
               labels(n) AS labels,
               n.name AS name,
               n.summary AS summary,
               n.created_at AS created_at,
               edge_count
        ORDER BY edge_count DESC
    """,
    )
    nodes = []
    for row in rows:
        nodes.append(
            {
                'nid': int(row[0]),
                'labels': row[1],
                'name': row[2],
                'summary': row[3] or '',
                'created_at': row[4] or '',
                'edge_count': int(row[5]),
            }
        )
    return nodes


def pick_canonical(nodes):
    """Pick the canonical node: most edges → longest summary → earliest created_at."""
    return sorted(
        nodes,
        key=lambda n: (
            -n['edge_count'],
            -len(n['summary']),
            n['created_at'] or 'z',  # earliest first, missing last
        ),
    )[0]


def transfer_edges(r, canonical_nid, dup_nid, edge_type, dry_run=True):
    """Transfer edges of a specific type from duplicate to canonical.

    Returns (transferred, skipped_self_loops, skipped_existing).
    """
    transferred = 0
    skipped_self = 0
    skipped_existing = 0

    # Transfer INCOMING edges: (source)-[r]->(dup) → (source)-[r]->(canonical)
    incoming = query(
        r,
        f"""
        MATCH (source)-[r:{edge_type}]->(dup)
        WHERE id(dup) = {dup_nid}
        RETURN id(source) AS src_nid, id(r) AS rid, properties(r) AS props
    """,
    )

    for row in incoming:
        src_nid = int(row[0])
        if src_nid == canonical_nid:
            skipped_self += 1
            continue

        # Check if canonical already has this edge from same source
        existing = query(
            r,
            f"""
            MATCH (source)-[r:{edge_type}]->(target)
            WHERE id(source) = {src_nid} AND id(target) = {canonical_nid}
            RETURN count(r)
        """,
        )
        if existing and int(existing[0][0]) > 0:
            skipped_existing += 1
            if not dry_run:
                # Delete the duplicate edge
                query(r, f'MATCH ()-[r]->() WHERE id(r) = {int(row[1])} DELETE r')
            continue

        if not dry_run:
            # Create edge to canonical, then delete old
            query(
                r,
                f"""
                MATCH (source), (canonical)
                WHERE id(source) = {src_nid} AND id(canonical) = {canonical_nid}
                CREATE (source)-[r:{edge_type}]->(canonical)
            """,
            )
            query(r, f'MATCH ()-[r]->() WHERE id(r) = {int(row[1])} DELETE r')
        transferred += 1

    # Transfer OUTGOING edges: (dup)-[r]->(target) → (canonical)-[r]->(target)
    outgoing = query(
        r,
        f"""
        MATCH (dup)-[r:{edge_type}]->(target)
        WHERE id(dup) = {dup_nid}
        RETURN id(target) AS tgt_nid, id(r) AS rid, properties(r) AS props
    """,
    )

    for row in outgoing:
        tgt_nid = int(row[0])
        if tgt_nid == canonical_nid:
            skipped_self += 1
            continue

        # Check if canonical already has this edge to same target
        existing = query(
            r,
            f"""
            MATCH (source)-[r:{edge_type}]->(target)
            WHERE id(source) = {canonical_nid} AND id(target) = {tgt_nid}
            RETURN count(r)
        """,
        )
        if existing and int(existing[0][0]) > 0:
            skipped_existing += 1
            if not dry_run:
                query(r, f'MATCH ()-[r]->() WHERE id(r) = {int(row[1])} DELETE r')
            continue

        if not dry_run:
            query(
                r,
                f"""
                MATCH (canonical), (target)
                WHERE id(canonical) = {canonical_nid} AND id(target) = {tgt_nid}
                CREATE (canonical)-[r:{edge_type}]->(target)
            """,
            )
            query(r, f'MATCH ()-[r]->() WHERE id(r) = {int(row[1])} DELETE r')
        transferred += 1

    return transferred, skipped_self, skipped_existing


def delete_remaining_edges(r, nid):
    """Delete any remaining edges on a node (safety net)."""
    query(
        r,
        f"""
        MATCH (n)-[r]-()
        WHERE id(n) = {nid}
        DELETE r
    """,
    )


def delete_node(r, nid):
    """Delete a node by internal ID."""
    query(
        r,
        f"""
        MATCH (n)
        WHERE id(n) = {nid}
        DELETE n
    """,
    )


def main():
    parser = argparse.ArgumentParser(description='Merge duplicate-UUID nodes in FalkorDB')
    parser.add_argument('--fix', action='store_true', help='Execute merges (default: dry run)')
    parser.add_argument('--host', default='localhost', help='FalkorDB host')
    parser.add_argument('--port', type=int, default=6379, help='FalkorDB port')
    args = parser.parse_args()

    dry_run = not args.fix
    r = redis.Redis(host=args.host, port=args.port, decode_responses=True)

    # Verify connectivity
    try:
        r.ping()
    except redis.ConnectionError:
        print(f'ERROR: Cannot connect to FalkorDB at {args.host}:{args.port}')
        sys.exit(1)

    print(f'{"DRY RUN" if dry_run else "EXECUTING"}: Merge duplicate-UUID nodes')
    print('=' * 70)

    duplicates = find_duplicate_uuids(r)
    if not duplicates:
        print('No duplicate UUIDs found. Graph is clean.')
        return

    print(f'Found {len(duplicates)} duplicate UUIDs ({sum(c for _, c in duplicates)} total nodes)')
    print()

    total_merged = 0
    total_transferred = 0
    total_deleted = 0
    errors = []

    for uuid, count in duplicates:
        nodes = get_node_details(r, uuid)
        if len(nodes) < 2:
            continue  # Race condition — already cleaned up

        canonical = pick_canonical(nodes)
        duplicates_to_merge = [n for n in nodes if n['nid'] != canonical['nid']]

        print(f'UUID: {uuid} ({count} copies)')
        print(
            f'  Canonical: nid={canonical["nid"]} labels={canonical["labels"]} '
            f'edges={canonical["edge_count"]} name="{canonical["name"]}"'
        )

        for dup in duplicates_to_merge:
            print(
                f'  Duplicate: nid={dup["nid"]} labels={dup["labels"]} '
                f'edges={dup["edge_count"]} name="{dup["name"]}"'
            )

            try:
                # Transfer RELATES_TO edges
                rt_xfer, rt_self, rt_exist = transfer_edges(
                    r, canonical['nid'], dup['nid'], 'RELATES_TO', dry_run
                )

                # Transfer MENTIONS edges
                mn_xfer, mn_self, mn_exist = transfer_edges(
                    r, canonical['nid'], dup['nid'], 'MENTIONS', dry_run
                )

                transferred = rt_xfer + mn_xfer
                skipped = rt_self + mn_self + rt_exist + mn_exist

                print(
                    f'    → Transfer: {transferred} edges, skip: {skipped} '
                    f'(self-loops: {rt_self + mn_self}, existing: {rt_exist + mn_exist})'
                )

                if not dry_run:
                    # Delete any remaining edges (safety net for unknown edge types)
                    delete_remaining_edges(r, dup['nid'])
                    # Delete the duplicate node
                    delete_node(r, dup['nid'])
                    print(f'    → Deleted duplicate node {dup["nid"]}')

                total_transferred += transferred
                total_deleted += 1
                total_merged += 1

            except Exception as e:
                msg = f'Error merging nid={dup["nid"]} uuid={uuid}: {e}'
                print(f'    ERROR: {msg}')
                errors.append(msg)

        print()

    print('=' * 70)
    print(f'Summary: {total_merged} duplicates {"would be" if dry_run else ""} merged')
    print(f'  Edges transferred: {total_transferred}')
    print(f'  Nodes deleted: {total_deleted}')
    if errors:
        print(f'  Errors: {len(errors)}')
        for e in errors:
            print(f'    - {e}')

    if dry_run:
        print()
        print('This was a DRY RUN. Run with --fix to execute.')

    # Post-fix verification
    if not dry_run:
        print()
        remaining = find_duplicate_uuids(r)
        if remaining:
            print(f'WARNING: {len(remaining)} duplicate UUIDs still remain!')
            for uuid, cnt in remaining[:5]:
                print(f'  {uuid}: {cnt} copies')
        else:
            print('✓ Verification passed: 0 duplicate UUIDs remain')

        # Print final counts
        node_count = query(r, 'MATCH (n) RETURN count(n)')[0][0]
        edge_count = query(r, 'MATCH ()-[r]->() RETURN count(r)')[0][0]
        print(f'  Final graph: {node_count} nodes, {edge_count} edges')


if __name__ == '__main__':
    main()
