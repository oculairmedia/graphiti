"""
Reverse migration: FalkorDB → Neo4j with embedding preservation.

Based on simple_migration.py but modified to:
1. Read from FalkorDB instead of Neo4j
2. Write to Neo4j with proper vecf32() casting for embeddings
3. Preserve all embedding properties that were skipped in the original
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

from falkordb import FalkorDB
from neo4j import AsyncGraphDatabase

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration for reverse migration behavior
MIGRATION_CONFIG = {
    'max_query_length': 10000,
    'embedding_properties': ['name_embedding', 'summary_embedding', 'fact_embedding', 'content_embedding'],
    'preserve_embeddings': True,  # KEY CHANGE: We now preserve embeddings
    'max_array_size': 3000,  # Increased for embeddings (2560 dimensions)
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


def is_embedding_property(key: str) -> bool:
    """Check if a property is an embedding that needs vecf32 casting."""
    return key.lower() in MIGRATION_CONFIG['embedding_properties']


def should_skip_property(key: str, value: Any) -> bool:
    """Determine if a property should be skipped during migration."""
    # DON'T skip embedding properties - this is the key change!
    if is_embedding_property(key) and MIGRATION_CONFIG['preserve_embeddings']:
        return False
    
    # Skip very large arrays that aren't embeddings
    if isinstance(value, list):
        if len(value) > MIGRATION_CONFIG['max_array_size']:
            if not is_embedding_property(key):  # Only skip if not an embedding
                return True
        
        # Check if array contains large objects or deeply nested data
        try:
            if not is_embedding_property(key):  # Only check for non-embeddings
                serialized = json.dumps(value)
                if len(serialized) > 5000:  # Larger threshold for embeddings
                    return True
        except (TypeError, ValueError):
            return True
    
    # Skip complex nested dictionaries
    if isinstance(value, dict) and key not in ['name', 'type', 'summary']:
        try:
            serialized = json.dumps(value)
            if len(serialized) > 500:
                return True
        except (TypeError, ValueError):
            return True
    
    return False


def format_value_for_neo4j(key: str, value: Any) -> tuple[str, Any]:
    """
    Format value for Neo4j with special handling for embeddings.
    Returns (formatted_string, parameter_value) for parameterized queries.
    """
    if value is None:
        return 'null', None
    elif is_embedding_property(key) and isinstance(value, list):
        # For embeddings in Neo4j, store as regular lists (Neo4j doesn't have vecf32 function)
        return f'${key}', value
    elif isinstance(value, str):
        return f'${key}', value
    elif isinstance(value, bool):
        return f'${key}', value
    elif isinstance(value, (int, float)):
        # Handle special float values
        if isinstance(value, float):
            if value != value:  # NaN check
                return 'null', None
            elif value == float('inf'):
                return f'${key}', 999999999
            elif value == float('-inf'):
                return f'${key}', -999999999
        return f'${key}', value
    elif isinstance(value, list):
        return f'${key}', value
    elif hasattr(value, 'to_native'):
        # Handle Neo4j DateTime objects and similar
        try:
            native_value = value.to_native()
            if isinstance(native_value, datetime):
                return f'${key}', native_value.isoformat()
            else:
                return f'${key}', str(native_value)
        except Exception:
            return f'${key}', str(value)
    else:
        return f'${key}', str(value)


async def migrate_falkor_to_neo4j(
    falkordb_config: Dict[str, Any], 
    neo4j_config: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Perform reverse migration from FalkorDB to Neo4j with embedding preservation.
    
    Args:
        falkordb_config: FalkorDB connection configuration
        neo4j_config: Neo4j connection configuration
    
    Returns:
        Dictionary with migration statistics
    """
    start_time = datetime.now()
    logger.info("Starting reverse migration: FalkorDB → Neo4j with embedding preservation")
    
    # Initialize connections
    falkor_db = FalkorDB(
        host=falkordb_config['host'],
        port=falkordb_config['port'],
        username=falkordb_config.get('username'),
        password=falkordb_config.get('password')
    )
    falkor_graph = falkor_db.select_graph(falkordb_config['database'])
    
    neo4j_driver = AsyncGraphDatabase.driver(
        neo4j_config['uri'],
        auth=(neo4j_config['user'], neo4j_config['password'])
    )
    
    try:
        # Clear target Neo4j database (since we already cleared it)
        logger.info("Neo4j database already cleared, proceeding with migration")
        
        # Get nodes from FalkorDB
        logger.info("Fetching nodes from FalkorDB")
        falkor_nodes_result = falkor_graph.query('MATCH (n) RETURN n, labels(n) as labels')
        nodes_data = []
        
        for record in falkor_nodes_result.result_set:
            # FalkorDB returns results differently than Neo4j
            node_props = {}
            labels = []
            
            # Extract node properties and labels
            # The format is [node_object, labels_list]
            if len(record) >= 2:
                node = record[0]
                labels = record[1] if record[1] else []
                
                # Convert node to dictionary
                if hasattr(node, 'properties'):
                    node_props = dict(node.properties)
                elif hasattr(node, '__dict__'):
                    node_props = node.__dict__
                else:
                    # Try to convert directly
                    try:
                        node_props = dict(node)
                    except:
                        logger.warning(f"Could not extract properties from node: {node}")
                        continue
            
            nodes_data.append({'properties': node_props, 'labels': labels})
        
        logger.info(f"Found {len(nodes_data)} nodes to migrate from FalkorDB")
        
        # Migrate nodes to Neo4j
        node_count = 0
        node_uuid_map = {}
        
        async with neo4j_driver.session() as session:
            for i, node_data in enumerate(nodes_data):
                try:
                    properties = node_data['properties']
                    labels = node_data['labels']
                    
                    if not labels:
                        continue
                    
                    label = labels[0]  # Use first label
                    
                    # Build parameterized query for Neo4j
                    set_clauses = []
                    params = {}
                    node_uuid = properties.get('uuid')
                    
                    for key, value in properties.items():
                        # Apply filtering (but preserve embeddings)
                        if should_skip_property(key, value):
                            continue
                        
                        try:
                            formatted_value, param_value = format_value_for_neo4j(key, value)
                            if param_value is not None:
                                set_clauses.append(f'n.{key} = {formatted_value}')
                                params[key] = param_value
                            else:
                                set_clauses.append(f'n.{key} = null')
                        except Exception as e:
                            logger.warning(f'Failed to format property {key}: {e}')
                    
                    # Execute migration with parameterized query
                    if set_clauses:
                        query = f"""
                        CREATE (n:{label})
                        SET {', '.join(set_clauses)}
                        RETURN n.uuid as uuid
                        """
                    else:
                        query = f"CREATE (n:{label}) RETURN n.uuid as uuid"
                    
                    # Execute with retries
                    success = False
                    for attempt in range(MIGRATION_CONFIG['retry_attempts']):
                        try:
                            result = await session.run(query, params)
                            await result.consume()
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
                        # Log embedding stats
                        embedding_props = [k for k in properties.keys() if is_embedding_property(k)]
                        if embedding_props:
                            logger.info(f'  Node had embeddings: {embedding_props}')
                
                except Exception as e:
                    logger.error(f'Error processing node {i}: {e}')
        
        node_success_rate = (node_count / len(nodes_data) * 100) if nodes_data else 0
        logger.info(f'Successfully migrated {node_count}/{len(nodes_data)} nodes ({node_success_rate:.1f}% success rate)')
        
        # Migrate relationships from FalkorDB to Neo4j (using batching to avoid memory exhaustion)
        rel_count = 0
        if node_uuid_map:
            logger.info("Fetching relationships from FalkorDB in batches to avoid memory exhaustion")
            
            # First get total count
            count_result = falkor_graph.query("MATCH ()-[r]->() RETURN count(r) as total")
            total_rels = count_result.result_set[0][0] if count_result.result_set else 0
            logger.info(f"Total relationships to migrate: {total_rels}")
            
            # Process in smaller batches to avoid memory issues
            batch_size = 100  # Small batch size to avoid memory exhaustion
            relationships_data = []
            
            for offset in range(0, total_rels, batch_size):
                logger.info(f"Fetching batch {offset//batch_size + 1}: relationships {offset}-{offset+batch_size}")
                
                try:
                    # Get relationships from FalkorDB in small batches
                    falkor_rels_result = falkor_graph.query(f"""
                        MATCH (s)-[r]->(t) 
                        WHERE s.uuid IS NOT NULL AND t.uuid IS NOT NULL
                        RETURN s.uuid as source_uuid, t.uuid as target_uuid, type(r) as rel_type, properties(r) as props
                        SKIP {offset} LIMIT {batch_size}
                    """)
                    
                    batch_data = []
                    for record in falkor_rels_result.result_set:
                        if len(record) >= 4:
                            batch_data.append({
                                'source_uuid': record[0],
                                'target_uuid': record[1],
                                'rel_type': record[2],
                                'props': record[3] if record[3] else {}
                            })
                    
                    relationships_data.extend(batch_data)
                    logger.info(f"  Fetched {len(batch_data)} relationships in this batch")
                    
                except Exception as e:
                    logger.error(f"Failed to fetch relationship batch {offset//batch_size + 1}: {e}")
                    # Continue with what we have
                    break
            
            logger.info(f'Found {len(relationships_data)} relationships to migrate')
            
            async with neo4j_driver.session() as session:
                for i, rel_data in enumerate(relationships_data):
                    try:
                        source_uuid = rel_data['source_uuid']
                        target_uuid = rel_data['target_uuid']
                        rel_type = rel_data['rel_type']
                        props = rel_data['props']
                        
                        # Build parameterized relationship query
                        set_clauses = []
                        params = {
                            'source_uuid': source_uuid,
                            'target_uuid': target_uuid
                        }
                        
                        if props:
                            for key, value in props.items():
                                if should_skip_property(key, value):
                                    continue
                                try:
                                    formatted_value, param_value = format_value_for_neo4j(key, value)
                                    if param_value is not None:
                                        set_clauses.append(f'r.{key} = {formatted_value}')
                                        params[key] = param_value
                                    else:
                                        set_clauses.append(f'r.{key} = null')
                                except Exception as e:
                                    logger.warning(f'Failed to format relationship property {key}: {e}')
                        
                        # Create relationship query
                        if set_clauses:
                            rel_query = f"""
                            MATCH (s {{uuid: $source_uuid}}), (t {{uuid: $target_uuid}}) 
                            CREATE (s)-[r:{rel_type}]->(t)
                            SET {', '.join(set_clauses)}
                            RETURN r
                            """
                        else:
                            rel_query = f"""
                            MATCH (s {{uuid: $source_uuid}}), (t {{uuid: $target_uuid}}) 
                            CREATE (s)-[r:{rel_type}]->(t)
                            RETURN r
                            """
                        
                        # Execute with retries
                        success = False
                        for attempt in range(MIGRATION_CONFIG['retry_attempts']):
                            try:
                                result = await session.run(rel_query, params)
                                await result.consume()
                                rel_count += 1
                                success = True
                                break
                                
                            except Exception as e:
                                if attempt == MIGRATION_CONFIG['retry_attempts'] - 1:
                                    logger.error(f'Failed to migrate relationship {source_uuid}->{target_uuid} after {MIGRATION_CONFIG["retry_attempts"]} attempts: {e}')
                        
                        # Progress reporting
                        if (i + 1) % MIGRATION_CONFIG['batch_progress_interval'] == 0:
                            logger.info(f'Migrated {rel_count}/{i+1} relationships so far')
                            # Log embedding stats for relationships
                            if props:
                                embedding_props = [k for k in props.keys() if is_embedding_property(k)]
                                if embedding_props:
                                    logger.info(f'  Relationship had embeddings: {embedding_props}')
                    
                    except Exception as e:
                        logger.error(f'Error processing relationship {i}: {e}')
        
        rel_success_rate = (rel_count / len(relationships_data) * 100) if relationships_data else 0
        logger.info(f'Successfully migrated {rel_count}/{len(relationships_data)} relationships ({rel_success_rate:.1f}% success rate)')
        
        # Calculate overall statistics
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        # Count preserved embeddings
        embedding_stats = await get_embedding_statistics(neo4j_driver)
        
        stats = {
            'status': 'completed',
            'duration_seconds': duration,
            'nodes_migrated': node_count,
            'total_nodes': len(nodes_data),
            'node_success_rate': node_success_rate,
            'relationships_migrated': rel_count,
            'total_relationships': len(relationships_data),
            'relationship_success_rate': rel_success_rate,
            'embeddings_preserved': embedding_stats,
            'started_at': start_time.isoformat(),
            'completed_at': end_time.isoformat()
        }
        
        logger.info(f"Reverse migration completed successfully in {duration:.2f}s")
        logger.info(f"Embedding preservation statistics: {embedding_stats}")
        return stats
        
    except Exception as e:
        logger.error(f"Reverse migration failed: {e}")
        return {
            'status': 'failed',
            'error': str(e),
            'duration_seconds': (datetime.now() - start_time).total_seconds()
        }
        
    finally:
        await neo4j_driver.close()


