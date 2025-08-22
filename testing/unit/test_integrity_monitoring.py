#!/usr/bin/env python3
"""
Test script for the integrity monitoring service.

This script validates the functionality of the IntegrityMonitoringService
that continuously monitors data integrity and generates alerts.
"""

import asyncio
import os
import sys
from datetime import datetime, timedelta
from unittest.mock import MagicMock, AsyncMock
from uuid import uuid4

# Add the project root to path for imports
sys.path.append('/opt/stacks/graphiti')

from graphiti_core.utils.integrity_monitoring import (
    IntegrityMonitoringService,
    MonitoringAlert,
    MonitoringSeverity,
    MonitoringMetric,
    MonitoringThresholds,
    HealthReport,
    get_monitoring_service,
    run_integrity_check,
    get_monitoring_config
)


def create_mock_driver():
    """Create a mock GraphDriver for testing."""
    driver = MagicMock()
    driver.provider = 'neo4j'
    
    # Create a proper context manager for session
    session = AsyncMock()
    
    # Create a mock context manager
    async def aenter(self):
        return session
    
    async def aexit(self, exc_type, exc_val, exc_tb):
        return None
    
    # Set up the session context manager
    session_cm = AsyncMock()
    session_cm.__aenter__ = aenter
    session_cm.__aexit__ = aexit
    driver.session.return_value = session_cm
    
    # Mock database responses for different queries
    async def mock_run(query, **params):
        result = AsyncMock()
        
        # Create a simple record class to avoid MagicMock issues
        class MockRecord:
            def __init__(self, data):
                self._data = data
            
            def __getitem__(self, key):
                return self._data.get(key, 0)
        
        # Entity count queries
        if 'MATCH (n:Entity) RETURN count(n)' in query:
            mock_record = MockRecord({'count': 1000})
            
        # Edge count queries
        elif 'MATCH ()-[r:RELATES_TO]->' in query and 'count(r)' in query:
            if 'total' in query:
                mock_record = MockRecord({'total': 500})
            else:
                # Orphaned edges query
                sample_ids = [str(uuid4()) for _ in range(3)]
                mock_record = MockRecord({'orphaned': 5, 'sample_edge_ids': sample_ids})
                
        # Invalid centrality query
        elif 'degree_centrality < 0 OR degree_centrality > 1' in query:
            sample_ids = [str(uuid4()) for _ in range(5)]
            mock_record = MockRecord({'invalid_count': 10, 'sample_entity_ids': sample_ids})
            
        # Duplicate entities query
        elif 'WITH n.name as name, collect(n.uuid)' in query:
            sample_groups = [
                [str(uuid4()), str(uuid4())],
                [str(uuid4()), str(uuid4()), str(uuid4())]
            ]
            mock_record = MockRecord({
                'duplicate_groups': 3,
                'duplicate_entities': 8,
                'sample_groups': sample_groups
            })
            
        # Missing embeddings query
        elif 'name_embedding IS NULL' in query:
            sample_ids = [str(uuid4()) for _ in range(5)]
            mock_record = MockRecord({'missing_count': 25, 'sample_entity_ids': sample_ids})
            
        # Total entities for percentages
        elif 'MATCH (n:Entity)' in query and 'total' in query:
            mock_record = MockRecord({'total': 1000})
            
        else:
            mock_record = MockRecord({'count': 0})
            
        result.single.return_value = mock_record
        return result
    
    session.run.side_effect = mock_run
    return driver


async def test_monitoring_service_initialization():
    """Test monitoring service initialization."""
    print("Testing monitoring service initialization...")
    
    # Test default initialization
    service = IntegrityMonitoringService()
    assert service.thresholds is not None, "Should have default thresholds"
    assert service.monitoring_enabled, "Should be enabled by default"
    print("✅ Default initialization works")
    
    # Test with driver
    driver = create_mock_driver()
    service = IntegrityMonitoringService(driver=driver)
    assert service.driver == driver, "Should store driver"
    assert service.post_save_validator is not None, "Should initialize post-save validator"
    print("✅ Driver initialization works")
    
    # Test with custom thresholds
    thresholds = MonitoringThresholds(max_entity_count_change_percent=5.0)
    service = IntegrityMonitoringService(thresholds=thresholds)
    assert service.thresholds.max_entity_count_change_percent == 5.0, "Should use custom thresholds"
    print("✅ Custom thresholds work")


