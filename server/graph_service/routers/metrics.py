"""
Performance metrics and monitoring endpoints.

Provides a comprehensive view of system performance including
cache hit rates, webhook queue depth, and latency statistics.
"""

import time
import psutil
import asyncio
from typing import Dict, Any, List
from datetime import datetime, timezone
from collections import deque

from fastapi import APIRouter, Response
from fastapi.responses import HTMLResponse

from graph_service.cache import search_cache, embedding_cache
from graph_service.async_webhooks import dispatcher

router = APIRouter(prefix="/metrics", tags=["metrics"])


class PerformanceTracker:
    """Track request performance metrics."""
    
    def __init__(self, window_size: int = 1000):
        self.latencies: deque = deque(maxlen=window_size)
        self.endpoints: Dict[str, deque] = {}
        self.start_time = time.time()
    
    def record_latency(self, endpoint: str, latency_ms: float):
        """Record a latency measurement."""
        self.latencies.append(latency_ms)
        
        if endpoint not in self.endpoints:
            self.endpoints[endpoint] = deque(maxlen=100)
        self.endpoints[endpoint].append(latency_ms)
    
    def get_percentiles(self, values: List[float]) -> Dict[str, float]:
        """Calculate percentiles for a list of values."""
        if not values:
            return {"p50": 0, "p95": 0, "p99": 0}
        
        sorted_values = sorted(values)
        n = len(sorted_values)
        
        return {
            "p50": sorted_values[int(n * 0.5)],
            "p95": sorted_values[int(n * 0.95)],
            "p99": sorted_values[int(n * 0.99)],
        }
    
    def get_metrics(self) -> Dict[str, Any]:
        """Get current performance metrics."""
        uptime_seconds = time.time() - self.start_time
        
        # Overall latencies
        overall_latencies = list(self.latencies)
        overall_percentiles = self.get_percentiles(overall_latencies)
        
        # Per-endpoint metrics
        endpoint_metrics = {}
        for endpoint, latencies in self.endpoints.items():
            latency_list = list(latencies)
            if latency_list:
                endpoint_metrics[endpoint] = {
                    "count": len(latency_list),
                    "avg_ms": sum(latency_list) / len(latency_list),
                    **self.get_percentiles(latency_list),
                }
        
        return {
            "uptime_seconds": uptime_seconds,
            "total_requests": len(overall_latencies),
            "overall_latency": {
                "avg_ms": sum(overall_latencies) / len(overall_latencies) if overall_latencies else 0,
                **overall_percentiles,
            },
            "endpoints": endpoint_metrics,
        }


# Global performance tracker
perf_tracker = PerformanceTracker()


@router.get("/")
async def get_all_metrics() -> Dict[str, Any]:
    """
    Get comprehensive system metrics.
    
    Returns cache metrics, webhook metrics, and performance statistics.
    """
    # System metrics
    process = psutil.Process()
    memory_info = process.memory_info()
    
    system_metrics = {
        "cpu_percent": process.cpu_percent(interval=0.1),
        "memory_mb": memory_info.rss / 1024 / 1024,
        "memory_percent": process.memory_percent(),
        "num_threads": process.num_threads(),
    }
    
    # Cache metrics
    cache_metrics = {
        "search": search_cache.get_metrics(),
        "embedding": embedding_cache.get_metrics(),
    }
    
    # Webhook metrics
    webhook_metrics = dispatcher.get_metrics()
    
    # Performance metrics
    performance_metrics = perf_tracker.get_metrics()
    
    # Calculate overall health score (0-100)
    cache_hit_rate = cache_metrics["search"].get("hit_rate", "0%").rstrip("%")
    cache_hit_rate = float(cache_hit_rate) if cache_hit_rate else 0
    
    health_score = min(100, max(0, 
        (cache_hit_rate * 0.4) +  # 40% weight on cache hit rate
        (100 - min(webhook_metrics.get("queue_size", 0) / 100, 100)) * 0.3 +  # 30% on queue depth
        (100 - min(performance_metrics["overall_latency"]["p99"] / 100, 100)) * 0.3  # 30% on p99 latency
    ))
    
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "health_score": round(health_score, 2),
        "system": system_metrics,
        "cache": cache_metrics,
        "webhooks": webhook_metrics,
        "performance": performance_metrics,
    }


