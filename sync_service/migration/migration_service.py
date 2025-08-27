"""
Migration service for Neo4j to FalkorDB data migration.

This service encapsulates the proven migration logic from migrate_working.py
as an async service class that integrates with the sync service architecture.
"""

import asyncio
import json
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional, Callable
from dataclasses import dataclass
from enum import Enum

from falkordb import FalkorDB
from neo4j import AsyncGraphDatabase, AsyncDriver

logger = logging.getLogger(__name__)


class MigrationStatus(Enum):
    """Migration operation status."""
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MigrationProgress:
    """Migration progress tracking."""
    status: MigrationStatus = MigrationStatus.IDLE
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    total_nodes: int = 0
    migrated_nodes: int = 0
    total_relationships: int = 0
    migrated_relationships: int = 0
    current_phase: str = "initializing"
    errors: List[str] = None
    
    def __post_init__(self):
        if self.errors is None:
            self.errors = []
    
    @property
    def node_success_rate(self) -> float:
        """Calculate node migration success rate."""
        if self.total_nodes == 0:
            return 0.0
        return (self.migrated_nodes / self.total_nodes) * 100
    
    @property
    def relationship_success_rate(self) -> float:
        """Calculate relationship migration success rate."""
        if self.total_relationships == 0:
            return 0.0
        return (self.migrated_relationships / self.total_relationships) * 100
    
    @property
    def duration_seconds(self) -> float:
        """Calculate migration duration."""
        if not self.started_at:
            return 0.0
        end_time = self.completed_at or datetime.utcnow()
        return (end_time - self.started_at).total_seconds()


@dataclass
class MigrationConfig:
    """Migration service configuration."""
    max_query_length: int = 10000
    embedding_properties: List[str] = None
    skip_large_arrays: bool = True
    max_array_size: int = 100
    retry_attempts: int = 3
    batch_progress_interval: int = 50
    clear_target_on_start: bool = True
    
    def __post_init__(self):
        if self.embedding_properties is None:
            self.embedding_properties = [
                'name_embedding', 
                'summary_embedding', 
                'embedding', 
                'embeddings'
            ]


