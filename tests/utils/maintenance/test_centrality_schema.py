"""
Tests for versioned centrality schema with migrations.
"""

import pytest
from datetime import datetime, timezone
from unittest.mock import AsyncMock, Mock, patch
from typing import Dict, Any

from graphiti_core.utils.maintenance.centrality_schema import (
    SchemaVersion,
    MetricDefinition,
    CentralitySchema,
    SchemaMigration,
    MigrationV1ToV2,
    SchemaManager,
    APIVersionNegotiator,
    CompatibleMigration,
)
from graphiti_core.driver.driver import GraphDriver


@pytest.fixture
def mock_driver():
    """Create a mock graph driver."""
    driver = AsyncMock(spec=GraphDriver)
    driver.execute_query = AsyncMock()
    return driver


@pytest.fixture
def schema_manager(mock_driver):
    """Create a schema manager instance."""
    return SchemaManager(driver=mock_driver)


@pytest.fixture
def api_negotiator(schema_manager):
    """Create an API version negotiator."""
    return APIVersionNegotiator(schema_manager)


class TestSchemaVersion:
    """Test schema version enum and methods."""
    
    def test_latest_version(self):
        """Test getting latest version."""
        latest = SchemaVersion.latest()
        assert latest == SchemaVersion.V2_2_0
    
    def test_from_string(self):
        """Test parsing version from string."""
        version = SchemaVersion.from_string("1.0.0")
        assert version == SchemaVersion.V1_0_0
        
        version = SchemaVersion.from_string("2.2.0")
        assert version == SchemaVersion.V2_2_0
        
        with pytest.raises(ValueError):
            SchemaVersion.from_string("99.99.99")
    
    def test_compatibility(self):
        """Test version compatibility checking."""
        # Same major version = compatible
        assert SchemaVersion.V1_0_0.is_compatible_with(SchemaVersion.V1_1_0)
        assert SchemaVersion.V1_1_0.is_compatible_with(SchemaVersion.V1_2_0)
        assert SchemaVersion.V2_0_0.is_compatible_with(SchemaVersion.V2_1_0)
        
        # Different major version = incompatible
        assert not SchemaVersion.V1_0_0.is_compatible_with(SchemaVersion.V2_0_0)
        assert not SchemaVersion.V1_2_0.is_compatible_with(SchemaVersion.V2_1_0)


class TestCentralitySchema:
    """Test centrality schema definitions."""
    
    def test_get_schema_v1_0_0(self):
        """Test initial schema."""
        schema = CentralitySchema.get_schema(SchemaVersion.V1_0_0)
        
        assert schema.version == SchemaVersion.V1_0_0
        assert len(schema.metrics) == 3
        assert "pagerank" in schema.metrics
        assert "degree" in schema.metrics
        assert "betweenness" in schema.metrics
        
        # Check metric properties
        pagerank = schema.metrics["pagerank"]
        assert pagerank.data_type == "float"
        assert pagerank.range_min == 0.0
        assert pagerank.range_max == 1.0
    
    def test_get_schema_v2_0_0(self):
        """Test v2 schema with normalization."""
        schema = CentralitySchema.get_schema(SchemaVersion.V2_0_0)
        
        assert schema.version == SchemaVersion.V2_0_0
        assert len(schema.metrics) == 4  # Added eigenvector
        
        # All metrics should be normalized
        for metric in schema.metrics.values():
            assert metric.data_type == "normalized"
            assert metric.normalize is True
        
        # Check breaking change flag
        assert schema.metadata.get("breaking_change") is True
    
    def test_get_new_metrics(self):
        """Test getting new metrics since a version."""
        schema = CentralitySchema.get_schema(SchemaVersion.V2_2_0)
        
        # Get metrics added since v2.0.0
        new_metrics = schema.get_new_metrics(SchemaVersion.V2_0_0)
        
        assert len(new_metrics) == 2  # closeness and harmonic
        metric_names = [m.name for m in new_metrics]
        assert "closeness" in metric_names
        assert "harmonic" in metric_names
    
    def test_validate_scores(self):
        """Test score validation against schema."""
        schema = CentralitySchema.get_schema(SchemaVersion.V1_0_0)
        
        # Valid scores
        scores = {
            "pagerank": 0.5,
            "degree": 10,
            "betweenness": 0.3,
        }
        is_valid, errors = schema.validate_scores(scores)
        assert is_valid
        assert len(errors) == 0
        
        # Invalid: out of range
        scores = {"pagerank": 1.5}  # > 1.0
        is_valid, errors = schema.validate_scores(scores)
        assert not is_valid
        assert "above maximum" in errors[0]
        
        # Invalid: wrong type
        scores = {"degree": 10.5}  # Should be int
        is_valid, errors = schema.validate_scores(scores)
        assert not is_valid
        assert "Expected integer" in errors[0]
        
        # Invalid: unknown metric
        scores = {"unknown_metric": 0.5}
        is_valid, errors = schema.validate_scores(scores)
        assert not is_valid
        assert "Unknown metric" in errors[0]


