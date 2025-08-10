"""
Integration tests for webhook synchronization.

Tests the complete webhook flow including dispatch, retry, and error handling.
"""

import asyncio
import json
import pytest
from datetime import datetime, timezone
from typing import Dict, Any, List
from unittest.mock import Mock, patch, AsyncMock

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from graph_service.webhooks import WebhookService, NodeAccessEvent, DataIngestionEvent
from graph_service.async_webhooks import AsyncWebhookDispatcher


@pytest.fixture
def webhook_service():
    """Create a webhook service instance for testing."""
    service = WebhookService(webhook_url="http://test-webhook.local/hook")
    return service


@pytest.fixture
def async_dispatcher():
    """Create an async webhook dispatcher for testing."""
    dispatcher = AsyncWebhookDispatcher(
        webhook_url="http://test-webhook.local/hook",
        max_queue_size=100,
        num_workers=1,
        max_retries=2,
        timeout_seconds=1.0,
    )
    return dispatcher


@pytest.mark.asyncio
async def test_webhook_service_emit_node_access(webhook_service):
    """Test emitting node access events."""
    with patch.object(webhook_service.client, 'post', new_callable=AsyncMock) as mock_post:
        mock_post.return_value = Mock(status_code=200, text="OK")
        
        await webhook_service.emit_node_access(
            node_ids=["node1", "node2"],
            access_type="search",
            query="test query",
            metadata={"user": "test_user"}
        )
        
        # Verify the webhook was called
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        
        # Check URL
        assert call_args[0][0] == "http://test-webhook.local/hook"
        
        # Check payload
        payload = call_args[1]["json"]
        assert payload["event_type"] == "node_access"
        assert payload["node_ids"] == ["node1", "node2"]
        assert payload["access_type"] == "search"
        assert payload["query"] == "test query"


@pytest.mark.asyncio
async def test_webhook_service_emit_data_ingestion():
    """Test emitting data ingestion events."""
    # Mock environment variable
    with patch.dict('os.environ', {'GRAPHITI_DATA_WEBHOOK_URLS': 'http://webhook1.local,http://webhook2.local'}):
        service = WebhookService()
        
        with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(status_code=200, text="OK")
            
            # Create mock entities
            mock_node = Mock()
            mock_node.model_dump = Mock(return_value={"uuid": "node1", "name": "Test Node"})
            
            mock_edge = Mock()
            mock_edge.model_dump = Mock(return_value={"uuid": "edge1", "name": "Test Edge"})
            
            await service.emit_data_ingestion(
                operation="add_episode",
                nodes=[mock_node],
                edges=[mock_edge],
                group_id="test_group",
                metadata={"source": "test"}
            )
            
            # Should be called twice (once for each webhook URL)
            assert mock_post.call_count == 2
            
            # Check both calls
            calls = mock_post.call_args_list
            assert calls[0][0][0] == "http://webhook1.local"
            assert calls[1][0][0] == "http://webhook2.local"