@router.get("/dashboard", response_class=HTMLResponse)
async def metrics_dashboard():
    """
    Interactive performance dashboard.
    
    Provides a real-time view of system performance with auto-refresh.
    """
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Graphiti Performance Dashboard</title>
        <style>
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                margin: 0;
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: #333;
            }
            .container {
                max-width: 1400px;
                margin: 0 auto;
            }
            h1 {
                color: white;
                text-align: center;
                margin-bottom: 30px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.2);
            }
            .metrics-grid {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 20px;
            }
            .metric-card {
                background: white;
                border-radius: 12px;
                padding: 20px;
                box-shadow: 0 10px 30px rgba(0,0,0,0.1);
                transition: transform 0.2s;
            }
            .metric-card:hover {
                transform: translateY(-5px);
                box-shadow: 0 15px 40px rgba(0,0,0,0.15);
            }
            .metric-title {
                font-size: 14px;
                color: #666;
                text-transform: uppercase;
                letter-spacing: 1px;
                margin-bottom: 10px;
            }
            .metric-value {
                font-size: 32px;
                font-weight: bold;
                color: #333;
                margin-bottom: 5px;
            }
            .metric-subtitle {
                font-size: 12px;
                color: #999;
            }
            .health-score {
                background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%);
                color: white;
            }
            .health-good { background: linear-gradient(135deg, #84fab0 0%, #8fd3f4 100%); }
            .health-warning { background: linear-gradient(135deg, #ffd89b 0%, #ffa751 100%); }
            .health-bad { background: linear-gradient(135deg, #ff6b6b 0%, #ff4757 100%); }
            .refresh-info {
                text-align: center;
                color: white;
                margin-top: 20px;
                font-size: 14px;
            }
            .latency-bars {
                display: flex;
                justify-content: space-between;
                margin-top: 10px;
            }
            .latency-bar {
                flex: 1;
                text-align: center;
                padding: 5px;
                background: #f0f0f0;
                border-radius: 4px;
                margin: 0 2px;
            }
            .latency-bar-label {
                font-size: 10px;
                color: #666;
            }
            .latency-bar-value {
                font-size: 14px;
                font-weight: bold;
            }
            table {
                width: 100%;
                border-collapse: collapse;
                margin-top: 10px;
            }
            th, td {
                padding: 8px;
                text-align: left;
                border-bottom: 1px solid #eee;
            }
            th {
                font-size: 12px;
                color: #666;
                text-transform: uppercase;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🚀 Graphiti Performance Dashboard</h1>
            <div class="metrics-grid" id="metrics-grid">
                <div class="metric-card">Loading metrics...</div>
            </div>
            <div class="refresh-info">
                Auto-refreshing every 2 seconds | <span id="last-update"></span>
            </div>
        </div>
        
        <script>
            function formatNumber(num) {
                return new Intl.NumberFormat().format(Math.round(num));
            }
            
            function formatPercent(num) {
                return num.toFixed(1) + '%';
            }
            
            function formatLatency(ms) {
                if (ms < 1) return '<1ms';
                if (ms < 1000) return Math.round(ms) + 'ms';
                return (ms / 1000).toFixed(2) + 's';
            }
            
            function getHealthClass(score) {
                if (score >= 80) return 'health-good';
                if (score >= 50) return 'health-warning';
                return 'health-bad';
            }
            
            async function updateMetrics() {
                try {
                    const response = await fetch('/metrics/');
                    const data = await response.json();
                    
                    const grid = document.getElementById('metrics-grid');
                    grid.innerHTML = `
                        <!-- Health Score -->
                        <div class="metric-card ${getHealthClass(data.health_score)}">
                            <div class="metric-title">System Health</div>
                            <div class="metric-value">${formatPercent(data.health_score)}</div>
                            <div class="metric-subtitle">Overall system performance</div>
                        </div>
                        
                        <!-- Cache Performance -->
                        <div class="metric-card">
                            <div class="metric-title">Cache Hit Rate</div>
                            <div class="metric-value">${data.cache.search.hit_rate || '0%'}</div>
                            <div class="metric-subtitle">
                                ${formatNumber(data.cache.search.hits)} hits / 
                                ${formatNumber(data.cache.search.misses)} misses
                            </div>
                            <div class="latency-bars">
                                <div class="latency-bar">
                                    <div class="latency-bar-label">L1</div>
                                    <div class="latency-bar-value">${formatNumber(data.cache.search.l1_hits)}</div>
                                </div>
                                <div class="latency-bar">
                                    <div class="latency-bar-label">L2</div>
                                    <div class="latency-bar-value">${formatNumber(data.cache.search.l2_hits)}</div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Latency -->
                        <div class="metric-card">
                            <div class="metric-title">Request Latency</div>
                            <div class="metric-value">${formatLatency(data.performance.overall_latency.p50)}</div>
                            <div class="metric-subtitle">Median response time</div>
                            <div class="latency-bars">
                                <div class="latency-bar">
                                    <div class="latency-bar-label">p50</div>
                                    <div class="latency-bar-value">${formatLatency(data.performance.overall_latency.p50)}</div>
                                </div>
                                <div class="latency-bar">
                                    <div class="latency-bar-label">p95</div>
                                    <div class="latency-bar-value">${formatLatency(data.performance.overall_latency.p95)}</div>
                                </div>
                                <div class="latency-bar">
                                    <div class="latency-bar-label">p99</div>
                                    <div class="latency-bar-value">${formatLatency(data.performance.overall_latency.p99)}</div>
                                </div>
                            </div>
                        </div>
                        
                        <!-- Webhook Queue -->
                        <div class="metric-card">
                            <div class="metric-title">Webhook Queue</div>
                            <div class="metric-value">${formatNumber(data.webhooks.queue_size)}</div>
                            <div class="metric-subtitle">
                                ${formatNumber(data.webhooks.total_dispatched)} dispatched / 
                                ${formatNumber(data.webhooks.total_failed)} failed
                            </div>
                        </div>
                        
                        <!-- System Resources -->
                        <div class="metric-card">
                            <div class="metric-title">Memory Usage</div>
                            <div class="metric-value">${data.system.memory_mb.toFixed(1)} MB</div>
                            <div class="metric-subtitle">
                                ${formatPercent(data.system.memory_percent)} of system | 
                                ${data.system.num_threads} threads
                            </div>
                        </div>
                        
                        <!-- Request Volume -->
                        <div class="metric-card">
                            <div class="metric-title">Total Requests</div>
                            <div class="metric-value">${formatNumber(data.performance.total_requests)}</div>
                            <div class="metric-subtitle">
                                Since ${new Date(Date.now() - data.performance.uptime_seconds * 1000).toLocaleTimeString()}
                            </div>
                        </div>
                    `;
                    
                    document.getElementById('last-update').textContent = 
                        'Last updated: ' + new Date().toLocaleTimeString();
                    
                } catch (error) {
                    console.error('Error fetching metrics:', error);
                }
            }
            
            // Initial load
            updateMetrics();
            
            // Auto-refresh every 2 seconds
            setInterval(updateMetrics, 2000);
        </script>
    </body>
    </html>
    """
    return html_content


@router.get("/prometheus")
async def prometheus_metrics():
    """
    Export metrics in Prometheus format.
    
    Compatible with Prometheus, Grafana, and other monitoring tools.
    """
    metrics = await get_all_metrics()
    
    # Format as Prometheus metrics
    lines = []
    
    # System metrics
    lines.append(f'# HELP graphiti_cpu_percent CPU usage percentage')
    lines.append(f'# TYPE graphiti_cpu_percent gauge')
    lines.append(f'graphiti_cpu_percent {metrics["system"]["cpu_percent"]}')
    
    lines.append(f'# HELP graphiti_memory_bytes Memory usage in bytes')
    lines.append(f'# TYPE graphiti_memory_bytes gauge')
    lines.append(f'graphiti_memory_bytes {metrics["system"]["memory_mb"] * 1024 * 1024}')
    
    # Cache metrics
    cache_hit_rate = metrics["cache"]["search"].get("hit_rate", "0%").rstrip("%")
    lines.append(f'# HELP graphiti_cache_hit_rate Cache hit rate percentage')
    lines.append(f'# TYPE graphiti_cache_hit_rate gauge')
    lines.append(f'graphiti_cache_hit_rate {cache_hit_rate}')
    
    lines.append(f'# HELP graphiti_cache_hits_total Total cache hits')
    lines.append(f'# TYPE graphiti_cache_hits_total counter')
    lines.append(f'graphiti_cache_hits_total {metrics["cache"]["search"]["hits"]}')
    
    # Latency metrics
    lines.append(f'# HELP graphiti_latency_p50_ms P50 latency in milliseconds')
    lines.append(f'# TYPE graphiti_latency_p50_ms gauge')
    lines.append(f'graphiti_latency_p50_ms {metrics["performance"]["overall_latency"]["p50"]}')
    
    lines.append(f'# HELP graphiti_latency_p99_ms P99 latency in milliseconds')
    lines.append(f'# TYPE graphiti_latency_p99_ms gauge')
    lines.append(f'graphiti_latency_p99_ms {metrics["performance"]["overall_latency"]["p99"]}')
    
    # Webhook metrics
    lines.append(f'# HELP graphiti_webhook_queue_size Current webhook queue size')
    lines.append(f'# TYPE graphiti_webhook_queue_size gauge')
    lines.append(f'graphiti_webhook_queue_size {metrics["webhooks"]["queue_size"]}')
    
    # Health score
    lines.append(f'# HELP graphiti_health_score Overall system health score (0-100)')
    lines.append(f'# TYPE graphiti_health_score gauge')
    lines.append(f'graphiti_health_score {metrics["health_score"]}')
    
    return Response(content="\n".join(lines), media_type="text/plain")