class TestMigrationV1ToV2:
    """Test migration from v1 to v2."""
    
    @pytest.mark.asyncio
    async def test_migrate_node(self):
        """Test node migration with normalization."""
        migration = MigrationV1ToV2(total_nodes=100)
        
        # Input v1 data
        node_data = {
            "pagerank": 0.15,
            "degree": 25,  # Raw count
            "betweenness": 0.08,
            "eigenvector": 0.6,
            "importance": 5.2,  # Should be removed
        }
        
        # Migrate
        migrated = await migration.migrate_node(node_data)
        
        # Check normalization
        assert migrated["pagerank"] == 0.15  # Already normalized
        assert migrated["degree"] == pytest.approx(25 / 99)  # Normalized
        assert migrated["betweenness"] == 0.08  # Already normalized
        assert migrated["eigenvector"] == 0.6  # Already normalized
        assert "importance" not in migrated  # Removed
    
    @pytest.mark.asyncio
    async def test_validate_migration(self):
        """Test migration validation."""
        migration = MigrationV1ToV2(total_nodes=100)
        
        # Valid migrated data
        valid_data = {
            "pagerank": 0.5,
            "degree": 0.3,
            "betweenness": 0.2,
            "eigenvector": 0.7,
        }
        assert await migration.validate_migration(valid_data)
        
        # Invalid: out of range
        invalid_data = {"pagerank": 1.5}
        assert not await migration.validate_migration(invalid_data)


@pytest.mark.asyncio
class TestSchemaManager:
    """Test schema manager functionality."""
    
    async def test_get_current_version_none(self, schema_manager, mock_driver):
        """Test getting version when none exists."""
        mock_driver.execute_query.return_value = ([], None, None)
        
        version = await schema_manager.get_current_version()
        assert version is None
    
    async def test_get_current_version_exists(self, schema_manager, mock_driver):
        """Test getting existing version."""
        mock_driver.execute_query.return_value = (
            [{"version": "2.1.0"}],
            None,
            None,
        )
        
        version = await schema_manager.get_current_version()
        assert version == SchemaVersion.V2_1_0
    
    async def test_set_version(self, schema_manager, mock_driver):
        """Test setting schema version."""
        await schema_manager.set_version(SchemaVersion.V2_0_0)
        
        # Check query was executed
        assert mock_driver.execute_query.called
        call_args = mock_driver.execute_query.call_args
        assert "CentralitySchemaVersion" in call_args[0][0]
        assert call_args[1]["version"] == "2.0.0"
    
    async def test_initialize_schema(self, schema_manager, mock_driver):
        """Test schema initialization."""
        mock_driver.execute_query.return_value = ([], None, None)  # No existing version
        
        await schema_manager.initialize_schema()
        
        # Should set to latest version
        assert mock_driver.execute_query.called
        calls = mock_driver.execute_query.call_args_list
        
        # Check version was set
        version_call = [c for c in calls if "CentralitySchemaVersion" in c[0][0]][0]
        assert version_call[1]["version"] == SchemaVersion.latest().value
    
    async def test_initialize_schema_already_exists(self, schema_manager, mock_driver):
        """Test initialization when schema already exists."""
        # Mock existing version
        mock_driver.execute_query.return_value = (
            [{"version": "1.0.0"}],
            None,
            None,
        )
        
        await schema_manager.initialize_schema()
        
        # Should not set new version (only 1 call to check)
        assert mock_driver.execute_query.call_count == 1
    
    async def test_migrate_to_version_same(self, schema_manager, mock_driver):
        """Test migration to same version."""
        # Set current version
        schema_manager._current_version = SchemaVersion.V2_0_0
        
        result = await schema_manager.migrate_to_version(SchemaVersion.V2_0_0)
        
        assert result["status"] == "no_change"
        assert result["version"] == "2.0.0"
    
    async def test_migrate_to_version_compatible(self, schema_manager, mock_driver):
        """Test migration between compatible versions."""
        # Set current version
        schema_manager._current_version = SchemaVersion.V2_0_0
        
        # Mock node data
        mock_driver.execute_query.side_effect = [
            ([{"count": 10}], None, None),  # Node count
            ([  # Node data
                {
                    "uuid": "node1",
                    "pagerank": 0.5,
                    "degree": 0.3,
                    "betweenness": 0.2,
                    "eigenvector": 0.7,
                    "importance": None,
                }
            ], None, None),
            ([], None, None),  # Update query
            ([], None, None),  # Set version
        ]
        
        result = await schema_manager.migrate_to_version(SchemaVersion.V2_1_0)
        
        assert result["from_version"] == "2.0.0"
        assert result["to_version"] == "2.1.0"
        assert result["nodes_migrated"] == 1
        assert len(result["errors"]) == 0
    
    async def test_migrate_to_version_incompatible(self, schema_manager, mock_driver):
        """Test migration between incompatible versions."""
        # Set current v1
        schema_manager._current_version = SchemaVersion.V1_0_0
        
        # Should fail without explicit migration
        with pytest.raises(ValueError, match="Cannot migrate"):
            await schema_manager.migrate_to_version(SchemaVersion.V2_0_0)


