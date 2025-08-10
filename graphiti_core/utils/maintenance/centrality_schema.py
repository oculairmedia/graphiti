"""
Versioned centrality schema with API compatibility and migration support.

This module provides a robust schema versioning system for centrality metrics with:
- Schema version tracking and evolution
- Backward compatibility guarantees
- Automated migration between versions
- API version negotiation
- Zero-downtime schema updates
"""

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple, Any, Protocol
from abc import ABC, abstractmethod

from graphiti_core.driver.driver import GraphDriver

logger = logging.getLogger(__name__)


class SchemaVersion(Enum):
    """Centrality schema versions with semantic versioning."""
    V1_0_0 = "1.0.0"  # Initial: pagerank, degree, betweenness
    V1_1_0 = "1.1.0"  # Added: importance composite score
    V1_2_0 = "1.2.0"  # Added: eigenvector centrality
    V2_0_0 = "2.0.0"  # Breaking: New normalized format
    V2_1_0 = "2.1.0"  # Added: closeness centrality
    V2_2_0 = "2.2.0"  # Added: harmonic centrality
    
    @classmethod
    def latest(cls) -> "SchemaVersion":
        """Get the latest schema version."""
        return cls.V2_2_0
    
    @classmethod
    def from_string(cls, version: str) -> "SchemaVersion":
        """Parse version string to SchemaVersion."""
        for v in cls:
            if v.value == version:
                return v
        raise ValueError(f"Unknown schema version: {version}")
    
    def is_compatible_with(self, other: "SchemaVersion") -> bool:
        """Check if this version is compatible with another."""
        # Same major version = compatible
        self_major = int(self.value.split(".")[0])
        other_major = int(other.value.split(".")[0])
        return self_major == other_major


@dataclass
class MetricDefinition:
    """Definition of a centrality metric."""
    name: str
    display_name: str
    description: str
    data_type: str  # "float", "int", "normalized"
    range_min: Optional[float] = None
    range_max: Optional[float] = None
    normalize: bool = False
    introduced_in: SchemaVersion = SchemaVersion.V1_0_0
    deprecated_in: Optional[SchemaVersion] = None
    compute_function: Optional[str] = None  # Function name for computation