async def test_entity_count_monitoring():
    """Test entity count change monitoring."""
    print("Testing entity count monitoring...")
    
    driver = create_mock_driver()
    service = IntegrityMonitoringService(driver=driver)
    
    # First check should not generate alerts (no historical data)
    alerts = await service.check_entity_count_changes()
    print(f"First check alerts: {len(alerts)}")
    if alerts:
        print(f"First alert: {alerts[0].message}")
    assert len(alerts) == 0, "Should not alert on first check"
    print("✅ First check handles missing history")
    
    # Debug: check what's in historical metrics now
    history = service.historical_metrics[MonitoringMetric.ENTITY_COUNT]
    print(f"Historical data after first check: {history}")
    
    # Second check should detect the same count (no alert)
    alerts = await service.check_entity_count_changes()
    print(f"Second check alerts: {len(alerts)}")
    if alerts:
        print(f"Second alert: {alerts[0].message}")
        print(f"Alert details: {alerts[0].details}")
    
    assert len(alerts) == 0, "Should not alert when count is stable"
    print("✅ Stable count check works")
    
    # Simulate a significant count change by modifying historical data
    # First ensure we have some historical data - let's run one more check to populate it
    await service.check_entity_count_changes()
    
    # Now manually set the historical data to a different value to simulate change
    service.historical_metrics[MonitoringMetric.ENTITY_COUNT] = [{
        'timestamp': datetime.now() - timedelta(minutes=5),
        'value': 100  # Much lower than current count of 1000
    }]
    
    alerts = await service.check_entity_count_changes()
    assert len(alerts) == 1, "Should generate alert for significant change"
    assert alerts[0].severity in [MonitoringSeverity.WARNING, MonitoringSeverity.ERROR], "Should be warning or error"
    assert "Entity count changed by" in alerts[0].message, "Should describe the change"
    print("✅ Significant count change detection works")


async def test_orphaned_edge_detection():
    """Test orphaned edge detection."""
    print("Testing orphaned edge detection...")
    
    driver = create_mock_driver()
    service = IntegrityMonitoringService(driver=driver)
    
    alerts = await service.check_orphaned_edges()
    
    # Should detect orphaned edges (5 out of 500 = 1%)
    assert len(alerts) == 0, "Should not alert when orphaned percentage is below threshold"
    print("✅ Orphaned edges below threshold handled correctly")
    
    # Test with higher threshold to trigger alert
    service.thresholds.max_orphaned_edges_percent = 0.5  # Lower threshold
    alerts = await service.check_orphaned_edges()
    assert len(alerts) == 1, "Should generate alert when orphaned percentage exceeds threshold"
    assert alerts[0].metric == MonitoringMetric.ORPHANED_EDGES, "Should be orphaned edges metric"
    print("✅ Orphaned edges detection works")


async def test_centrality_validation_monitoring():
    """Test centrality validation monitoring."""
    print("Testing centrality validation monitoring...")
    
    driver = create_mock_driver()
    service = IntegrityMonitoringService(driver=driver)
    
    alerts = await service.check_centrality_validity()
    
    # Should detect invalid centrality (10 out of 1000 = 1%)
    assert len(alerts) == 0, "Should not alert when invalid percentage is below threshold"
    print("✅ Invalid centrality below threshold handled correctly")
    
    # Test with higher threshold to trigger alert
    service.thresholds.max_invalid_centrality_percent = 0.5  # Lower threshold
    alerts = await service.check_centrality_validity()
    assert len(alerts) == 1, "Should generate alert when invalid percentage exceeds threshold"
    assert alerts[0].metric == MonitoringMetric.INVALID_CENTRALITY, "Should be invalid centrality metric"
    print("✅ Invalid centrality detection works")


async def test_duplicate_entity_detection():
    """Test duplicate entity detection."""
    print("Testing duplicate entity detection...")
    
    driver = create_mock_driver()
    service = IntegrityMonitoringService(driver=driver)
    
    alerts = await service.check_duplicate_entities()
    
    # Should detect duplicates (8 out of 1000 = 0.8%)
    assert len(alerts) == 1, "Should generate alert for duplicate entities"
    assert alerts[0].metric == MonitoringMetric.DUPLICATE_ENTITIES, "Should be duplicate entities metric"
    assert "duplicate entities" in alerts[0].message.lower(), "Should mention duplicates"
    print("✅ Duplicate entity detection works")


async def test_missing_embeddings_detection():
    """Test missing embeddings detection."""
    print("Testing missing embeddings detection...")
    
    driver = create_mock_driver()
    service = IntegrityMonitoringService(driver=driver)
    
    alerts = await service.check_missing_embeddings()
    
    # Should detect missing embeddings (25 out of 1000 = 2.5%)
    assert len(alerts) == 0, "Should not alert when missing percentage is below threshold"
    print("✅ Missing embeddings below threshold handled correctly")
    
    # Test with higher threshold to trigger alert
    service.thresholds.max_missing_embeddings_percent = 2.0  # Lower threshold
    alerts = await service.check_missing_embeddings()
    assert len(alerts) == 1, "Should generate alert when missing percentage exceeds threshold"
    assert alerts[0].metric == MonitoringMetric.MISSING_EMBEDDINGS, "Should be missing embeddings metric"
    print("✅ Missing embeddings detection works")


