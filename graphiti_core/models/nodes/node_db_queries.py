"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

EPISODIC_NODE_SAVE = """
        MERGE (n:Episodic {uuid: $uuid})
        SET n = {uuid: $uuid, name: $name, group_id: $group_id, source_description: $source_description, source: $source, content: $content, 
        entity_edges: $entity_edges, created_at: $created_at, valid_at: $valid_at, entity_count: $entity_count, edge_count: $edge_count, cross_group_connections: $cross_group_connections, extraction_version: $extraction_version, confidence_score: $confidence_score}
        RETURN n.uuid AS uuid"""

EPISODIC_NODE_SAVE_BULK = """
    UNWIND $episodes AS episode
    MERGE (n:Episodic {uuid: episode.uuid, group_id: episode.group_id})
    SET n.name = episode.name,
        n.source_description = episode.source_description,
        n.source = episode.source,
        n.content = episode.content,
        n.entity_edges = episode.entity_edges,
        n.created_at = episode.created_at,
        n.valid_at = episode.valid_at,
        n.entity_count = episode.entity_count,
        n.edge_count = episode.edge_count,
        n.cross_group_connections = episode.cross_group_connections,
        n.extraction_version = episode.extraction_version,
        n.confidence_score = episode.confidence_score
    RETURN n.uuid AS uuid
"""

ENTITY_NODE_SAVE = """
        MERGE (n:Entity {uuid: $entity_data.uuid})
        SET n = $entity_data
        SET n.name_embedding = vecf32($entity_data.name_embedding)
        RETURN n.uuid AS uuid"""

ENTITY_NODE_SAVE_BULK = """
    UNWIND $nodes AS node
    MERGE (n:Entity {uuid: node.uuid})
    SET n = node
    SET n.name_embedding = vecf32(node.name_embedding)
    RETURN n.uuid AS uuid
"""

COMMUNITY_NODE_SAVE = """
        MERGE (n:Community {uuid: $uuid})
        SET n = {uuid: $uuid, name: $name, group_id: $group_id, summary: $summary, created_at: $created_at}
        SET n.name_embedding = vecf32($name_embedding)
        RETURN n.uuid AS uuid"""