@dataclass
class CentralitySchema:
    """
    Versioned schema for centrality metrics.
    
    Defines the structure, validation rules, and compatibility
    for different versions of centrality metrics.
    """
    version: SchemaVersion
    metrics: Dict[str, MetricDefinition]
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    
    @classmethod
    def get_schema(cls, version: SchemaVersion) -> "CentralitySchema":
        """Get schema definition for a specific version."""
        schemas = {
            SchemaVersion.V1_0_0: cls._schema_v1_0_0(),
            SchemaVersion.V1_1_0: cls._schema_v1_1_0(),
            SchemaVersion.V1_2_0: cls._schema_v1_2_0(),
            SchemaVersion.V2_0_0: cls._schema_v2_0_0(),
            SchemaVersion.V2_1_0: cls._schema_v2_1_0(),
            SchemaVersion.V2_2_0: cls._schema_v2_2_0(),
        }
        return schemas[version]
    
    @classmethod
    def _schema_v1_0_0(cls) -> "CentralitySchema":
        """Initial schema with basic metrics."""
        return cls(
            version=SchemaVersion.V1_0_0,
            metrics={
                "pagerank": MetricDefinition(
                    name="pagerank",
                    display_name="PageRank",
                    description="Importance based on incoming links",
                    data_type="float",
                    range_min=0.0,
                    range_max=1.0,
                ),
                "degree": MetricDefinition(
                    name="degree",
                    display_name="Degree Centrality",
                    description="Number of connections",
                    data_type="int",
                    range_min=0,
                ),
                "betweenness": MetricDefinition(
                    name="betweenness",
                    display_name="Betweenness Centrality",
                    description="Frequency on shortest paths",
                    data_type="float",
                    range_min=0.0,
                    range_max=1.0,
                ),
            },
        )
    
    @classmethod
    def _schema_v1_1_0(cls) -> "CentralitySchema":
        """Added importance composite score."""
        schema = cls._schema_v1_0_0()
        schema.version = SchemaVersion.V1_1_0
        schema.metrics["importance"] = MetricDefinition(
            name="importance",
            display_name="Importance Score",
            description="Composite importance metric",
            data_type="float",
            range_min=0.0,
            introduced_in=SchemaVersion.V1_1_0,
        )
        return schema
    
    @classmethod
    def _schema_v1_2_0(cls) -> "CentralitySchema":
        """Added eigenvector centrality."""
        schema = cls._schema_v1_1_0()
        schema.version = SchemaVersion.V1_2_0
        schema.metrics["eigenvector"] = MetricDefinition(
            name="eigenvector",
            display_name="Eigenvector Centrality",
            description="Importance of connections",
            data_type="float",
            range_min=0.0,
            range_max=1.0,
            introduced_in=SchemaVersion.V1_2_0,
        )
        return schema
    
    @classmethod
    def _schema_v2_0_0(cls) -> "CentralitySchema":
        """Breaking change: normalized format."""
        return cls(
            version=SchemaVersion.V2_0_0,
            metrics={
                "pagerank": MetricDefinition(
                    name="pagerank",
                    display_name="PageRank",
                    description="Normalized PageRank score",
                    data_type="normalized",
                    range_min=0.0,
                    range_max=1.0,
                    normalize=True,
                ),
                "degree": MetricDefinition(
                    name="degree",
                    display_name="Degree Centrality",
                    description="Normalized degree centrality",
                    data_type="normalized",
                    range_min=0.0,
                    range_max=1.0,
                    normalize=True,
                ),
                "betweenness": MetricDefinition(
                    name="betweenness",
                    display_name="Betweenness Centrality",
                    description="Normalized betweenness",
                    data_type="normalized",
                    range_min=0.0,
                    range_max=1.0,
                    normalize=True,
                ),
                "eigenvector": MetricDefinition(
                    name="eigenvector",
                    display_name="Eigenvector Centrality",
                    description="Normalized eigenvector",
                    data_type="normalized",
                    range_min=0.0,
                    range_max=1.0,
                    normalize=True,
                ),
            },
            metadata={"breaking_change": True},
        )
    
    @classmethod
    def _schema_v2_1_0(cls) -> "CentralitySchema":
        """Added closeness centrality."""
        schema = cls._schema_v2_0_0()
        schema.version = SchemaVersion.V2_1_0
        schema.metrics["closeness"] = MetricDefinition(
            name="closeness",
            display_name="Closeness Centrality",
            description="Average distance to all nodes",
            data_type="normalized",
            range_min=0.0,
            range_max=1.0,
            normalize=True,
            introduced_in=SchemaVersion.V2_1_0,
        )
        return schema
    
    @classmethod
    def _schema_v2_2_0(cls) -> "CentralitySchema":
        """Added harmonic centrality."""
        schema = cls._schema_v2_1_0()
        schema.version = SchemaVersion.V2_2_0
        schema.metrics["harmonic"] = MetricDefinition(
            name="harmonic",
            display_name="Harmonic Centrality",
            description="Sum of reciprocal distances",
            data_type="normalized",
            range_min=0.0,
            range_max=1.0,
            normalize=True,
            introduced_in=SchemaVersion.V2_2_0,
        )
        return schema
    
    def get_new_metrics(self, from_version: SchemaVersion) -> List[MetricDefinition]:
        """Get metrics added since a specific version."""
        new_metrics = []
        for metric in self.metrics.values():
            if metric.introduced_in.value > from_version.value:
                new_metrics.append(metric)
        return new_metrics
    
    def get_deprecated_metrics(self) -> List[MetricDefinition]:
        """Get deprecated metrics in this version."""
        return [m for m in self.metrics.values() if m.deprecated_in is not None]
    
    def validate_scores(self, scores: Dict[str, float]) -> Tuple[bool, List[str]]:
        """
        Validate scores against schema.
        
        Returns:
            Tuple of (is_valid, error_messages)
        """
        errors = []
        
        for metric_name, value in scores.items():
            if metric_name not in self.metrics:
                errors.append(f"Unknown metric: {metric_name}")
                continue
            
            metric = self.metrics[metric_name]
            
            # Type validation
            if metric.data_type in ("float", "normalized"):
                if not isinstance(value, (int, float)):
                    errors.append(f"{metric_name}: Expected number, got {type(value)}")
            elif metric.data_type == "int":
                if not isinstance(value, int):
                    errors.append(f"{metric_name}: Expected integer, got {type(value)}")
            
            # Range validation
            if metric.range_min is not None and value < metric.range_min:
                errors.append(f"{metric_name}: Value {value} below minimum {metric.range_min}")
            if metric.range_max is not None and value > metric.range_max:
                errors.append(f"{metric_name}: Value {value} above maximum {metric.range_max}")
        
        return len(errors) == 0, errors


