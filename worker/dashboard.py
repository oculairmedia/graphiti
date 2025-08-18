"""
Simple web dashboard for monitoring the Graphiti ingestion queue system.
Provides real-time metrics, queue status, and management capabilities.
"""

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import asyncio
import json
from datetime import datetime, timedelta
from typing import Dict, Any, List
import logging
from contextlib import asynccontextmanager

from graphiti_core.ingestion.queue_client import QueuedClient, QueueMetrics
from graphiti_core.ingestion.worker import WorkerPool

logger = logging.getLogger(__name__)

# Global instances
queue_client: QueuedClient = None
worker_pool: WorkerPool = None
metrics_history: List[Dict[str, Any]] = []
connected_websockets: List[WebSocket] = []


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize and cleanup resources"""
    global queue_client, worker_pool
    
    # Initialize queue client
    queue_client = QueuedClient(
        base_url=os.getenv("QUEUED_URL", "http://localhost:8090")
    )
    
    # Start metrics collection task
    asyncio.create_task(collect_metrics_loop())
    
    yield
    
    # Cleanup
    if queue_client:
        await queue_client.close()


app = FastAPI(title="Graphiti Queue Dashboard", lifespan=lifespan)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


async def collect_metrics_loop():
    """Collect metrics periodically"""
    global metrics_history
    
    while True:
        try:
            # Get queue statistics
            stats = await queue_client.get_stats() if queue_client else {}
            
            # Get worker metrics if available
            worker_metrics = worker_pool.get_metrics() if worker_pool else {}
            
            # Combine metrics
            metrics = {
                "timestamp": datetime.utcnow().isoformat(),
                "queue": stats,
                "workers": worker_metrics,
            }
            
            # Store in history (keep last hour)
            metrics_history.append(metrics)
            cutoff = datetime.utcnow() - timedelta(hours=1)
            metrics_history = [
                m for m in metrics_history 
                if datetime.fromisoformat(m["timestamp"]) > cutoff
            ]
            
            # Broadcast to connected websockets
            await broadcast_metrics(metrics)
            
        except Exception as e:
            logger.error(f"Error collecting metrics: {e}")
        
        await asyncio.sleep(5)  # Collect every 5 seconds


async def broadcast_metrics(metrics: Dict[str, Any]):
    """Broadcast metrics to all connected websockets"""
    disconnected = []
    
    for ws in connected_websockets:
        try:
            await ws.send_json(metrics)
        except:
            disconnected.append(ws)
    
    # Remove disconnected websockets
    for ws in disconnected:
        if ws in connected_websockets:
            connected_websockets.remove(ws)


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML"""
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Graphiti Ingestion Queue Dashboard</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            padding: 20px;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
        }
        
        .header {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 16px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 10px 40px rgba(0, 0, 0, 0.1);
        }
        
        .header h1 {
            color: #2d3748;
            font-size: 28px;
            margin-bottom: 8px;
        }
        
        .header .subtitle {
            color: #718096;
            font-size: 14px;
        }
        
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
            animation: pulse 2s infinite;
        }
        
        .status-indicator.connected {
            background: #48bb78;
        }
        
        .status-indicator.disconnected {
            background: #f56565;
            animation: none;
        }
        
        @keyframes pulse {
            0% { opacity: 1; }
            50% { opacity: 0.5; }
            100% { opacity: 1; }
        }
        
        .metrics-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 24px;
        }
        
        .metric-card {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 20px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
            transition: transform 0.2s;
        }
        
        .metric-card:hover {
            transform: translateY(-2px);
            box-shadow: 0 8px 30px rgba(0, 0, 0, 0.12);
        }
        
        .metric-label {
            font-size: 12px;
            color: #718096;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 8px;
        }
        
        .metric-value {
            font-size: 32px;
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 4px;
        }
        
        .metric-change {
            font-size: 14px;
            color: #48bb78;
        }
        
        .metric-change.negative {
            color: #f56565;
        }
        
        .chart-container {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        }
        
        .chart-title {
            font-size: 18px;
            color: #2d3748;
            margin-bottom: 16px;
            font-weight: 600;
        }
        
        .queue-table {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        }
        
        table {
            width: 100%;
            border-collapse: collapse;
        }
        
        th {
            text-align: left;
            padding: 12px;
            border-bottom: 2px solid #e2e8f0;
            color: #4a5568;
            font-weight: 600;
            font-size: 14px;
        }
        
        td {
            padding: 12px;
            border-bottom: 1px solid #e2e8f0;
            color: #2d3748;
            font-size: 14px;
        }
        
        tr:last-child td {
            border-bottom: none;
        }
        
        .priority-badge {
            display: inline-block;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
            font-weight: 600;
        }
        
        .priority-critical { background: #fed7d7; color: #742a2a; }
        .priority-high { background: #feebc8; color: #7c2d12; }
        .priority-normal { background: #e6fffa; color: #234e52; }
        .priority-low { background: #f0fff4; color: #22543d; }
        
        .worker-status {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 12px;
            margin-top: 16px;
        }
        
        .worker-card {
            background: #f7fafc;
            border-radius: 8px;
            padding: 12px;
            border-left: 4px solid #4299e1;
        }
        
        .worker-card.idle {
            border-left-color: #cbd5e0;
        }
        
        .worker-card.busy {
            border-left-color: #48bb78;
        }
        
        .control-panel {
            background: rgba(255, 255, 255, 0.95);
            border-radius: 12px;
            padding: 24px;
            margin-bottom: 24px;
            box-shadow: 0 4px 20px rgba(0, 0, 0, 0.08);
        }
        
        .button {
            padding: 10px 20px;
            border-radius: 6px;
            border: none;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            margin-right: 12px;
        }
        
        .button.primary {
            background: #4299e1;
            color: white;
        }
        
        .button.primary:hover {
            background: #3182ce;
        }
        
        .button.danger {
            background: #f56565;
            color: white;
        }
        
        .button.danger:hover {
            background: #e53e3e;
        }
        
        .button.success {
            background: #48bb78;
            color: white;
        }
        
        .button.success:hover {
            background: #38a169;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🚀 Graphiti Ingestion Queue Dashboard</h1>
            <div class="subtitle">
                <span class="status-indicator connected" id="connection-status"></span>
                <span id="connection-text">Connected</span>
                <span style="margin-left: 20px;">Last Update: <span id="last-update">-</span></span>
            </div>
        </div>
        
        <div class="metrics-grid">
            <div class="metric-card">
                <div class="metric-label">Queue Depth</div>
                <div class="metric-value" id="queue-depth">0</div>
                <div class="metric-change" id="queue-depth-change">No change</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Processing Rate</div>
                <div class="metric-value" id="processing-rate">0</div>
                <div class="metric-change">msgs/sec</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Success Rate</div>
                <div class="metric-value" id="success-rate">100%</div>
                <div class="metric-change" id="success-trend">Stable</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Active Workers</div>
                <div class="metric-value" id="active-workers">0/0</div>
                <div class="metric-change">workers</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Failed Tasks</div>
                <div class="metric-value" id="failed-tasks">0</div>
                <div class="metric-change" id="failed-change">Last hour</div>
            </div>
            
            <div class="metric-card">
                <div class="metric-label">Avg Latency</div>
                <div class="metric-value" id="avg-latency">0ms</div>
                <div class="metric-change" id="latency-trend">-</div>
            </div>
        </div>
        
        <div class="control-panel">
            <h3 style="margin-bottom: 16px; color: #2d3748;">Queue Control</h3>
            <button class="button primary" onclick="pauseQueue()">⏸ Pause Queue</button>
            <button class="button success" onclick="resumeQueue()">▶ Resume Queue</button>
            <button class="button danger" onclick="clearDLQ()">🗑 Clear DLQ</button>
            <button class="button primary" onclick="reprocessDLQ()">♻️ Reprocess DLQ</button>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">Throughput (Last Hour)</div>
            <canvas id="throughput-chart" height="80"></canvas>
        </div>
        
        <div class="chart-container">
            <div class="chart-title">Queue Depth by Priority</div>
            <canvas id="priority-chart" height="80"></canvas>
        </div>
        
        <div class="queue-table">
            <h3 style="margin-bottom: 16px; color: #2d3748;">Queue Status</h3>
            <table>
                <thead>
                    <tr>
                        <th>Queue</th>
                        <th>Priority</th>
                        <th>Depth</th>
                        <th>Processing</th>
                        <th>Failed</th>
                        <th>Rate Limited</th>
                    </tr>
                </thead>
                <tbody id="queue-status-table">
                    <tr>
                        <td colspan="6" style="text-align: center; color: #718096;">Loading...</td>
                    </tr>
                </tbody>
            </table>
            
            <h3 style="margin: 24px 0 16px 0; color: #2d3748;">Worker Status</h3>
            <div class="worker-status" id="worker-status">
                <div class="worker-card idle">
                    <strong>Worker 0</strong>
                    <div style="font-size: 12px; color: #718096; margin-top: 4px;">Idle</div>
                </div>
            </div>
        </div>
    </div>
    
    <script>
        // WebSocket connection
        let ws = null;
        let reconnectInterval = null;
        
        // Chart instances
        let throughputChart = null;
        let priorityChart = null;
        
        // Metrics history
        let metricsHistory = [];
        let lastMetrics = null;
        
        function connectWebSocket() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            ws = new WebSocket(`${protocol}//${window.location.host}/ws`);
            
            ws.onopen = () => {
                console.log('WebSocket connected');
                document.getElementById('connection-status').className = 'status-indicator connected';
                document.getElementById('connection-text').textContent = 'Connected';
                
                if (reconnectInterval) {
                    clearInterval(reconnectInterval);
                    reconnectInterval = null;
                }
            };
            
            ws.onmessage = (event) => {
                const metrics = JSON.parse(event.data);
                updateMetrics(metrics);
            };
            
            ws.onclose = () => {
                console.log('WebSocket disconnected');
                document.getElementById('connection-status').className = 'status-indicator disconnected';
                document.getElementById('connection-text').textContent = 'Disconnected';
                
                // Reconnect after 5 seconds
                if (!reconnectInterval) {
                    reconnectInterval = setInterval(() => {
                        console.log('Attempting to reconnect...');
                        connectWebSocket();
                    }, 5000);
                }
            };
            
            ws.onerror = (error) => {
                console.error('WebSocket error:', error);
            };
        }
        
        function updateMetrics(metrics) {
            // Store metrics
            metricsHistory.push(metrics);
            if (metricsHistory.length > 720) { // Keep last hour (5 sec intervals)
                metricsHistory.shift();
            }
            
            // Update last update time
            document.getElementById('last-update').textContent = 
                new Date(metrics.timestamp).toLocaleTimeString();
            
            // Update metric cards
            const queue = metrics.queue || {};
            const workers = metrics.workers || {};
            
            // Queue depth
            const queueDepth = queue.total_messages || 0;
            document.getElementById('queue-depth').textContent = queueDepth.toLocaleString();
            
            if (lastMetrics) {
                const lastDepth = lastMetrics.queue?.total_messages || 0;
                const change = queueDepth - lastDepth;
                const changeEl = document.getElementById('queue-depth-change');
                if (change > 0) {
                    changeEl.textContent = `+${change} from last`;
                    changeEl.className = 'metric-change negative';
                } else if (change < 0) {
                    changeEl.textContent = `${change} from last`;
                    changeEl.className = 'metric-change';
                } else {
                    changeEl.textContent = 'No change';
                    changeEl.className = 'metric-change';
                }
            }
            
            // Processing rate
            const processingRate = calculateProcessingRate();
            document.getElementById('processing-rate').textContent = processingRate.toFixed(1);
            
            // Success rate
            const successRate = calculateSuccessRate(workers);
            document.getElementById('success-rate').textContent = successRate + '%';
            
            // Active workers
            const activeWorkers = workers.workers?.filter(w => w.running).length || 0;
            const totalWorkers = workers.pool_size || 0;
            document.getElementById('active-workers').textContent = `${activeWorkers}/${totalWorkers}`;
            
            // Failed tasks
            const failedTasks = workers.workers?.reduce((sum, w) => sum + (w.failed || 0), 0) || 0;
            document.getElementById('failed-tasks').textContent = failedTasks.toLocaleString();
            
            // Update charts
            updateCharts(metrics);
            
            // Update tables
            updateQueueTable(metrics);
            updateWorkerStatus(workers);
            
            lastMetrics = metrics;
        }
        
        function calculateProcessingRate() {
            if (metricsHistory.length < 2) return 0;
            
            const recent = metricsHistory.slice(-12); // Last minute
            if (recent.length < 2) return 0;
            
            const first = recent[0].workers?.workers?.reduce((sum, w) => sum + (w.completed || 0), 0) || 0;
            const last = recent[recent.length - 1].workers?.workers?.reduce((sum, w) => sum + (w.completed || 0), 0) || 0;
            const timeDiff = (new Date(recent[recent.length - 1].timestamp) - new Date(recent[0].timestamp)) / 1000;
            
            return timeDiff > 0 ? (last - first) / timeDiff : 0;
        }
        
        function calculateSuccessRate(workers) {
            const totals = workers.workers?.reduce((acc, w) => {
                acc.completed += w.completed || 0;
                acc.failed += w.failed || 0;
                return acc;
            }, { completed: 0, failed: 0 }) || { completed: 0, failed: 0 };
            
            const total = totals.completed + totals.failed;
            return total > 0 ? Math.round((totals.completed / total) * 100) : 100;
        }
        
        function initCharts() {
            // Throughput chart
            const throughputCtx = document.getElementById('throughput-chart').getContext('2d');
            throughputChart = new Chart(throughputCtx, {
                type: 'line',
                data: {
                    labels: [],
                    datasets: [{
                        label: 'Messages/sec',
                        data: [],
                        borderColor: '#4299e1',
                        backgroundColor: 'rgba(66, 153, 225, 0.1)',
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
            
            // Priority chart
            const priorityCtx = document.getElementById('priority-chart').getContext('2d');
            priorityChart = new Chart(priorityCtx, {
                type: 'bar',
                data: {
                    labels: ['Critical', 'High', 'Normal', 'Low'],
                    datasets: [{
                        label: 'Queue Depth',
                        data: [0, 0, 0, 0],
                        backgroundColor: [
                            '#f56565',
                            '#ed8936',
                            '#4299e1',
                            '#48bb78'
                        ]
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        legend: { display: false }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });
        }
        
        function updateCharts(metrics) {
            // Update throughput chart
            if (throughputChart && metricsHistory.length > 1) {
                const labels = metricsHistory.slice(-60).map(m => 
                    new Date(m.timestamp).toLocaleTimeString()
                );
                const data = [];
                
                for (let i = 1; i < metricsHistory.slice(-60).length; i++) {
                    const prev = metricsHistory.slice(-60)[i-1];
                    const curr = metricsHistory.slice(-60)[i];
                    const prevCompleted = prev.workers?.workers?.reduce((sum, w) => sum + (w.completed || 0), 0) || 0;
                    const currCompleted = curr.workers?.workers?.reduce((sum, w) => sum + (w.completed || 0), 0) || 0;
                    const timeDiff = (new Date(curr.timestamp) - new Date(prev.timestamp)) / 1000;
                    const rate = timeDiff > 0 ? (currCompleted - prevCompleted) / timeDiff : 0;
                    data.push(rate);
                }
                
                throughputChart.data.labels = labels.slice(1);
                throughputChart.data.datasets[0].data = data;
                throughputChart.update('none');
            }
            
            // Update priority chart (mock data for now)
            if (priorityChart) {
                const queueDepth = metrics.queue?.total_messages || 0;
                priorityChart.data.datasets[0].data = [
                    Math.floor(queueDepth * 0.05),  // Critical
                    Math.floor(queueDepth * 0.15),  // High
                    Math.floor(queueDepth * 0.60),  // Normal
                    Math.floor(queueDepth * 0.20)   // Low
                ];
                priorityChart.update('none');
            }
        }
        
        function updateQueueTable(metrics) {
            const tbody = document.getElementById('queue-status-table');
            const queues = [
                { name: 'ingestion', priority: 'Normal', depth: 0, processing: 0, failed: 0, rateLimited: 0 },
                { name: 'dead_letter', priority: 'N/A', depth: 0, processing: 0, failed: 0, rateLimited: 0 }
            ];
            
            // Update with actual data
            if (metrics.queue) {
                queues[0].depth = metrics.queue.ingestion_depth || 0;
                queues[1].depth = metrics.queue.dlq_depth || 0;
            }
            
            if (metrics.workers?.workers) {
                const totals = metrics.workers.workers.reduce((acc, w) => {
                    acc.processing += w.processing || 0;
                    acc.failed += w.failed || 0;
                    return acc;
                }, { processing: 0, failed: 0 });
                
                queues[0].processing = totals.processing;
                queues[0].failed = totals.failed;
            }
            
            tbody.innerHTML = queues.map(q => `
                <tr>
                    <td><strong>${q.name}</strong></td>
                    <td><span class="priority-badge priority-${q.priority.toLowerCase()}">${q.priority}</span></td>
                    <td>${q.depth.toLocaleString()}</td>
                    <td>${q.processing.toLocaleString()}</td>
                    <td>${q.failed.toLocaleString()}</td>
                    <td>${q.rateLimited.toLocaleString()}</td>
                </tr>
            `).join('');
        }
        
        function updateWorkerStatus(workers) {
            const container = document.getElementById('worker-status');
            
            if (!workers.workers || workers.workers.length === 0) {
                container.innerHTML = '<div class="worker-card idle"><strong>No workers</strong></div>';
                return;
            }
            
            container.innerHTML = workers.workers.map(w => {
                const status = w.running ? 'busy' : 'idle';
                const statusText = w.running ? 'Processing' : 'Idle';
                const stats = `C:${w.completed || 0} F:${w.failed || 0}`;
                
                return `
                    <div class="worker-card ${status}">
                        <strong>${w.worker_id}</strong>
                        <div style="font-size: 12px; color: #718096; margin-top: 4px;">
                            ${statusText} | ${stats}
                        </div>
                    </div>
                `;
            }).join('');
        }
        
        // Control functions
        async function pauseQueue() {
            try {
                const response = await fetch('/api/queue/pause', { method: 'POST' });
                if (response.ok) {
                    alert('Queue paused');
                }
            } catch (error) {
                console.error('Error pausing queue:', error);
                alert('Failed to pause queue');
            }
        }
        
        async function resumeQueue() {
            try {
                const response = await fetch('/api/queue/resume', { method: 'POST' });
                if (response.ok) {
                    alert('Queue resumed');
                }
            } catch (error) {
                console.error('Error resuming queue:', error);
                alert('Failed to resume queue');
            }
        }
        
        async function clearDLQ() {
            if (!confirm('Are you sure you want to clear the dead letter queue?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/dlq/clear', { method: 'POST' });
                if (response.ok) {
                    alert('Dead letter queue cleared');
                }
            } catch (error) {
                console.error('Error clearing DLQ:', error);
                alert('Failed to clear DLQ');
            }
        }
        
        async function reprocessDLQ() {
            if (!confirm('Reprocess all messages in the dead letter queue?')) {
                return;
            }
            
            try {
                const response = await fetch('/api/dlq/reprocess', { method: 'POST' });
                if (response.ok) {
                    const result = await response.json();
                    alert(`Reprocessing ${result.count} messages`);
                }
            } catch (error) {
                console.error('Error reprocessing DLQ:', error);
                alert('Failed to reprocess DLQ');
            }
        }
        
        // Initialize on load
        document.addEventListener('DOMContentLoaded', () => {
            initCharts();
            connectWebSocket();
            
            // Fetch initial metrics
            fetch('/api/metrics')
                .then(res => res.json())
                .then(metrics => updateMetrics(metrics))
                .catch(console.error);
        });
    </script>
</body>
</html>
    """


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint for real-time metrics"""
    await websocket.accept()
    connected_websockets.append(websocket)
    
    try:
        while True:
            # Keep connection alive
            await websocket.receive_text()
    except WebSocketDisconnect:
        connected_websockets.remove(websocket)


@app.get("/api/metrics")
async def get_metrics():
    """Get current metrics"""
    if not queue_client:
        return JSONResponse({"error": "Queue client not initialized"}, status_code=503)
    
    try:
        stats = await queue_client.get_stats()
        worker_metrics = worker_pool.get_metrics() if worker_pool else {}
        
        return JSONResponse({
            "timestamp": datetime.utcnow().isoformat(),
            "queue": stats,
            "workers": worker_metrics,
        })
    except Exception as e:
        logger.error(f"Error getting metrics: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/api/metrics/history")
async def get_metrics_history():
    """Get metrics history"""
    return JSONResponse(metrics_history)


@app.post("/api/queue/pause")
async def pause_queue():
    """Pause queue processing"""
    if not queue_client:
        return JSONResponse({"error": "Queue client not initialized"}, status_code=503)
    
    try:
        # Suspend main queue for 1 hour
        await queue_client.suspend_queue("ingestion", 3600000)
        return JSONResponse({"status": "paused"})
    except Exception as e:
        logger.error(f"Error pausing queue: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/queue/resume")
async def resume_queue():
    """Resume queue processing"""
    if not queue_client:
        return JSONResponse({"error": "Queue client not initialized"}, status_code=503)
    
    try:
        # Resume by setting suspension to 0
        await queue_client.suspend_queue("ingestion", 0)
        return JSONResponse({"status": "resumed"})
    except Exception as e:
        logger.error(f"Error resuming queue: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/dlq/clear")
async def clear_dlq():
    """Clear dead letter queue"""
    if not queue_client:
        return JSONResponse({"error": "Queue client not initialized"}, status_code=503)
    
    try:
        # Poll all messages from DLQ and delete them
        cleared = 0
        while True:
            messages = await queue_client.poll("dead_letter", count=100)
            if not messages:
                break
            
            for msg_id, _, poll_tag in messages:
                await queue_client.delete(msg_id, poll_tag)
                cleared += 1
        
        return JSONResponse({"cleared": cleared})
    except Exception as e:
        logger.error(f"Error clearing DLQ: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.post("/api/dlq/reprocess")
async def reprocess_dlq():
    """Reprocess messages from dead letter queue"""
    if not queue_client:
        return JSONResponse({"error": "Queue client not initialized"}, status_code=503)
    
    try:
        # Poll messages from DLQ
        messages = await queue_client.poll("dead_letter", count=100)
        
        # Reset retry count and push back to main queue
        tasks_to_reprocess = []
        for msg_id, task, poll_tag in messages:
            task.retry_count = 0
            task.metadata['reprocessed_at'] = datetime.utcnow().isoformat()
            tasks_to_reprocess.append(task)
            
            # Delete from DLQ
            await queue_client.delete(msg_id, poll_tag)
        
        # Push to main queue
        if tasks_to_reprocess:
            await queue_client.push(tasks_to_reprocess, "ingestion")
        
        return JSONResponse({"count": len(tasks_to_reprocess)})
    except Exception as e:
        logger.error(f"Error reprocessing DLQ: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)


@app.get("/health")
async def health_check():
    """Health check endpoint"""
    return JSONResponse({"status": "healthy"})


if __name__ == "__main__":
    import uvicorn
    import os
    
    port = int(os.getenv("DASHBOARD_PORT", "8091"))
    uvicorn.run(app, host="0.0.0.0", port=port)