async def test_full_monitoring_cycle():
    """Test complete monitoring cycle."""
    print("Testing full monitoring cycle...")
    
    driver = create_mock_driver()
    service = IntegrityMonitoringService(driver=driver)
    
    # Adjust thresholds to trigger some alerts
    service.thresholds.max_duplicate_entities_percent = 0.5
    service.thresholds.max_missing_embeddings_percent = 2.0
    service.thresholds.max_orphaned_edges_percent = 0.5
    service.thresholds.max_invalid_centrality_percent = 0.5
    
    health_report = await service.run_monitoring_cycle()
    
    assert isinstance(health_report, HealthReport), "Should return HealthReport"
    assert health_report.overall_health in ['healthy', 'warning', 'error', 'critical'], "Should have valid health status"
    assert health_report.total_alerts >= 0, "Should have non-negative alert count"
    print(f"✅ Full monitoring cycle works - Health: {health_report.overall_health}, Alerts: {health_report.total_alerts}")


async def test_alert_management():
    """Test alert creation, resolution, and filtering."""
    print("Testing alert management...")
    
    service = IntegrityMonitoringService()
    
    # Create test alerts
    alert1 = MonitoringAlert(
        id="test_alert_1",
        timestamp=datetime.now(),
        severity=MonitoringSeverity.WARNING,
        metric=MonitoringMetric.ENTITY_COUNT,
        message="Test warning alert"
    )
    
    alert2 = MonitoringAlert(
        id="test_alert_2",
        timestamp=datetime.now(),
        severity=MonitoringSeverity.ERROR,
        metric=MonitoringMetric.ORPHANED_EDGES,
        message="Test error alert"
    )
    
    service.alerts = [alert1, alert2]
    
    # Test getting active alerts
    active_alerts = service.get_active_alerts()
    assert len(active_alerts) == 2, "Should have 2 active alerts"
    print("✅ Active alerts retrieval works")
    
    # Test filtering by severity
    error_alerts = service.get_active_alerts(MonitoringSeverity.ERROR)
    assert len(error_alerts) == 1, "Should have 1 error alert"
    assert error_alerts[0].severity == MonitoringSeverity.ERROR, "Should be error severity"
    print("✅ Alert filtering by severity works")
    
    # Test alert resolution
    resolved = service.resolve_alert("test_alert_1", "Test resolution")
    assert resolved, "Should successfully resolve alert"
    assert alert1.resolved, "Alert should be marked as resolved"
    assert alert1.resolution_timestamp is not None, "Should have resolution timestamp"
    print("✅ Alert resolution works")
    
    # Test active alerts after resolution
    active_alerts = service.get_active_alerts()
    assert len(active_alerts) == 1, "Should have 1 active alert after resolution"
    print("✅ Alert management after resolution works")


async def test_health_summary():
    """Test health summary generation."""
    print("Testing health summary...")
    
    service = IntegrityMonitoringService()
    
    # Create test alerts of different severities
    alerts = [
        MonitoringAlert("crit1", datetime.now(), MonitoringSeverity.CRITICAL, MonitoringMetric.ENTITY_COUNT, "Critical alert"),
        MonitoringAlert("err1", datetime.now(), MonitoringSeverity.ERROR, MonitoringMetric.ORPHANED_EDGES, "Error alert"),
        MonitoringAlert("warn1", datetime.now(), MonitoringSeverity.WARNING, MonitoringMetric.DUPLICATE_ENTITIES, "Warning alert"),
        MonitoringAlert("warn2", datetime.now(), MonitoringSeverity.WARNING, MonitoringMetric.MISSING_EMBEDDINGS, "Another warning")
    ]
    
    service.alerts = alerts
    
    summary = service.get_health_summary()
    
    assert 'health_score' in summary, "Should have health score"
    assert 'overall_status' in summary, "Should have overall status"
    assert 'severity_breakdown' in summary, "Should have severity breakdown"
    
    assert summary['severity_breakdown']['critical'] == 1, "Should count critical alerts"
    assert summary['severity_breakdown']['error'] == 1, "Should count error alerts"
    assert summary['severity_breakdown']['warning'] == 2, "Should count warning alerts"
    
    # Health score should be reduced due to alerts
    assert summary['health_score'] < 100, "Health score should be reduced with active alerts"
    assert summary['overall_status'] in ['critical', 'error', 'warning'], "Should reflect alert severity"
    
    print(f"✅ Health summary works - Score: {summary['health_score']}, Status: {summary['overall_status']}")