class SchemaMigration(ABC):
    """Abstract base class for schema migrations."""
    
    @property
    @abstractmethod
    def from_version(self) -> SchemaVersion:
        """Source schema version."""
        pass
    
    @property
    @abstractmethod
    def to_version(self) -> SchemaVersion:
        """Target schema version."""
        pass
    
    @abstractmethod
    async def migrate_node(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """Migrate a single node's centrality data."""
        pass
    
    @abstractmethod
    async def validate_migration(self, node_data: Dict[str, Any]) -> bool:
        """Validate migrated data."""
        pass
    
    async def pre_migration(self, driver: GraphDriver) -> None:
        """Hook for pre-migration setup."""
        pass
    
    async def post_migration(self, driver: GraphDriver) -> None:
        """Hook for post-migration cleanup."""
        pass


class MigrationV1ToV2(SchemaMigration):
    """Migration from v1.x to v2.x (normalization)."""
    
    @property
    def from_version(self) -> SchemaVersion:
        return SchemaVersion.V1_2_0
    
    @property
    def to_version(self) -> SchemaVersion:
        return SchemaVersion.V2_0_0
    
    def __init__(self, total_nodes: int):
        self.total_nodes = total_nodes
    
    async def migrate_node(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize centrality values."""
        migrated = node_data.copy()
        
        # Normalize degree (was raw count, now 0-1)
        if "degree" in migrated and self.total_nodes > 1:
            migrated["degree"] = migrated["degree"] / (self.total_nodes - 1)
        
        # PageRank and betweenness already normalized in v1
        # Just ensure they're floats
        for metric in ["pagerank", "betweenness", "eigenvector"]:
            if metric in migrated:
                migrated[metric] = float(migrated[metric])
        
        # Remove importance score (recalculated in v2)
        migrated.pop("importance", None)
        
        return migrated
    
    async def validate_migration(self, node_data: Dict[str, Any]) -> bool:
        """Validate normalized values."""
        for metric in ["pagerank", "degree", "betweenness", "eigenvector"]:
            if metric in node_data:
                value = node_data[metric]
                if not (0.0 <= value <= 1.0):
                    return False
        return True


class SchemaManager:
    """
    Manages centrality schema versioning and migrations.
    
    Provides version tracking, compatibility checking,
    and automated migration between schema versions.
    """
    
    def __init__(self, driver: GraphDriver):
        self.driver = driver
        self._current_version: Optional[SchemaVersion] = None
        self._migrations: Dict[Tuple[SchemaVersion, SchemaVersion], SchemaMigration] = {}
        self._register_migrations()
    
    def _register_migrations(self) -> None:
        """Register available migrations."""
        # Register migration from v1 to v2
        # Note: We'd need node count for this migration
        # This would be determined at migration time
        pass
    
    async def get_current_version(self) -> Optional[SchemaVersion]:
        """Get current schema version from the database."""
        if self._current_version:
            return self._current_version
        
        query = """
        MATCH (s:CentralitySchemaVersion)
        RETURN s.version AS version
        ORDER BY s.created_at DESC
        LIMIT 1
        """
        
        records, _, _ = await self.driver.execute_query(query)
        
        if records:
            version_str = records[0]["version"]
            self._current_version = SchemaVersion.from_string(version_str)
            return self._current_version
        
        return None
    
    async def set_version(self, version: SchemaVersion) -> None:
        """Set the current schema version."""
        query = """
        CREATE (s:CentralitySchemaVersion {
            version: $version,
            created_at: $created_at,
            is_current: true
        })
        WITH s
        MATCH (old:CentralitySchemaVersion {is_current: true})
        WHERE old <> s
        SET old.is_current = false
        """
        
        await self.driver.execute_query(
            query,
            version=version.value,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        
        self._current_version = version
        logger.info(f"Schema version set to {version.value}")
    
    async def initialize_schema(self, version: Optional[SchemaVersion] = None) -> None:
        """Initialize schema for first use."""
        if version is None:
            version = SchemaVersion.latest()
        
        current = await self.get_current_version()
        if current:
            logger.warning(f"Schema already initialized at version {current.value}")
            return
        
        await self.set_version(version)
        
        # Create indices for centrality metrics
        schema = CentralitySchema.get_schema(version)
        await self._create_indices(schema)
        
        logger.info(f"Schema initialized at version {version.value}")
    
    async def _create_indices(self, schema: CentralitySchema) -> None:
        """Create database indices for schema metrics."""
        for metric_name in schema.metrics:
            try:
                query = f"""
                CREATE INDEX IF NOT EXISTS 
                FOR (n:EntityNode) 
                ON (n.centrality_{metric_name})
                """
                await self.driver.execute_query(query)
            except Exception as e:
                logger.debug(f"Index creation note for {metric_name}: {e}")
    
    async def migrate_to_version(
        self,
        target_version: SchemaVersion,
        batch_size: int = 100,
    ) -> Dict[str, Any]:
        """
        Migrate schema to a target version.
        
        Args:
            target_version: Target schema version
            batch_size: Nodes to process per batch
        
        Returns:
            Migration statistics
        """
        current = await self.get_current_version()
        if not current:
            raise RuntimeError("No current schema version found")
        
        if current == target_version:
            logger.info("Already at target version")
            return {"status": "no_change", "version": current.value}
        
        # Check compatibility
        if not self._can_migrate(current, target_version):
            raise ValueError(f"Cannot migrate from {current.value} to {target_version.value}")
        
        # Get migration path
        migration_path = self._get_migration_path(current, target_version)
        
        stats = {
            "from_version": current.value,
            "to_version": target_version.value,
            "migrations": len(migration_path),
            "nodes_migrated": 0,
            "errors": [],
        }
        
        # Execute migrations in sequence
        for from_v, to_v in migration_path:
            migration_stats = await self._execute_migration(from_v, to_v, batch_size)
            stats["nodes_migrated"] += migration_stats["nodes_migrated"]
            stats["errors"].extend(migration_stats.get("errors", []))
        
        # Update current version
        await self.set_version(target_version)
        
        # Create new indices
        schema = CentralitySchema.get_schema(target_version)
        await self._create_indices(schema)
        
        logger.info(f"Migration complete: {stats}")
        return stats
    
    def _can_migrate(self, from_v: SchemaVersion, to_v: SchemaVersion) -> bool:
        """Check if migration is possible."""
        # Can always migrate within same major version
        if from_v.is_compatible_with(to_v):
            return True
        
        # Check if explicit migration exists
        return (from_v, to_v) in self._migrations
    
    def _get_migration_path(
        self,
        from_v: SchemaVersion,
        to_v: SchemaVersion,
    ) -> List[Tuple[SchemaVersion, SchemaVersion]]:
        """Get migration path between versions."""
        # For now, simple direct migration
        # In production, would calculate shortest path
        return [(from_v, to_v)]
    
    async def _execute_migration(
        self,
        from_v: SchemaVersion,
        to_v: SchemaVersion,
        batch_size: int,
    ) -> Dict[str, Any]:
        """Execute a single migration."""
        logger.info(f"Migrating from {from_v.value} to {to_v.value}")
        
        # Get node count for migration setup
        count_query = "MATCH (n:EntityNode) RETURN count(n) AS count"
        count_records, _, _ = await self.driver.execute_query(count_query)
        total_nodes = count_records[0]["count"] if count_records else 0
        
        # Create migration instance
        if from_v.value.startswith("1.") and to_v.value.startswith("2."):
            migration = MigrationV1ToV2(total_nodes)
        else:
            # Default compatible migration (same major version)
            migration = CompatibleMigration(from_v, to_v)
        
        # Pre-migration hook
        await migration.pre_migration(self.driver)
        
        # Migrate nodes in batches
        stats = {"nodes_migrated": 0, "errors": []}
        
        query = """
        MATCH (n:EntityNode)
        RETURN n.uuid AS uuid,
               n.centrality_pagerank AS pagerank,
               n.centrality_degree AS degree,
               n.centrality_betweenness AS betweenness,
               n.centrality_eigenvector AS eigenvector,
               n.centrality_importance AS importance
        """
        
        records, _, _ = await self.driver.execute_query(query)
        
        for i in range(0, len(records), batch_size):
            batch = records[i:i + batch_size]
            
            for record in batch:
                try:
                    # Extract current data
                    node_data = {
                        k: v for k, v in record.items()
                        if k != "uuid" and v is not None
                    }
                    
                    # Migrate
                    migrated = await migration.migrate_node(node_data)
                    
                    # Validate
                    if not await migration.validate_migration(migrated):
                        stats["errors"].append(f"Validation failed for {record['uuid']}")
                        continue
                    
                    # Update node
                    await self._update_node_metrics(record["uuid"], migrated)
                    stats["nodes_migrated"] += 1
                    
                except Exception as e:
                    stats["errors"].append(f"Error migrating {record['uuid']}: {e}")
        
        # Post-migration hook
        await migration.post_migration(self.driver)
        
        return stats
    
    async def _update_node_metrics(self, node_uuid: str, metrics: Dict[str, Any]) -> None:
        """Update node with migrated metrics."""
        set_clauses = []
        params = {"uuid": node_uuid}
        
        for metric_name, value in metrics.items():
            set_clauses.append(f"n.centrality_{metric_name} = ${metric_name}")
            params[metric_name] = value
        
        if set_clauses:
            query = f"""
            MATCH (n {{uuid: $uuid}})
            SET {', '.join(set_clauses)},
                n.centrality_schema_version = '{self._current_version.value}'
            """
            await self.driver.execute_query(query, **params)


class CompatibleMigration(SchemaMigration):
    """Migration between compatible versions (same major)."""
    
    def __init__(self, from_v: SchemaVersion, to_v: SchemaVersion):
        self._from = from_v
        self._to = to_v
    
    @property
    def from_version(self) -> SchemaVersion:
        return self._from
    
    @property
    def to_version(self) -> SchemaVersion:
        return self._to
    
    async def migrate_node(self, node_data: Dict[str, Any]) -> Dict[str, Any]:
        """Compatible migration - no data transformation needed."""
        return node_data
    
    async def validate_migration(self, node_data: Dict[str, Any]) -> bool:
        """Always valid for compatible versions."""
        return True


class APIVersionNegotiator:
    """
    Handles API version negotiation for centrality endpoints.
    
    Provides backward compatibility and version-specific
    response formatting.
    """
    
    def __init__(self, schema_manager: SchemaManager):
        self.schema_manager = schema_manager
    
    async def negotiate_version(
        self,
        requested_version: Optional[str],
        accept_header: Optional[str] = None,
    ) -> SchemaVersion:
        """
        Negotiate API version based on request.
        
        Args:
            requested_version: Explicit version request
            accept_header: Accept header with version
        
        Returns:
            Negotiated schema version
        """
        current = await self.schema_manager.get_current_version()
        if not current:
            current = SchemaVersion.latest()
        
        # Explicit version request
        if requested_version:
            try:
                requested = SchemaVersion.from_string(requested_version)
                if requested.is_compatible_with(current):
                    return requested
                else:
                    logger.warning(
                        f"Incompatible version {requested_version}, using {current.value}"
                    )
            except ValueError:
                logger.warning(f"Unknown version {requested_version}, using {current.value}")
        
        # Parse Accept header (e.g., "application/vnd.centrality.v2+json")
        if accept_header and "vnd.centrality" in accept_header:
            import re
            match = re.search(r"v(\d+)", accept_header)
            if match:
                major = match.group(1)
                # Find latest version with this major number
                for v in SchemaVersion:
                    if v.value.startswith(f"{major}."):
                        if v.is_compatible_with(current):
                            return v
        
        # Default to current version
        return current
    
    def format_response(
        self,
        data: Dict[str, Any],
        version: SchemaVersion,
    ) -> Dict[str, Any]:
        """
        Format response according to API version.
        
        Args:
            data: Raw centrality data
            version: API version to format for
        
        Returns:
            Formatted response
        """
        schema = CentralitySchema.get_schema(version)
        
        # Filter to only include metrics in this version
        filtered_data = {}
        for metric_name in schema.metrics:
            if metric_name in data:
                filtered_data[metric_name] = data[metric_name]
        
        # Add version metadata
        return {
            "version": version.value,
            "data": filtered_data,
            "schema": {
                "metrics": [m.name for m in schema.metrics.values()],
            },
        }