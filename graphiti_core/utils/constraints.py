"""
Database constraint utilities for FalkorDB graph database.

This module provides constraint generation for FalkorDB,
supporting unique constraints, existence constraints, and other data integrity rules.
"""

import logging
from typing_extensions import LiteralString

logger = logging.getLogger(__name__)


def get_unique_constraints() -> list[LiteralString]:
    """
    Get unique constraint creation queries for FalkorDB.

    These constraints prevent duplicate entities and edges from being created
    at the database level, complementing application-level validation.

    Note: For FalkorDB, exact-match indexes must exist before creating unique constraints.

    Returns:
        List of constraint creation queries
    """
    return [
        'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Entity PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Episodic PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Community PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE RELATIONSHIP HAS_MEMBER PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} UNIQUE NODE Entity PROPERTIES 2 name group_id',
    ]


def get_existence_constraints() -> list[LiteralString]:
    """
    Get existence constraint creation queries for FalkorDB.

    These constraints ensure required fields are always present.

    Returns:
        List of existence constraint creation queries
    """
    return [
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Entity PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Entity PROPERTIES 1 name',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Entity PROPERTIES 1 group_id',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Episodic PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Episodic PROPERTIES 1 group_id',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY NODE Community PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP RELATES_TO PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP RELATES_TO PROPERTIES 1 group_id',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP MENTIONS PROPERTIES 1 uuid',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP MENTIONS PROPERTIES 1 group_id',
        'GRAPH.CONSTRAINT CREATE {graph_key} MANDATORY RELATIONSHIP HAS_MEMBER PROPERTIES 1 uuid',
    ]


def get_all_constraints() -> list[LiteralString]:
    """
    Get all constraint creation queries for FalkorDB.

    Returns:
        List of all constraint creation queries
    """
    return get_unique_constraints() + get_existence_constraints()
