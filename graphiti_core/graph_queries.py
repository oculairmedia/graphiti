"""
Database query utilities for FalkorDB graph database.

This module provides query generation for FalkorDB,
supporting index creation, fulltext search, and bulk operations.
"""

from typing import Any

from typing_extensions import LiteralString

from graphiti_core.models.edges.edge_db_queries import (
    ENTITY_EDGE_SAVE_BULK,
)
from graphiti_core.models.nodes.node_db_queries import (
    ENTITY_NODE_SAVE_BULK,
)

FULLTEXT_INDEX_NAME_TO_LABEL = {
    'node_name_and_summary': 'Entity',
    'community_name': 'Community',
    'episode_content': 'Episodic',
    'edge_name_and_fact': 'RELATES_TO',
}


def get_range_indices() -> list[LiteralString]:
    return [
        'CREATE INDEX FOR (n:Entity) ON (n.uuid, n.group_id, n.name, n.created_at)',
        'CREATE INDEX FOR (n:Episodic) ON (n.uuid, n.group_id, n.created_at, n.valid_at)',
        'CREATE INDEX FOR (n:Community) ON (n.uuid)',
        'CREATE INDEX FOR ()-[e:RELATES_TO]-() ON (e.uuid, e.group_id, e.name, e.created_at, e.expired_at, e.valid_at, e.invalid_at)',
        'CREATE INDEX FOR ()-[e:MENTIONS]-() ON (e.uuid, e.group_id)',
        'CREATE INDEX FOR ()-[e:HAS_MEMBER]-() ON (e.uuid)',
    ]


def get_fulltext_indices() -> list[LiteralString]:
    return [
        """CREATE FULLTEXT INDEX FOR (e:Episodic) ON (e.content, e.source, e.source_description, e.group_id)""",
        """CREATE FULLTEXT INDEX FOR (n:Entity) ON (n.name, n.summary, n.group_id)""",
        """CREATE FULLTEXT INDEX FOR (n:Community) ON (n.name, n.group_id)""",
        """CREATE FULLTEXT INDEX FOR ()-[e:RELATES_TO]-() ON (e.name, e.fact, e.group_id)""",
    ]


def get_vector_indices(embedding_dim: int = 2560) -> list[str]:
    """
    Get HNSW vector index queries required by search-rs for fast similarity search.
    Without these indexes, searches fall back to O(n) brute-force which exhausts connection pools.
    """
    return [
        f"""CREATE VECTOR INDEX FOR (n:Entity) ON (n.name_embedding) OPTIONS {{dimension: {embedding_dim}, similarityFunction: 'cosine'}}""",
        f"""CREATE VECTOR INDEX FOR ()-[r:RELATES_TO]->() ON (r.fact_embedding) OPTIONS {{dimension: {embedding_dim}, similarityFunction: 'cosine'}}""",
    ]


def get_nodes_query(name: str = '', query: str | None = None) -> str:
    label = FULLTEXT_INDEX_NAME_TO_LABEL[name]
    return f"CALL db.idx.fulltext.queryNodes('{label}', {query})"


def get_vector_cosine_func_query(vec1, vec2) -> str:
    def should_wrap_in_vecf32(vec_param: str) -> bool:
        if '.' in vec_param and not vec_param.startswith(
            ('edge.', 'node.', 'entity.', 'relationship.', 'item.')
        ):
            return False
        if vec_param.startswith('$'):
            return True
        if vec_param.startswith(('edge.', 'node.', 'entity.', 'relationship.', 'item.')):
            return False
        return False

    falkor_vec1 = f'vecf32({vec1})' if should_wrap_in_vecf32(vec1) else vec1
    falkor_vec2 = f'vecf32({vec2})' if should_wrap_in_vecf32(vec2) else vec2
    return f'(2 - vec.cosineDistance({falkor_vec1}, {falkor_vec2}))/2'


def get_relationships_query(name: str) -> str:
    label = FULLTEXT_INDEX_NAME_TO_LABEL[name]
    return f"CALL db.idx.fulltext.queryRelationships('{label}', $query)"


def get_entity_node_save_bulk_query(nodes) -> list[tuple[str, dict[str, Any]]]:
    queries = []
    for node in nodes:
        for label in node['labels']:
            queries.append(
                (
                    f"""
                UNWIND $nodes AS node
                MERGE (n:Entity {{uuid: node.uuid}})
                ON CREATE SET n.name = node.name,
                              n.group_id = node.group_id,
                              n.summary = node.summary,
                              n.created_at = node.created_at
                ON MATCH SET n.name = COALESCE(n.name, node.name),
                             n.summary = node.summary
                SET n:{label}
                WITH n, node
                WHERE node.name_embedding IS NOT NULL
                SET n.name_embedding = vecf32(node.name_embedding)
                RETURN n.uuid AS uuid
            """,
                    {'nodes': [node]},
                )
            )
    return queries


def get_entity_edge_save_bulk_query() -> str:
    return """
    UNWIND $entity_edges AS edge
    MATCH (source:Entity {uuid: edge.source_node_uuid}) 
    MATCH (target:Entity {uuid: edge.target_node_uuid}) 
    MERGE (source)-[r:RELATES_TO {uuid: edge.uuid, group_id: edge.group_id}]->(target)
    SET r.name = edge.name,
        r.fact = edge.fact,
        r.episodes = edge.episodes,
        r.created_at = edge.created_at,
        r.expired_at = edge.expired_at,
        r.valid_at = edge.valid_at,
        r.invalid_at = edge.invalid_at,
        r.fact_embedding = vecf32(edge.fact_embedding)
    WITH r, edge
    RETURN edge.uuid AS uuid"""
