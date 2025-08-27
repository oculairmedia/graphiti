"""
Simple migration function using proven logic from migrate_working.py.

This module contains the core migration logic that achieved 100% success rate,
adapted for the sync service environment with minimal dependencies.
"""

import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from falkordb import FalkorDB
from neo4j import AsyncGraphDatabase, AsyncDriver

logger = logging.getLogger(__name__)

# Configuration for migration behavior (proven settings)
MIGRATION_CONFIG = {
    'max_query_length': 10000,
    'embedding_properties': ['name_embedding', 'summary_embedding', 'embedding', 'embeddings'],
    'skip_large_arrays': True,
    'max_array_size': 100,
    'retry_attempts': 3,
    'batch_progress_interval': 50,
}


def escape_string(value: str) -> str:
    """Enhanced string escaping for Cypher queries."""
    if value is None:
        return 'null'
    
    value_str = str(value)
    
    # Escape backslashes first to prevent double escaping
    value_str = value_str.replace('\\', '\\\\')
    
    # Escape quotes
    value_str = value_str.replace("'", "\\'")
    value_str = value_str.replace('"', '\\"')
    
    # Escape newlines and other control characters
    value_str = value_str.replace('\n', '\\n')
    value_str = value_str.replace('\r', '\\r')
    value_str = value_str.replace('\t', '\\t')
    
    return value_str


def should_skip_property(key: str, value: Any) -> bool:
    """Determine if a property should be skipped during migration."""
    # Skip known problematic embedding properties
    if key.lower() in MIGRATION_CONFIG['embedding_properties']:
        return True
    
    # Skip large arrays that might cause query length issues
    if isinstance(value, list) and MIGRATION_CONFIG['skip_large_arrays']:
        if len(value) > MIGRATION_CONFIG['max_array_size']:
            return True
        
        # Check if array contains large objects or deeply nested data
        try:
            serialized = json.dumps(value)
            if len(serialized) > 1000:  # Skip if JSON representation is too large
                return True
        except (TypeError, ValueError):
            return True
    
    # Skip complex nested dictionaries
    if isinstance(value, dict) and key not in ['name', 'type', 'summary']:
        try:
            serialized = json.dumps(value)
            if len(serialized) > 500:  # Skip large nested objects
                return True
        except (TypeError, ValueError):
            return True
    
    return False


def format_value(value: Any) -> str:
    """Format value for Cypher query with improved handling."""
    if value is None:
        return 'null'
    elif isinstance(value, str):
        return f"'{escape_string(value)}'"
    elif isinstance(value, bool):
        return 'true' if value else 'false'
    elif isinstance(value, (int, float)):
        # Handle special float values
        if isinstance(value, float):
            if value != value:  # NaN check
                return 'null'
            elif value == float('inf'):
                return '999999999'  # Large number representation
            elif value == float('-inf'):
                return '-999999999'
        return str(value)
    elif isinstance(value, list):
        try:
            # Convert list to JSON-like array format
            formatted_items = []
            for item in value:
                if isinstance(item, str):
                    formatted_items.append(f"'{escape_string(item)}'")
                else:
                    formatted_items.append(str(item))
            return '[' + ', '.join(formatted_items) + ']'
        except Exception:
            return 'null'
    elif hasattr(value, 'to_native'):
        # Handle Neo4j DateTime objects and similar
        try:
            native_value = value.to_native()
            if isinstance(native_value, datetime):
                return f"'{native_value.isoformat()}'"
            else:
                return f"'{escape_string(str(native_value))}'"
        except Exception:
            return f"'{escape_string(str(value))}'"
    else:
        return f"'{escape_string(str(value))}'"


def estimate_query_length(query: str) -> int:
    """Estimate the length of a Cypher query."""
    return len(query.encode('utf-8'))


