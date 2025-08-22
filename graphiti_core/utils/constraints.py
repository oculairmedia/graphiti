"""
Database constraint utilities for different graph database backends.

This module provides database-agnostic constraint generation for Neo4j and FalkorDB,
supporting unique constraints, existence constraints, and other data integrity rules.
"""

import logging
from typing_extensions import LiteralString

logger = logging.getLogger(__name__)


def get_unique_constraints(db_type: str = 'neo4j') -> list[LiteralString]:
    """
    Get unique constraint creation queries for the specified database type.
    
    These constraints prevent duplicate entities and edges from being created
    at the database level, complementing application-level validation.
    
    Note: For FalkorDB, exact-match indexes must exist before creating unique constraints.
    
    Args:
        db_type: Database type ('neo4j' or 'falkordb')
        
    Returns:
        List of constraint creation queries
    """
    if db_type == 'falkordb':
        # FalkorDB uses GRAPH.CONSTRAINT CREATE syntax and requires indices first
        # These will be executed via the driver's execute_query method
        return [
            # Unique constraint on Entity UUID - prevents duplicate entities
            'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Entity PROPERTIES 1 uuid',
            
            # Unique constraint on Episodic UUID - prevents duplicate episodes  
            'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Episodic PROPERTIES 1 uuid',
            
            # Unique constraint on Community UUID - prevents duplicate communities
            'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Community PROPERTIES 1 uuid',
            
            # Unique constraint on RELATES_TO edge UUID - prevents duplicate relationships
            'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE RELATIONSHIP RELATES_TO PROPERTIES 1 uuid',
            
            # MENTIONS edge UUID constraint removed - episodes can legitimately mention same entities
            # 'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE RELATIONSHIP MENTIONS PROPERTIES 1 uuid',
            
            # Unique constraint on HAS_MEMBER edge UUID - prevents duplicate memberships
            'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE RELATIONSHIP HAS_MEMBER PROPERTIES 1 uuid',
            
            # Unique constraint on Entity name+group_id combination for deduplication
            # This prevents multiple entities with the same normalized name in a group
            'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Entity PROPERTIES 2 name group_id',
        ]
    else:
        # Neo4j syntax
        return [
            # Unique constraint on Entity UUID
            'CREATE CONSTRAINT entity_uuid_unique IF NOT EXISTS FOR (n:Entity) REQUIRE n.uuid IS UNIQUE',
            
            # Unique constraint on Episodic UUID  
            'CREATE CONSTRAINT episodic_uuid_unique IF NOT EXISTS FOR (n:Episodic) REQUIRE n.uuid IS UNIQUE',
            
            # Unique constraint on Community UUID
            'CREATE CONSTRAINT community_uuid_unique IF NOT EXISTS FOR (n:Community) REQUIRE n.uuid IS UNIQUE',
            
            # Unique constraint on RELATES_TO edge UUID
            'CREATE CONSTRAINT relates_to_uuid_unique IF NOT EXISTS FOR ()-[e:RELATES_TO]-() REQUIRE e.uuid IS UNIQUE',
            
            # MENTIONS edge UUID constraint removed - episodes can legitimately mention same entities
            # 'CREATE CONSTRAINT mentions_uuid_unique IF NOT EXISTS FOR ()-[e:MENTIONS]-() REQUIRE e.uuid IS UNIQUE',
            
            # Unique constraint on HAS_MEMBER edge UUID
            'CREATE CONSTRAINT has_member_uuid_unique IF NOT EXISTS FOR ()-[e:HAS_MEMBER]-() REQUIRE e.uuid IS UNIQUE',
            
            # Unique constraint on Entity name+group_id combination
            'CREATE CONSTRAINT entity_name_group_unique IF NOT EXISTS FOR (n:Entity) REQUIRE (n.name, n.group_id) IS UNIQUE',
        ]


def get_existence_constraints(db_type: str = 'neo4j') -> list[LiteralString]:
    """
    Get existence constraint creation queries for the specified database type.
    
    These constraints ensure required fields are always present.
    
    Args:
        db_type: Database type ('neo4j' or 'falkordb')
        
    Returns:
        List of existence constraint creation queries
    """
    if db_type == 'falkordb':
        # FalkorDB uses GRAPH.CONSTRAINT CREATE syntax for mandatory constraints
        return [
            # Entity nodes must have UUID, name, and group_id
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Entity PROPERTIES 1 uuid',
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Entity PROPERTIES 1 name',
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Entity PROPERTIES 1 group_id',
            
            # Episodic nodes must have UUID and group_id
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Episodic PROPERTIES 1 uuid',
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Episodic PROPERTIES 1 group_id',
            
            # Community nodes must have UUID
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Community PROPERTIES 1 uuid',
            
            # All edges must have UUID and group_id
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP RELATES_TO PROPERTIES 1 uuid',
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP RELATES_TO PROPERTIES 1 group_id',
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP MENTIONS PROPERTIES 1 uuid',
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP MENTIONS PROPERTIES 1 group_id',
            'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP HAS_MEMBER PROPERTIES 1 uuid',
        ]
    else:
        # Neo4j syntax
        return [
            # Entity nodes existence constraints
            'CREATE CONSTRAINT entity_uuid_exists IF NOT EXISTS FOR (n:Entity) REQUIRE n.uuid IS NOT NULL',
            'CREATE CONSTRAINT entity_name_exists IF NOT EXISTS FOR (n:Entity) REQUIRE n.name IS NOT NULL',
            'CREATE CONSTRAINT entity_group_id_exists IF NOT EXISTS FOR (n:Entity) REQUIRE n.group_id IS NOT NULL',
            
            # Episodic nodes existence constraints
            'CREATE CONSTRAINT episodic_uuid_exists IF NOT EXISTS FOR (n:Episodic) REQUIRE n.uuid IS NOT NULL',
            'CREATE CONSTRAINT episodic_group_id_exists IF NOT EXISTS FOR (n:Episodic) REQUIRE n.group_id IS NOT NULL',
            
            # Community nodes existence constraints  
            'CREATE CONSTRAINT community_uuid_exists IF NOT EXISTS FOR (n:Community) REQUIRE n.uuid IS NOT NULL',
            
            # Edge existence constraints
            'CREATE CONSTRAINT relates_to_uuid_exists IF NOT EXISTS FOR ()-[e:RELATES_TO]-() REQUIRE e.uuid IS NOT NULL',
            'CREATE CONSTRAINT relates_to_group_id_exists IF NOT EXISTS FOR ()-[e:RELATES_TO]-() REQUIRE e.group_id IS NOT NULL',
            'CREATE CONSTRAINT mentions_uuid_exists IF NOT EXISTS FOR ()-[e:MENTIONS]-() REQUIRE e.uuid IS NOT NULL',
            'CREATE CONSTRAINT mentions_group_id_exists IF NOT EXISTS FOR ()-[e:MENTIONS]-() REQUIRE e.group_id IS NOT NULL',
            'CREATE CONSTRAINT has_member_uuid_exists IF NOT EXISTS FOR ()-[e:HAS_MEMBER]-() REQUIRE e.uuid IS NOT NULL',
        ]


def get_all_constraints(db_type: str = 'neo4j') -> list[LiteralString]:
    """
    Get all constraint creation queries for the specified database type.
    
    Args:
        db_type: Database type ('neo4j' or 'falkordb')
        
    Returns:
        List of all constraint creation queries
    """
    return get_unique_constraints(db_type) + get_existence_constraints(db_type)