@pytest.mark.asyncio
class TestAPIVersionNegotiator:
    """Test API version negotiation."""
    
    async def test_negotiate_explicit_version(self, api_negotiator, schema_manager, mock_driver):
        """Test explicit version request."""
        schema_manager._current_version = SchemaVersion.V2_2_0
        
        # Request compatible version
        version = await api_negotiator.negotiate_version("2.1.0")
        assert version == SchemaVersion.V2_1_0
        
        # Request incompatible version (falls back to current)
        version = await api_negotiator.negotiate_version("1.0.0")
        assert version == SchemaVersion.V2_2_0
    
    async def test_negotiate_accept_header(self, api_negotiator, schema_manager, mock_driver):
        """Test version from Accept header."""
        schema_manager._current_version = SchemaVersion.V2_2_0
        
        # Accept header with version
        version = await api_negotiator.negotiate_version(
            None,
            "application/vnd.centrality.v2+json"
        )
        # Should return a v2.x version
        assert version.value.startswith("2.")
        
        # No version in header
        version = await api_negotiator.negotiate_version(
            None,
            "application/json"
        )
        assert version == SchemaVersion.V2_2_0
    
    def test_format_response(self, api_negotiator):
        """Test response formatting for different versions."""
        # Raw data with all metrics
        data = {
            "pagerank": 0.5,
            "degree": 0.3,
            "betweenness": 0.2,
            "eigenvector": 0.7,
            "closeness": 0.4,  # Only in v2.1+
            "harmonic": 0.6,   # Only in v2.2+
        }
        
        # Format for v2.0 (should exclude closeness and harmonic)
        response = api_negotiator.format_response(data, SchemaVersion.V2_0_0)
        
        assert response["version"] == "2.0.0"
        assert "pagerank" in response["data"]
        assert "degree" in response["data"]
        assert "closeness" not in response["data"]
        assert "harmonic" not in response["data"]
        
        # Format for v2.2 (should include all)
        response = api_negotiator.format_response(data, SchemaVersion.V2_2_0)
        
        assert response["version"] == "2.2.0"
        assert "closeness" in response["data"]
        assert "harmonic" in response["data"]


class TestCompatibleMigration:
    """Test compatible version migration."""
    
    @pytest.mark.asyncio
    async def test_compatible_migration(self):
        """Test migration between compatible versions."""
        migration = CompatibleMigration(SchemaVersion.V2_0_0, SchemaVersion.V2_1_0)
        
        assert migration.from_version == SchemaVersion.V2_0_0
        assert migration.to_version == SchemaVersion.V2_1_0
        
        # Data passes through unchanged
        data = {"pagerank": 0.5, "degree": 0.3}
        migrated = await migration.migrate_node(data)
        assert migrated == data
        
        # Always valid
        assert await migration.validate_migration(data)