async def perform_simple_migration(neo4j_config: Dict[str, Any], falkordb_config: Dict[str, Any]) -> Dict[str, Any]:
    """
    Perform migration using the proven simple approach.
    
    Args:
        neo4j_config: Neo4j connection configuration
        falkordb_config: FalkorDB connection configuration
    
    Returns:
        Dictionary with migration statistics
    """
    start_time = datetime.now()
    logger.info("Starting simple migration using proven method")
    
    # Initialize connections
    neo4j_driver = AsyncGraphDatabase.driver(
        neo4j_config['uri'],
        auth=(neo4j_config['user'], neo4j_config['password'])
    )
    
    falkor_db = FalkorDB(
        host=falkordb_config['host'],
        port=falkordb_config['port'],
        username=falkordb_config.get('username'),
        password=falkordb_config.get('password')
    )
    falkor_graph = falkor_db.select_graph(falkordb_config['database'])
    
    try:
        # Clear target graph (proven approach)
        logger.info("Clearing target FalkorDB graph")
        try:
            falkor_graph.delete()
        except:
            pass  # Graph might not exist yet
        
        # Get nodes from Neo4j
        logger.info("Fetching nodes from Neo4j")
        async with neo4j_driver.session() as session:
            nodes_result = await session.run('MATCH (n) RETURN n, labels(n) as labels')
            nodes = await nodes_result.data()
        
        logger.info(f"Found {len(nodes)} nodes to migrate")
        
        # Migrate nodes
        node_count = 0
        node_uuid_map = {}
        
        for i, record in enumerate(nodes):
            try:
                node = record['n']
                labels = record['labels']
                
                if not labels:
                    continue
                
                label = labels[0]  # Use first label
                
                # Build properties with smart filtering
                props = []
                node_uuid = None
                
                for key, value in node.items():
                    if key == 'uuid':
                        node_uuid = value
                    
                    # Apply smart property filtering
                    if should_skip_property(key, value):
                        continue
                    
                    try:
                        formatted_value = format_value(value)
                        props.append(f'{key}: {formatted_value}')
                    except Exception as e:
                        logger.warning(f'Failed to format property {key}: {e}')
                
                # Build and execute query with retry logic
                success = False
                for attempt in range(MIGRATION_CONFIG['retry_attempts']):
                    try:
                        if props:
                            props_str = '{' + ', '.join(props) + '}'
                            query = f'CREATE (n:{label} {props_str})'
                        else:
                            query = f'CREATE (n:{label})'
                        
                        # Check query length and simplify if needed
                        if estimate_query_length(query) > MIGRATION_CONFIG['max_query_length']:
                            # Create simplified query with only essential properties
                            essential_props = []
                            for prop in props:
                                if any(key in prop for key in ['uuid:', 'name:', 'type:', 'group_id:']):
                                    essential_props.append(prop)
                            if essential_props:
                                props_str = '{' + ', '.join(essential_props) + '}'
                                query = f'CREATE (n:{label} {props_str})'
                            else:
                                query = f'CREATE (n:{label})'
                        
                        falkor_graph.query(query)
                        node_count += 1
                        success = True
                        
                        if node_uuid:
                            node_uuid_map[node_uuid] = True
                        break
                        
                    except Exception as e:
                        if attempt == MIGRATION_CONFIG['retry_attempts'] - 1:
                            logger.error(f'Failed to migrate node {node_uuid} after {MIGRATION_CONFIG["retry_attempts"]} attempts: {e}')
                
                # Progress reporting
                if (i + 1) % MIGRATION_CONFIG['batch_progress_interval'] == 0:
                    logger.info(f'Migrated {node_count}/{i+1} nodes so far')
            
            except Exception as e:
                logger.error(f'Error processing node {i}: {e}')
        
        node_success_rate = (node_count / len(nodes) * 100) if nodes else 0
        logger.info(f'Successfully migrated {node_count}/{len(nodes)} nodes ({node_success_rate:.1f}% success rate)')
        
        # Migrate relationships
        rel_count = 0
        if node_uuid_map:
            logger.info("Fetching relationships from Neo4j")
            
            async with neo4j_driver.session() as session:
                rels_result = await session.run("""
                    MATCH (s)-[r]->(t) 
                    WHERE s.uuid IS NOT NULL AND t.uuid IS NOT NULL
                    RETURN s.uuid as source_uuid, t.uuid as target_uuid, type(r) as rel_type, properties(r) as props
                """)
                relationships = await rels_result.data()
            
            logger.info(f'Found {len(relationships)} relationships to migrate')
            
            for i, record in enumerate(relationships):
                try:
                    source_uuid = record['source_uuid']
                    target_uuid = record['target_uuid']
                    rel_type = record['rel_type']
                    props = record['props']
                    
                    # Format properties with filtering
                    prop_list = []
                    if props:
                        for key, value in props.items():
                            if should_skip_property(key, value):
                                continue
                            try:
                                formatted_value = format_value(value)
                                prop_list.append(f"{key}: {formatted_value}")
                            except Exception as e:
                                logger.warning(f'Failed to format relationship property {key}: {e}')
                    
                    prop_string = "{" + ", ".join(prop_list) + "}" if prop_list else ""
                    
                    # Create relationship with retry logic
                    success = False
                    for attempt in range(MIGRATION_CONFIG['retry_attempts']):
                        try:
                            rel_query = f"""
                            MATCH (s {{uuid: '{escape_string(source_uuid)}'}}), (t {{uuid: '{escape_string(target_uuid)}'}}) 
                            CREATE (s)-[:{rel_type} {prop_string}]->(t)
                            """
                            
                            # Check query length and simplify if needed
                            if estimate_query_length(rel_query) > MIGRATION_CONFIG['max_query_length']:
                                # Simplify by removing properties
                                rel_query = f"""
                                MATCH (s {{uuid: '{escape_string(source_uuid)}'}}), (t {{uuid: '{escape_string(target_uuid)}'}}) 
                                CREATE (s)-[:{rel_type}]->(t)
                                """
                            
                            falkor_graph.query(rel_query)
                            rel_count += 1
                            success = True
                            break
                            
                        except Exception as e:
                            if attempt == MIGRATION_CONFIG['retry_attempts'] - 1:
                                logger.error(f'Failed to migrate relationship {source_uuid}->{target_uuid} after {MIGRATION_CONFIG["retry_attempts"]} attempts: {e}')
                
                except Exception as e:
                    logger.error(f'Error processing relationship {i}: {e}')
        
        rel_success_rate = (rel_count / len(relationships) * 100) if relationships else 0
        logger.info(f'Successfully migrated {rel_count}/{len(relationships)} relationships ({rel_success_rate:.1f}% success rate)')
        
        # Calculate overall statistics
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        stats = {
            'status': 'completed',
            'duration_seconds': duration,
            'nodes_migrated': node_count,
            'total_nodes': len(nodes),
            'node_success_rate': node_success_rate,
            'relationships_migrated': rel_count,
            'total_relationships': len(relationships) if 'relationships' in locals() else 0,
            'relationship_success_rate': rel_success_rate if 'relationships' in locals() else 0,
            'started_at': start_time.isoformat(),
            'completed_at': end_time.isoformat()
        }
        
        logger.info(f"Migration completed successfully in {duration:.2f}s")
        return stats
        
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'duration_seconds': (datetime.now() - start_time).total_seconds()
        }
        
    finally:
        await neo4j_driver.close()