async def test_custom_checks():
    """Test custom monitoring check registration."""
    print("Testing custom monitoring checks...")
    
    service = IntegrityMonitoringService()
    
    # Create a custom check function
    async def custom_check():
        return [MonitoringAlert(
            id="custom_check_alert",
            timestamp=datetime.now(),
            severity=MonitoringSeverity.INFO,
            metric=MonitoringMetric.VALIDATION_ERRORS,
            message="Custom check alert"
        )]
    
    # Register the custom check
    service.register_custom_check("test_check", custom_check)
    assert "test_check" in service.custom_checks, "Should register custom check"
    print("✅ Custom check registration works")
    
    # Test that custom check is executed during monitoring cycle
    health_report = await service.run_monitoring_cycle()
    
    # Check if custom alert was generated
    custom_alerts = [alert for alert in health_report.alerts if alert.id == "custom_check_alert"]
    assert len(custom_alerts) == 1, "Should execute custom check and generate alert"
    print("✅ Custom check execution works")


async def test_configuration():
    """Test monitoring configuration."""
    print("Testing configuration...")
    
    # Test environment-based thresholds
    os.environ['MONITORING_MAX_ENTITY_COUNT_CHANGE_PERCENT'] = '15.0'
    os.environ['MONITORING_MAX_ORPHANED_EDGES_PERCENT'] = '2.5'
    
    try:
        thresholds = MonitoringThresholds.from_environment()
        assert thresholds.max_entity_count_change_percent == 15.0, "Should load entity count threshold from env"
        assert thresholds.max_orphaned_edges_percent == 2.5, "Should load orphaned edges threshold from env"
        print("✅ Environment threshold loading works")
        
    finally:
        # Clean up environment
        os.environ.pop('MONITORING_MAX_ENTITY_COUNT_CHANGE_PERCENT', None)
        os.environ.pop('MONITORING_MAX_ORPHANED_EDGES_PERCENT', None)
    
    # Test monitoring configuration
    config = get_monitoring_config()
    assert 'enabled' in config, "Should have enabled setting"
    assert 'interval_seconds' in config, "Should have interval setting"
    assert 'thresholds' in config, "Should have thresholds"
    print("✅ Monitoring configuration works")


async def test_global_service():
    """Test global monitoring service."""
    print("Testing global service...")
    
    driver = create_mock_driver()
    
    # Test global service access
    service1 = get_monitoring_service(driver=driver)
    service2 = get_monitoring_service(driver=driver)
    
    assert service1 is service2, "Should return same instance (singleton)"
    print("✅ Global service singleton works")
    
    # Test convenience function
    health_report = await run_integrity_check(driver)
    assert isinstance(health_report, HealthReport), "Should return HealthReport"
    print("✅ Convenience function works")


async def test_error_handling():
    """Test error handling in monitoring service."""
    print("Testing error handling...")
    
    # Create a driver that raises exceptions
    error_driver = MagicMock()
    error_session = AsyncMock()
    error_session.run.side_effect = Exception("Database connection failed")
    error_driver.session.return_value = error_session
    
    service = IntegrityMonitoringService(driver=error_driver)
    
    # Test that monitoring continues despite database errors
    alerts = await service.check_entity_count_changes()
    assert len(alerts) == 1, "Should generate error alert"
    assert alerts[0].severity == MonitoringSeverity.ERROR, "Should be error severity"
    assert "Failed to check entity count" in alerts[0].message, "Should describe the error"
    print("✅ Database error handling works")
    
    # Test error handling in full monitoring cycle
    health_report = await service.run_monitoring_cycle()
    assert isinstance(health_report, HealthReport), "Should return report despite errors"
    assert health_report.total_alerts > 0, "Should have error alerts"
    print("✅ Monitoring cycle error handling works")


async def run_all_tests():
    """Run all integrity monitoring service tests."""
    print("=" * 70)
    print("TESTING INTEGRITY MONITORING SERVICE")
    print("=" * 70)
    
    try:
        await test_monitoring_service_initialization()
        await test_entity_count_monitoring()
        await test_orphaned_edge_detection()
        await test_centrality_validation_monitoring()
        await test_duplicate_entity_detection()
        await test_missing_embeddings_detection()
        await test_full_monitoring_cycle()
        await test_alert_management()
        await test_health_summary()
        await test_custom_checks()
        await test_configuration()
        await test_global_service()
        await test_error_handling()
        
        print("=" * 70)
        print("✅ ALL INTEGRITY MONITORING SERVICE TESTS PASSED!")
        print("The integrity monitoring system is working correctly.")
        print("=" * 70)
        return True
        
    except Exception as e:
        print(f"❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = asyncio.run(run_all_tests())
    exit(0 if success else 1)