async def get_embedding_statistics(neo4j_driver) -> Dict[str, Any]:
    """Get statistics about preserved embeddings in Neo4j."""
    try:
        async with neo4j_driver.session() as session:
            stats = {}
            
            # Count nodes with embeddings
            for embedding_prop in MIGRATION_CONFIG['embedding_properties']:
                result = await session.run(f"""
                    MATCH (n) 
                    WHERE n.{embedding_prop} IS NOT NULL 
                    RETURN count(n) as count
                """)
                record = await result.single()
                stats[f'nodes_with_{embedding_prop}'] = record['count'] if record else 0
            
            # Count relationships with embeddings
            result = await session.run("""
                MATCH ()-[r:RELATES_TO]->() 
                WHERE r.fact_embedding IS NOT NULL 
                RETURN count(r) as count
            """)
            record = await result.single()
            stats['relationships_with_fact_embedding'] = record['count'] if record else 0
            
            return stats
    except Exception as e:
        logger.error(f"Failed to get embedding statistics: {e}")
        return {}


async def main():
    """Main function to run the reverse migration."""
    
    # Configuration
    falkordb_config = {
        'host': 'localhost',
        'port': 6379,
        'username': '',
        'password': '',
        'database': 'graphiti_migration'  # CHANGED: Use the real data database
    }
    
    neo4j_config = {
        'uri': 'bolt://localhost:7687',
        'user': 'neo4j',
        'password': 'demodemo'
    }
    
    # Run migration
    logger.info("🔄 Starting FalkorDB → Neo4j migration with embedding preservation")
    logger.info("=" * 80)
    
    result = await migrate_falkor_to_neo4j(falkordb_config, neo4j_config)
    
    logger.info("📊 Migration Results:")
    logger.info("=" * 30)
    for key, value in result.items():
        logger.info(f"{key}: {value}")


if __name__ == '__main__':
    asyncio.run(main())