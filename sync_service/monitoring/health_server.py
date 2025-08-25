"""
Health monitoring server for sync service.

This module provides HTTP endpoints for health checks and metrics collection.
"""

import asyncio
import logging
import json
import time
from datetime import datetime
from typing import Any, Dict, Optional, Callable
from aiohttp import web, WSMsgType
from aiohttp.web import Request, Response, WebSocketResponse
import psutil

from ..config.settings import MonitoringConfig
from ..orchestrator.sync_orchestrator import SyncOrchestrator

logger = logging.getLogger(__name__)


class HealthServer:
    """HTTP server for health monitoring and metrics."""
    
    def __init__(
        self,
        config: MonitoringConfig,
        sync_orchestrator: SyncOrchestrator
    ):
        """
        Initialize health server.
        
        Args:
            config: Monitoring configuration
            sync_orchestrator: Sync orchestrator instance
        """
        self.config = config
        self.sync_orchestrator = sync_orchestrator
        self.app = web.Application()
        self.runner: Optional[web.AppRunner] = None
        self.site: Optional[web.TCPSite] = None
        self.start_time = time.time()
        
        # WebSocket connections for real-time updates
        self.websocket_connections: set[WebSocketResponse] = set()
        
        self._setup_routes()
        
    def _setup_routes(self) -> None:
        """Set up HTTP routes."""
        # Health check endpoint
        self.app.router.add_get(self.config.health_path, self.health_check)
        
        # Metrics endpoints
        if self.config.metrics_enabled:
            self.app.router.add_get(self.config.metrics_path, self.metrics)
            self.app.router.add_get('/api/sync/status', self.sync_status)
            self.app.router.add_get('/api/sync/statistics', self.sync_statistics)
            self.app.router.add_get('/api/sync/history', self.sync_history)
            
        # Control endpoints
        self.app.router.add_post('/api/sync/start', self.start_sync)
        self.app.router.add_post('/api/sync/stop', self.stop_sync)
        self.app.router.add_post('/api/sync/full', self.trigger_full_sync)
        self.app.router.add_post('/api/sync/incremental', self.trigger_incremental_sync)
        
        # WebSocket endpoint for real-time updates
        self.app.router.add_get('/ws/updates', self.websocket_handler)
        
        # System metrics
        self.app.router.add_get('/api/system/metrics', self.system_metrics)
        
    async def health_check(self, request: Request) -> Response:
        """Basic health check endpoint."""
        try:
            # Check sync orchestrator health
            orchestrator_health = await self.sync_orchestrator.get_health_status()
            
            health_status = {
                "status": "healthy",
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "uptime_seconds": time.time() - self.start_time,
                "sync_orchestrator": {
                    "is_running": orchestrator_health["is_running"],
                    "last_sync": orchestrator_health["last_sync_timestamp"].isoformat() + "Z" if orchestrator_health["last_sync_timestamp"] else None,
                    "current_operation": orchestrator_health.get("current_operation")
                }
            }
            
            return web.json_response(health_status)
            
        except Exception as e:
            logger.error(f"Health check failed: {e}")
            return web.json_response(
                {
                    "status": "unhealthy",
                    "timestamp": datetime.utcnow().isoformat() + "Z",
                    "error": str(e)
                },
                status=503
            )
            
    async def metrics(self, request: Request) -> Response:
        """Prometheus-style metrics endpoint."""
        try:
            # Get sync statistics
            sync_stats = await self.sync_orchestrator.get_sync_statistics()
            health_status = await self.sync_orchestrator.get_health_status()
            
            # System metrics
            process = psutil.Process()
            memory_info = process.memory_info()
            cpu_percent = process.cpu_percent()
            
            # Generate Prometheus metrics format
            metrics_lines = [
                "# HELP sync_service_uptime_seconds Total uptime of the sync service",
                "# TYPE sync_service_uptime_seconds counter",
                f"sync_service_uptime_seconds {time.time() - self.start_time}",
                "",
                "# HELP sync_operations_total Total number of sync operations",
                "# TYPE sync_operations_total counter", 
                f"sync_operations_total {sync_stats.get('total_operations', 0)}",
                "",
                "# HELP sync_operations_successful_total Total number of successful sync operations",
                "# TYPE sync_operations_successful_total counter",
                f"sync_operations_successful_total {sync_stats.get('successful_operations', 0)}",
                "",
                "# HELP sync_operations_failed_total Total number of failed sync operations", 
                "# TYPE sync_operations_failed_total counter",
                f"sync_operations_failed_total {sync_stats.get('failed_operations', 0)}",
                "",
                "# HELP sync_success_rate Success rate of sync operations",
                "# TYPE sync_success_rate gauge",
                f"sync_success_rate {sync_stats.get('success_rate', 0)}",
                "",
                "# HELP sync_items_processed_total Total number of items processed",
                "# TYPE sync_items_processed_total counter",
                f"sync_items_processed_total {sync_stats.get('total_items_processed', 0)}",
                "",
                "# HELP sync_average_duration_seconds Average duration of sync operations",
                "# TYPE sync_average_duration_seconds gauge",
                f"sync_average_duration_seconds {sync_stats.get('average_duration_seconds', 0)}",
                "",
                "# HELP sync_orchestrator_running Whether the sync orchestrator is currently running",
                "# TYPE sync_orchestrator_running gauge", 
                f"sync_orchestrator_running {1 if health_status['is_running'] else 0}",
                "",
                "# HELP process_memory_bytes Memory usage in bytes",
                "# TYPE process_memory_bytes gauge",
                f"process_memory_bytes {memory_info.rss}",
                "",
                "# HELP process_cpu_percent CPU usage percentage",
                "# TYPE process_cpu_percent gauge",
                f"process_cpu_percent {cpu_percent}",
            ]
            
            return web.Response(
                text="\n".join(metrics_lines),
                content_type="text/plain; version=0.0.4; charset=utf-8"
            )
            
        except Exception as e:
            logger.error(f"Metrics collection failed: {e}")
            return web.Response(text="# Error collecting metrics", status=500)
            
    async def sync_status(self, request: Request) -> Response:
        """Get current sync status."""
        try:
            health_status = await self.sync_orchestrator.get_health_status()
            return web.json_response(health_status)
        except Exception as e:
            logger.error(f"Failed to get sync status: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def sync_statistics(self, request: Request) -> Response:
        """Get sync statistics."""
        try:
            stats = await self.sync_orchestrator.get_sync_statistics()
            return web.json_response(stats)
        except Exception as e:
            logger.error(f"Failed to get sync statistics: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def sync_history(self, request: Request) -> Response:
        """Get sync operation history."""
        try:
            limit = int(request.query.get('limit', 50))
            history = self.sync_orchestrator.sync_history[-limit:]
            
            # Convert to serializable format
            serializable_history = []
            for operation in history:
                op_dict = {
                    "mode": operation.mode.value,
                    "status": operation.status.value,
                    "started_at": operation.started_at.isoformat() + "Z" if operation.started_at else None,
                    "completed_at": operation.completed_at.isoformat() + "Z" if operation.completed_at else None,
                    "duration_seconds": operation.duration_seconds,
                    "total_items_processed": operation.total_items_processed,
                    "total_items_failed": operation.total_items_failed,
                    "success_rate": operation.success_rate,
                    "errors": operation.errors
                }
                serializable_history.append(op_dict)
                
            return web.json_response(serializable_history)
        except Exception as e:
            logger.error(f"Failed to get sync history: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def start_sync(self, request: Request) -> Response:
        """Start continuous sync."""
        try:
            await self.sync_orchestrator.start_continuous_sync()
            return web.json_response({"message": "Continuous sync started"})
        except Exception as e:
            logger.error(f"Failed to start sync: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def stop_sync(self, request: Request) -> Response:
        """Stop continuous sync."""
        try:
            await self.sync_orchestrator.stop_continuous_sync()
            return web.json_response({"message": "Continuous sync stopped"})
        except Exception as e:
            logger.error(f"Failed to stop sync: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def trigger_full_sync(self, request: Request) -> Response:
        """Trigger a full sync operation."""
        try:
            operation_stats = await self.sync_orchestrator.sync_full()
            
            # Convert to serializable format
            result = {
                "mode": operation_stats.mode.value,
                "status": operation_stats.status.value,
                "duration_seconds": operation_stats.duration_seconds,
                "total_items_processed": operation_stats.total_items_processed,
                "success_rate": operation_stats.success_rate
            }
            
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Failed to trigger full sync: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def trigger_incremental_sync(self, request: Request) -> Response:
        """Trigger an incremental sync operation."""
        try:
            operation_stats = await self.sync_orchestrator.sync_incremental()
            
            # Convert to serializable format  
            result = {
                "mode": operation_stats.mode.value,
                "status": operation_stats.status.value,
                "duration_seconds": operation_stats.duration_seconds,
                "total_items_processed": operation_stats.total_items_processed,
                "success_rate": operation_stats.success_rate
            }
            
            return web.json_response(result)
        except Exception as e:
            logger.error(f"Failed to trigger incremental sync: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def websocket_handler(self, request: Request) -> WebSocketResponse:
        """WebSocket handler for real-time updates."""
        ws = WebSocketResponse()
        await ws.prepare(request)
        
        self.websocket_connections.add(ws)
        logger.info("WebSocket client connected")
        
        try:
            async for msg in ws:
                if msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket error: {ws.exception()}")
                    break
        except Exception as e:
            logger.error(f"WebSocket error: {e}")
        finally:
            self.websocket_connections.discard(ws)
            logger.info("WebSocket client disconnected")
            
        return ws
        
    async def broadcast_update(self, update_data: Dict[str, Any]) -> None:
        """Broadcast update to all WebSocket connections."""
        if not self.websocket_connections:
            return
            
        message = json.dumps(update_data)
        disconnected = set()
        
        for ws in self.websocket_connections:
            try:
                await ws.send_str(message)
            except Exception as e:
                logger.warning(f"Failed to send WebSocket message: {e}")
                disconnected.add(ws)
                
        # Remove disconnected clients
        self.websocket_connections -= disconnected
        
    async def system_metrics(self, request: Request) -> Response:
        """Get system resource metrics."""
        try:
            # Process metrics
            process = psutil.Process()
            memory_info = process.memory_info()
            
            # System metrics
            cpu_count = psutil.cpu_count()
            memory_total = psutil.virtual_memory().total
            memory_available = psutil.virtual_memory().available
            disk_usage = psutil.disk_usage('/')
            
            metrics = {
                "timestamp": datetime.utcnow().isoformat() + "Z",
                "process": {
                    "memory_rss_bytes": memory_info.rss,
                    "memory_vms_bytes": memory_info.vms,
                    "cpu_percent": process.cpu_percent(),
                    "num_threads": process.num_threads(),
                    "open_files": len(process.open_files()),
                    "connections": len(process.connections())
                },
                "system": {
                    "cpu_count": cpu_count,
                    "cpu_percent": psutil.cpu_percent(interval=1),
                    "memory_total_bytes": memory_total,
                    "memory_available_bytes": memory_available,
                    "memory_usage_percent": psutil.virtual_memory().percent,
                    "disk_total_bytes": disk_usage.total,
                    "disk_free_bytes": disk_usage.free,
                    "disk_usage_percent": (disk_usage.used / disk_usage.total) * 100
                }
            }
            
            return web.json_response(metrics)
        except Exception as e:
            logger.error(f"Failed to get system metrics: {e}")
            return web.json_response({"error": str(e)}, status=500)
            
    async def start(self) -> None:
        """Start the health server."""
        try:
            self.runner = web.AppRunner(self.app)
            await self.runner.setup()
            
            self.site = web.TCPSite(self.runner, '0.0.0.0', self.config.health_port)
            await self.site.start()
            
            logger.info(f"Health server started on port {self.config.health_port}")
        except Exception as e:
            logger.error(f"Failed to start health server: {e}")
            raise
            
    async def stop(self) -> None:
        """Stop the health server."""
        try:
            # Close WebSocket connections
            for ws in list(self.websocket_connections):
                await ws.close()
            self.websocket_connections.clear()
            
            if self.site:
                await self.site.stop()
                self.site = None
                
            if self.runner:
                await self.runner.cleanup()
                self.runner = None
                
            logger.info("Health server stopped")
        except Exception as e:
            logger.error(f"Failed to stop health server: {e}")