class MigrationService:
    """
    Service for migrating data from Neo4j to FalkorDB.
    
    This service integrates the proven migration logic into the sync service
    architecture with proper async operation, progress tracking, and monitoring.
    """
    
    def __init__(
        self,
        neo4j_config: Dict[str, Any],
        falkordb_config: Dict[str, Any],
        migration_config: Optional[MigrationConfig] = None,
        progress_callback: Optional[Callable[[MigrationProgress], None]] = None
    ):
        """
        Initialize migration service.
        
        Args:
            neo4j_config: Neo4j connection configuration
            falkordb_config: FalkorDB connection configuration
            migration_config: Migration behavior configuration
            progress_callback: Optional callback for progress updates
        """
        self.neo4j_config = neo4j_config
        self.falkordb_config = falkordb_config
        self.config = migration_config or MigrationConfig()
        self.progress_callback = progress_callback
        
        self.progress = MigrationProgress()
        self._cancelled = False
        
        # Connection objects
        self.neo4j_driver: Optional[AsyncDriver] = None
        self.falkor_db: Optional[FalkorDB] = None
        self.falkor_graph = None
    
    async def __aenter__(self):
        """Async context manager entry."""
        await self._initialize_connections()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        await self._cleanup_connections()
    
    async def _initialize_connections(self):
        """Initialize database connections."""
        try:
            # Initialize Neo4j driver
            self.neo4j_driver = AsyncGraphDatabase.driver(
                self.neo4j_config['uri'],
                auth=(self.neo4j_config['user'], self.neo4j_config['password'])
            )
            
            # Initialize FalkorDB connection
            self.falkor_db = FalkorDB(
                host=self.falkordb_config['host'],
                port=self.falkordb_config['port'],
                username=self.falkordb_config.get('username'),
                password=self.falkordb_config.get('password')
            )
            self.falkor_graph = self.falkor_db.select_graph(
                self.falkordb_config['database']
            )
            
            logger.info("Migration service connections initialized")
            
        except Exception as e:
            logger.error(f"Failed to initialize migration service connections: {e}")
            raise
    
    async def _cleanup_connections(self):
        """Clean up database connections."""
        if self.neo4j_driver:
            await self.neo4j_driver.close()
            self.neo4j_driver = None
        
        # FalkorDB connection cleanup is handled by the library
        self.falkor_db = None
        self.falkor_graph = None
        
        logger.info("Migration service connections cleaned up")
    
    def _should_skip_property(self, key: str, value: Any) -> bool:
        """Determine if a property should be skipped during migration."""
        # Skip known problematic embedding properties
        if key.lower() in self.config.embedding_properties:
            return True
        
        # Skip large arrays that might cause query length issues
        if isinstance(value, list) and self.config.skip_large_arrays:
            if len(value) > self.config.max_array_size:
                return True
            
            # Check if array contains large objects or deeply nested data
            try:
                serialized = json.dumps(value)
                if len(serialized) > 1000:  # Skip if JSON representation is too large
                    return True
            except (TypeError, ValueError):
                # Skip if not JSON serializable
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
    
    def _escape_string(self, value: str) -> str:
        """Enhanced string escaping for Cypher queries."""
        if value is None:
            return 'null'
        
        # Convert to string and handle various escape sequences
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
        
        # Handle Unicode and special characters
        try:
            # Ensure the string is properly encoded
            value_str.encode('utf-8')
        except UnicodeEncodeError:
            # Replace problematic characters
            value_str = value_str.encode('utf-8', errors='replace').decode('utf-8')
        
        return value_str
    
    def _format_value(self, value: Any) -> str:
        """Format value for Cypher query with improved handling."""
        if value is None:
            return 'null'
        elif isinstance(value, str):
            return f"'{self._escape_string(value)}'"
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
                    return '-999999999'  # Large negative number
            return str(value)
        elif isinstance(value, datetime):
            return f"'{value.isoformat()}'"
        elif hasattr(value, 'to_native'):
            # Handle Neo4j DateTime objects
            try:
                native_dt = value.to_native()
                return f"'{native_dt.strftime('%Y-%m-%dT%H:%M:%S')}'"
            except:
                return f"'{str(value).split('.')[0].replace('+00:00', '').replace('Z', '')}'"
        elif isinstance(value, list):
            # Only include small lists
            if len(value) <= self.config.max_array_size:
                try:
                    json_str = json.dumps(value, default=str)
                    if len(json_str) <= 500:  # Reasonable size limit
                        return f"'{self._escape_string(json_str)}'"
                except:
                    pass
            return f"'[{len(value)} items]'"  # Placeholder for large lists
        else:
            return f"'{self._escape_string(str(value))}'"
    
    def _estimate_query_length(self, query: str) -> int:
        """Estimate the length of a Cypher query."""
        return len(query.encode('utf-8'))
    
    def _update_progress(self, **kwargs):
        """Update migration progress and notify callback."""
        for key, value in kwargs.items():
            if hasattr(self.progress, key):
                setattr(self.progress, key, value)
        
        if self.progress_callback:
            try:
                self.progress_callback(self.progress)
            except Exception as e:
                logger.warning(f"Progress callback failed: {e}")
    
    async def migrate_full(self) -> MigrationProgress:
        """
        Perform a full migration from Neo4j to FalkorDB.
        
        Returns:
            MigrationProgress: Final migration progress with results
        """
        if not self.neo4j_driver or not self.falkor_graph:
            raise RuntimeError("Migration service not properly initialized")
        
        try:
            # Initialize progress tracking
            self.progress = MigrationProgress(
                status=MigrationStatus.RUNNING,
                started_at=datetime.utcnow()
            )
            self._update_progress(current_phase="starting_migration")
            
            logger.info("Starting full Neo4j to FalkorDB migration")
            
            # Clear FalkorDB if configured
            if self.config.clear_target_on_start:
                self._update_progress(current_phase="clearing_target_database")
                logger.info("Clearing FalkorDB...")
                try:
                    self.falkor_graph.query('MATCH (n) DETACH DELETE n')
                except:
                    pass  # Graph might not exist yet
            
            # Get total node count for progress tracking
            self._update_progress(current_phase="counting_source_data")
            async with self.neo4j_driver.session() as session:
                count_result = await session.run('MATCH (n) RETURN count(n) as count')
                count_record = await count_result.single()
            total_nodes = count_record['count'] if count_record else 0
            self._update_progress(total_nodes=total_nodes)
            
            logger.info(f"Found {total_nodes} nodes to migrate")
            
            # Migrate nodes
            self._update_progress(current_phase="migrating_nodes")
            await self._migrate_nodes()
            
            # Migrate relationships
            self._update_progress(current_phase="migrating_relationships")
            await self._migrate_relationships()
            
            # Verify migration results
            self._update_progress(current_phase="verifying_migration")
            await self._verify_migration()
            
            # Complete migration
            self.progress.status = MigrationStatus.COMPLETED
            self.progress.completed_at = datetime.utcnow()
            self._update_progress(current_phase="migration_completed")
            
            logger.info(
                f"Migration completed successfully: "
                f"{self.progress.migrated_nodes}/{self.progress.total_nodes} nodes "
                f"({self.progress.node_success_rate:.1f}%), "
                f"{self.progress.migrated_relationships}/{self.progress.total_relationships} relationships "
                f"({self.progress.relationship_success_rate:.1f}%)"
            )
            
            return self.progress
            
        except Exception as e:
            self.progress.status = MigrationStatus.FAILED
            self.progress.completed_at = datetime.utcnow()
            self.progress.errors.append(str(e))
            self._update_progress()
            
            logger.error(f"Migration failed: {e}", exc_info=True)
            raise
    
    async def _migrate_nodes(self):
        """Migrate nodes from Neo4j to FalkorDB."""
        logger.info("Fetching nodes from Neo4j...")
        
        # Get nodes with labels
        nodes_query = 'MATCH (n) RETURN n, labels(n) as labels'
        async with self.neo4j_driver.session() as session:
            nodes_result = await session.run(nodes_query)
            nodes = await nodes_result.data()
        
        logger.info(f"Migrating {len(nodes)} nodes...")
        node_count = 0
        node_uuid_map = {}  # Track successfully migrated nodes
        
        for i, record in enumerate(nodes):
            if self._cancelled:
                logger.info("Migration cancelled by user")
                break
            
            try:
                node = record['n']
                labels = record['labels']
                
                # Skip if no labels
                if not labels:
                    continue
                
                label = labels[0]  # Use first label
                
                # Build properties with smart filtering
                props = []
                node_uuid = None
                skipped_properties = []
                
                for key, value in node.items():
                    if key == 'uuid':
                        node_uuid = value
                    
                    # Apply smart property filtering
                    if self._should_skip_property(key, value):
                        skipped_properties.append(key)
                        continue
                    
                    try:
                        formatted_value = self._format_value(value)
                        props.append(f'{key}: {formatted_value}')
                    except Exception as e:
                        logger.warning(f"Failed to format property {key}: {e}")
                        skipped_properties.append(key)
                
                if skipped_properties and len(skipped_properties) <= 5:  # Log only if reasonable number
                    logger.debug(f"Skipped properties for node {node_uuid}: {skipped_properties}")
                
                # Build and execute query with retry logic
                success = False
                for attempt in range(self.config.retry_attempts):
                    try:
                        if props:
                            props_str = '{' + ', '.join(props) + '}'
                            query = f'CREATE (n:{label} {props_str})'
                        else:
                            query = f'CREATE (n:{label})'
                        
                        # Check query length
                        if self._estimate_query_length(query) > self.config.max_query_length:
                            logger.debug(f"Query too long for node {node_uuid}, simplifying...")
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
                        
                        self.falkor_graph.query(query)
                        node_count += 1
                        success = True
                        
                        if node_uuid:
                            node_uuid_map[node_uuid] = True
                        
                        break  # Success, exit retry loop
                        
                    except Exception as e:
                        if attempt == self.config.retry_attempts - 1:  # Last attempt
                            error_msg = str(e)
                            if ('Invalid input' not in error_msg and 
                                'query with more than one statement' not in error_msg):
                                logger.warning(f"Failed to migrate node {i} (uuid: {node_uuid}): {error_msg}")
                            break
                        else:
                            await asyncio.sleep(0.1)  # Brief delay before retry
                
                # Update progress periodically
                if (i + 1) % self.config.batch_progress_interval == 0:
                    self._update_progress(migrated_nodes=node_count)
                    logger.debug(f"Migrated {i + 1}/{len(nodes)} nodes...")
                    
            except Exception as e:
                logger.warning(f"Unexpected error processing node {i}: {e}")
        
        # Final progress update for nodes
        self.progress.migrated_nodes = node_count
        self.progress.total_nodes = len(nodes)
        self._update_progress()
        
        # Store node UUID map for relationship migration
        self._node_uuid_map = node_uuid_map
        
        success_rate = (node_count / len(nodes)) * 100 if nodes else 0
        logger.info(f"Node migration completed: {node_count}/{len(nodes)} ({success_rate:.1f}% success rate)")
    
    async def _migrate_relationships(self):
        """Migrate relationships from Neo4j to FalkorDB."""
        if not hasattr(self, '_node_uuid_map') or not self._node_uuid_map:
            logger.info("No successfully migrated nodes found, skipping relationships")
            return
        
        logger.info("Fetching relationships from Neo4j...")
        
        # Get all relationships between migrated nodes
        rels_query = """
        MATCH (s)-[r]->(t) 
        WHERE s.uuid IS NOT NULL AND t.uuid IS NOT NULL
        RETURN s.uuid as source_uuid, t.uuid as target_uuid, type(r) as rel_type, properties(r) as props
        """
        
        try:
            async with self.neo4j_driver.session() as session:
                rels_result = await session.run(rels_query)
                relationships = await rels_result.data()
            
            self.progress.total_relationships = len(relationships)
            self._update_progress()
            
            logger.info(f"Found {len(relationships)} relationships to migrate")
            
            rel_count = 0
            
            for i, record in enumerate(relationships):
                if self._cancelled:
                    logger.info("Migration cancelled by user")
                    break
                
                try:
                    source_uuid = record['source_uuid']
                    target_uuid = record['target_uuid']
                    rel_type = record['rel_type']
                    props = record['props']
                    
                    # Format properties for Cypher with filtering
                    prop_list = []
                    if props:
                        for key, value in props.items():
                            if self._should_skip_property(key, value):
                                continue
                            try:
                                formatted_value = self._format_value(value)
                                prop_list.append(f"{key}: {formatted_value}")
                            except Exception as e:
                                logger.debug(f"Failed to format relationship property {key}: {e}")
                    
                    prop_string = "{" + ", ".join(prop_list) + "}" if prop_list else ""
                    
                    # Relationship creation with retry logic
                    success = False
                    for attempt in range(self.config.retry_attempts):
                        try:
                            rel_query = f"""
                            MATCH (s {{uuid: '{self._escape_string(source_uuid)}'}}), (t {{uuid: '{self._escape_string(target_uuid)}'}}) 
                            CREATE (s)-[:{rel_type} {prop_string}]->(t)
                            """
                            
                            # Check query length
                            if self._estimate_query_length(rel_query) > self.config.max_query_length:
                                # Simplify by removing properties
                                rel_query = f"""
                                MATCH (s {{uuid: '{self._escape_string(source_uuid)}'}}), (t {{uuid: '{self._escape_string(target_uuid)}'}}) 
                                CREATE (s)-[:{rel_type}]->(t)
                                """
                            
                            self.falkor_graph.query(rel_query)
                            rel_count += 1
                            success = True
                            break
                            
                        except Exception as e:
                            if attempt == self.config.retry_attempts - 1:
                                error_msg = str(e)
                                if 'Invalid input' not in error_msg:
                                    logger.debug(f"Failed to migrate relationship {i} ({source_uuid} -> {target_uuid}): {error_msg}")
                                break
                            else:
                                await asyncio.sleep(0.1)
                    
                    # Update progress periodically
                    if (i + 1) % self.config.batch_progress_interval == 0:
                        self._update_progress(migrated_relationships=rel_count)
                        logger.debug(f"Migrated {i + 1}/{len(relationships)} relationships...")
                        
                except Exception as e:
                    logger.warning(f"Unexpected error processing relationship {i}: {e}")
            
            # Final progress update for relationships
            self.progress.migrated_relationships = rel_count
            self._update_progress()
            
            rel_success_rate = (rel_count / len(relationships)) * 100 if relationships else 0
            logger.info(f"Relationship migration completed: {rel_count}/{len(relationships)} ({rel_success_rate:.1f}% success rate)")
            
        except Exception as e:
            logger.error(f"Error fetching relationships: {e}")
            self.progress.errors.append(f"Relationship migration failed: {e}")
    
    async def _verify_migration(self):
        """Verify the migration results."""
        logger.info("Verifying migration results...")
        
        try:
            # Count nodes and relationships in FalkorDB
            node_result = self.falkor_graph.query('MATCH (n) RETURN count(n) as count')
            falkor_nodes = node_result.result_set[0][0] if node_result.result_set else 0
            
            rel_result = self.falkor_graph.query('MATCH ()-[r]->() RETURN count(r) as count')
            falkor_rels = rel_result.result_set[0][0] if rel_result.result_set else 0
            
            # Sample nodes for verification
            sample_result = self.falkor_graph.query('MATCH (n) RETURN n.name, labels(n) LIMIT 10')
            sample_nodes = []
            if sample_result.result_set:
                for row in sample_result.result_set:
                    if row[0]:  # If name exists
                        sample_nodes.append(f"{row[0]} ({row[1]})")
            
            logger.info(
                f"Verification complete - FalkorDB contains: "
                f"{falkor_nodes} nodes, {falkor_rels} relationships"
            )
            
            if sample_nodes:
                logger.info(f"Sample migrated nodes: {', '.join(sample_nodes[:5])}")
            
        except Exception as e:
            logger.warning(f"Migration verification failed: {e}")
            self.progress.errors.append(f"Verification failed: {e}")
    
    def cancel_migration(self):
        """Cancel the ongoing migration."""
        self._cancelled = True
        logger.info("Migration cancellation requested")
        
    def get_progress(self) -> MigrationProgress:
        """Get current migration progress."""
        return self.progress