@pytest.mark.asyncio
async def test_async_dispatcher_queue_and_dispatch(async_dispatcher):
    """Test async dispatcher queuing and dispatching."""
    await async_dispatcher.start()
    
    try:
        with patch.object(async_dispatcher.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(status_code=200, text="OK")
            
            # Emit an event
            await async_dispatcher.emit_node_access(
                node_ids=["node1"],
                access_type="direct"
            )
            
            # Wait for processing
            await asyncio.sleep(0.1)
            
            # Verify dispatch
            mock_post.assert_called_once()
            
            # Check metrics
            metrics = async_dispatcher.get_metrics()
            assert metrics["total_dispatched"] == 1
            assert metrics["total_failed"] == 0
            
    finally:
        await async_dispatcher.stop()


@pytest.mark.asyncio
async def test_async_dispatcher_retry_logic(async_dispatcher):
    """Test retry logic on failures."""
    await async_dispatcher.start()
    
    try:
        call_count = 0
        
        async def mock_post(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count < 3:  # Fail first 2 attempts
                raise httpx.TimeoutException("Timeout")
            return Mock(status_code=200, text="OK")
        
        with patch.object(async_dispatcher.client, 'post', side_effect=mock_post) as mock_post:
            # Emit an event
            await async_dispatcher.emit_node_access(
                node_ids=["node1"],
                access_type="search"
            )
            
            # Wait for retries
            await asyncio.sleep(5)
            
            # Should retry and eventually succeed
            assert call_count == 3
            metrics = async_dispatcher.get_metrics()
            assert metrics["total_retried"] == 2
            assert metrics["total_dispatched"] == 1
            
    finally:
        await async_dispatcher.stop()


@pytest.mark.asyncio
async def test_async_dispatcher_circuit_breaker(async_dispatcher):
    """Test circuit breaker functionality."""
    async_dispatcher.circuit_breaker_threshold = 3
    async_dispatcher.circuit_breaker_reset_seconds = 1
    
    await async_dispatcher.start()
    
    try:
        with patch.object(async_dispatcher.client, 'post', new_callable=AsyncMock) as mock_post:
            # Always fail
            mock_post.side_effect = httpx.TimeoutException("Timeout")
            
            # Send multiple events to trigger circuit breaker
            for i in range(5):
                await async_dispatcher.emit_node_access(
                    node_ids=[f"node{i}"],
                    access_type="search"
                )
            
            # Wait for processing
            await asyncio.sleep(2)
            
            # Circuit should be open after threshold failures
            assert async_dispatcher.is_circuit_open()
            
            # Wait for circuit reset
            await asyncio.sleep(2)
            
            # Circuit should be closed
            assert not async_dispatcher.is_circuit_open()
            
    finally:
        await async_dispatcher.stop()


@pytest.mark.asyncio
async def test_webhook_internal_handlers():
    """Test internal webhook handlers (e.g., WebSocket)."""
    service = WebhookService()
    
    # Track handler calls
    handler_calls = []
    
    async def test_handler(event: NodeAccessEvent):
        handler_calls.append(event)
    
    # Add internal handler
    await service.add_internal_handler(test_handler)
    
    # Emit event
    await service.emit_node_access(
        node_ids=["node1"],
        access_type="search"
    )
    
    # Handler should be called
    assert len(handler_calls) == 1
    assert handler_calls[0].node_ids == ["node1"]
    assert handler_calls[0].access_type == "search"


@pytest.mark.asyncio
async def test_webhook_queue_overflow_protection(async_dispatcher):
    """Test queue overflow protection."""
    # Create dispatcher with small queue
    dispatcher = AsyncWebhookDispatcher(
        webhook_url="http://test.local",
        max_queue_size=5,
        num_workers=0,  # No workers to process queue
    )
    
    # Fill the queue
    for i in range(10):
        await dispatcher.emit_node_access(
            node_ids=[f"node{i}"],
            access_type="search"
        )
    
    # Queue should be at max size
    assert dispatcher.queue.qsize() == 5
    
    # Check metrics
    metrics = dispatcher.get_metrics()
    assert metrics["queue_max_size"] >= 5


@pytest.mark.asyncio
async def test_data_ingestion_serialization():
    """Test proper serialization of different entity types."""
    service = WebhookService()
    
    with patch.dict('os.environ', {'GRAPHITI_DATA_WEBHOOK_URLS': 'http://test.local'}):
        with patch.object(service.client, 'post', new_callable=AsyncMock) as mock_post:
            mock_post.return_value = Mock(status_code=200)
            
            # Test with different entity types
            entities = [
                Mock(model_dump=Mock(return_value={"type": "model_dump"})),
                Mock(dict=Mock(return_value={"type": "dict"})),
                {"type": "plain_dict"}
            ]
            
            for entity in entities:
                if hasattr(entity, 'model_dump'):
                    entity.model_dump.return_value = {"type": "model_dump"}
                elif hasattr(entity, 'dict'):
                    entity.dict.return_value = {"type": "dict"}
            
            await service.emit_data_ingestion(
                operation="bulk_ingest",
                nodes=entities,
                edges=[]
            )
            
            # Check serialization
            call_args = mock_post.call_args
            payload = call_args[1]["json"]
            
            assert len(payload["nodes"]) == 3
            assert payload["nodes"][0]["type"] == "model_dump"
            assert payload["nodes"][1]["type"] == "dict"
            assert payload["nodes"][2]["type"] == "plain_dict"


@pytest.mark.asyncio
async def test_webhook_metrics_tracking():
    """Test webhook metrics are properly tracked."""
    dispatcher = AsyncWebhookDispatcher()
    await dispatcher.start()
    
    try:
        with patch.object(dispatcher.client, 'post', new_callable=AsyncMock) as mock_post:
            # Mix of successes and failures
            responses = [
                Mock(status_code=200),
                Mock(status_code=500),
                Mock(status_code=200),
            ]
            mock_post.side_effect = responses
            
            # Send events
            for i in range(3):
                await dispatcher.emit_node_access(
                    node_ids=[f"node{i}"],
                    access_type="search"
                )
            
            # Wait for processing
            await asyncio.sleep(0.5)
            
            # Check metrics
            metrics = dispatcher.get_metrics()
            assert metrics["total_dispatched"] >= 2  # At least 2 successes
            assert metrics["total_failed"] >= 1  # At least 1 failure
            assert metrics["last_success_time"] is not None
            assert metrics["last_error_time"] is not None
            
    finally:
        await dispatcher.stop()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])