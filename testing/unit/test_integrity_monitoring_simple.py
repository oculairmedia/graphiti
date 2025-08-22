#!/usr/bin/env python3
"""
Simple test for integrity monitoring service core functionality.
"""

import asyncio
import sys
from datetime import datetime

# Add the project root to path for imports
sys.path.append('/opt/stacks/graphiti')

from graphiti_core.utils.integrity_monitoring import (
    IntegrityMonitoringService,
    MonitoringAlert,
    MonitoringSeverity,
    MonitoringMetric,
    MonitoringThresholds
)


async def test_basic_functionality():
    """Test basic functionality without database dependencies."""
    print("Testing basic integrity monitoring functionality...")
    
    # Test service initialization
    service = IntegrityMonitoringService()
    assert service.thresholds is not None, "Should have thresholds"
    assert service.monitoring_enabled, "Should be enabled by default"
    print("✅ Service initialization works")
    
    # Test alert creation and management
    alert = MonitoringAlert(
        id="test_alert",
        timestamp=datetime.now(),
        severity=MonitoringSeverity.WARNING,
        metric=MonitoringMetric.ENTITY_COUNT,
        message="Test alert message"
    )
    
    service.alerts.append(alert)
    active_alerts = service.get_active_alerts()
    assert len(active_alerts) == 1, "Should have 1 active alert"
    print("✅ Alert creation and retrieval works")
    
    # Test alert resolution
    resolved = service.resolve_alert("test_alert", "Resolved for testing")
    assert resolved, "Should successfully resolve alert"
    assert alert.resolved, "Alert should be marked as resolved"
    print("✅ Alert resolution works")
    
    # Test health summary
    summary = service.get_health_summary()
    assert 'health_score' in summary, "Should have health score"
    assert 'overall_status' in summary, "Should have overall status"
    print(f"✅ Health summary works - Score: {summary['health_score']}, Status: {summary['overall_status']}")
    
    # Test custom check registration
    async def custom_check():
        return [MonitoringAlert(
            id="custom_test",
            timestamp=datetime.now(),
            severity=MonitoringSeverity.INFO,
            metric=MonitoringMetric.VALIDATION_ERRORS,
            message="Custom check test"
        )]
    
    service.register_custom_check("test_check", custom_check)
    assert "test_check" in service.custom_checks, "Should register custom check"
    print("✅ Custom check registration works")
    
    # Test threshold configuration
    thresholds = MonitoringThresholds(
        max_entity_count_change_percent=5.0,
        max_orphaned_edges_percent=2.0
    )
    
    custom_service = IntegrityMonitoringService(thresholds=thresholds)
    assert custom_service.thresholds.max_entity_count_change_percent == 5.0, "Should use custom thresholds"
    print("✅ Custom threshold configuration works")
    
    print("\n🎉 ALL BASIC FUNCTIONALITY TESTS PASSED!")
    return True


if __name__ == "__main__":
    success = asyncio.run(test_basic_functionality())
    exit(0 if success else 1)