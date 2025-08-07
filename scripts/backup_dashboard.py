#!/usr/bin/env python3
"""
FalkorDB Backup Monitoring Dashboard
Provides web interface and API endpoints for backup monitoring
"""

import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any

from flask import Flask, jsonify, render_template_string
import humanize

app = Flask(__name__)

# Configuration
STATUS_FILE = os.environ.get('STATUS_FILE', '/var/log/backup_status.json')
BACKUP_DIR = os.environ.get('BACKUP_DIR', '/backups/falkordb')

# HTML template for dashboard
DASHBOARD_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
    <title>FalkorDB Backup Monitor</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
            margin: 0;
            padding: 20px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
        }
        .container {
            max-width: 1200px;
            margin: 0 auto;
        }
        h1 {
            color: white;
            text-align: center;
            margin-bottom: 30px;
            text-shadow: 0 2px 4px rgba(0,0,0,0.2);
        }
        .grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .card {
            background: white;
            border-radius: 10px;
            padding: 20px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }
        .card h2 {
            margin-top: 0;
            color: #333;
            font-size: 18px;
            border-bottom: 2px solid #f0f0f0;
            padding-bottom: 10px;
        }
        .status {
            display: flex;
            align-items: center;
            margin: 10px 0;
        }
        .status-indicator {
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 10px;
        }
        .status-success { background: #10b981; }
        .status-warning { background: #f59e0b; }
        .status-error { background: #ef4444; }
        .status-unknown { background: #6b7280; }
        .metric {
            display: flex;
            justify-content: space-between;
            margin: 8px 0;
            padding: 5px 0;
            border-bottom: 1px solid #f9f9f9;
        }
        .metric-label {
            color: #666;
            font-size: 14px;
        }
        .metric-value {
            font-weight: 600;
            color: #333;
            font-size: 14px;
        }
        .storage-bar {
            background: #f3f4f6;
            border-radius: 5px;
            height: 30px;
            overflow: hidden;
            margin: 10px 0;
            position: relative;
        }
        .storage-fill {
            height: 100%;
            background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
            transition: width 0.3s ease;
            display: flex;
            align-items: center;
            padding: 0 10px;
            color: white;
            font-size: 12px;
            font-weight: 600;
        }
        .auto-refresh {
            text-align: center;
            color: white;
            margin-top: 20px;
            font-size: 14px;
        }
        .error-message {
            background: #fee;
            border-left: 4px solid #ef4444;
            padding: 10px;
            margin: 10px 0;
            font-size: 13px;
            color: #991b1b;
        }
        .timestamp {
            color: #999;
            font-size: 12px;
            margin-top: 10px;
        }
    </style>
    <script>
        function refreshData() {
            fetch('/api/status')
                .then(response => response.json())
                .then(data => {
                    updateDashboard(data);
                });
        }
        
        function updateDashboard(data) {
            // Update backup cards
            ['daily', 'weekly', 'monthly', 'snapshot'].forEach(type => {
                const backup = data.backups[type];
                if (backup) {
                    const card = document.getElementById(`backup-${type}`);
                    if (card) {
                        const statusEl = card.querySelector('.status-indicator');
                        statusEl.className = 'status-indicator status-' + backup.status;
                        
                        card.querySelector('.last-backup').textContent = 
                            backup.last_backup_timestamp ? 
                            new Date(backup.last_backup_timestamp).toLocaleString() : 'Never';
                        
                        card.querySelector('.backup-size').textContent = 
                            formatBytes(backup.last_backup_size || 0);
                    }
                }
            });
            
            // Update storage
            if (data.storage) {
                const total = data.storage.total_size || 0;
                document.getElementById('storage-used').textContent = formatBytes(total);
            }
        }
        
        function formatBytes(bytes) {
            if (bytes === 0) return '0 B';
            const k = 1024;
            const sizes = ['B', 'KB', 'MB', 'GB'];
            const i = Math.floor(Math.log(bytes) / Math.log(k));
            return (bytes / Math.pow(k, i)).toFixed(2) + ' ' + sizes[i];
        }
        
        // Auto-refresh every 30 seconds
        setInterval(refreshData, 30000);
    </script>
</head>
<body>
    <div class="container">
        <h1>🔒 FalkorDB Backup Monitor</h1>
        
        <div class="grid">
            {% for backup_type, backup_data in backups.items() %}
            <div class="card" id="backup-{{ backup_type }}">
                <h2>{{ backup_type.title() }} Backup</h2>
                <div class="status">
                    <div class="status-indicator status-{{ backup_data.status }}"></div>
                    <span>{{ backup_data.status.upper() }}</span>
                </div>
                
                <div class="metric">
                    <span class="metric-label">Last Backup:</span>
                    <span class="metric-value last-backup">
                        {% if backup_data.last_backup_timestamp %}
                            {{ backup_data.last_backup_timestamp }}
                        {% else %}
                            Never
                        {% endif %}
                    </span>
                </div>
                
                <div class="metric">
                    <span class="metric-label">Size:</span>
                    <span class="metric-value backup-size">{{ backup_data.size_human }}</span>
                </div>
                
                <div class="metric">
                    <span class="metric-label">Duration:</span>
                    <span class="metric-value">{{ backup_data.duration_human }}</span>
                </div>
                
                <div class="metric">
                    <span class="metric-label">Next Run:</span>
                    <span class="metric-value">{{ schedule[backup_type].next_run_human }}</span>
                </div>
                
                {% if backup_data.error_message %}
                <div class="error-message">
                    {{ backup_data.error_message }}
                </div>
                {% endif %}
            </div>
            {% endfor %}
        </div>
        
        <div class="card">
            <h2>Storage Usage</h2>
            <div class="metric">
                <span class="metric-label">Total Used:</span>
                <span class="metric-value" id="storage-used">{{ storage.total_human }}</span>
            </div>
            <div class="storage-bar">
                <div class="storage-fill" style="width: {{ storage.usage_percent }}%">
                    {{ storage.usage_percent }}%
                </div>
            </div>
            <div class="metric">
                <span class="metric-label">Daily:</span>
                <span class="metric-value">{{ storage.daily_human }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Weekly:</span>
                <span class="metric-value">{{ storage.weekly_human }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Monthly:</span>
                <span class="metric-value">{{ storage.monthly_human }}</span>
            </div>
            <div class="metric">
                <span class="metric-label">Snapshots:</span>
                <span class="metric-value">{{ storage.snapshot_human }}</span>
            </div>
        </div>
        
        <div class="auto-refresh">
            Auto-refreshing every 30 seconds | Last updated: <span id="last-update">{{ now }}</span>
        </div>
    </div>
</body>
</html>
"""

def get_status() -> Dict[str, Any]:
    """Get current backup status"""
    try:
        if os.path.exists(STATUS_FILE):
            with open(STATUS_FILE, 'r') as f:
                return json.load(f)
    except Exception as e:
        app.logger.error(f"Error reading status file: {e}")
    
    return {"backups": {}}

def get_schedule() -> Dict[str, Any]:
    """Get backup schedule"""
    from datetime import datetime, timedelta
    
    now = datetime.utcnow()
    
    # Calculate next run times
    next_hour = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
    next_3am = now.replace(hour=3, minute=0, second=0, microsecond=0)
    if next_3am <= now:
        next_3am += timedelta(days=1)
    
    # Next Sunday at 4 AM
    days_until_sunday = (6 - now.weekday()) % 7
    if days_until_sunday == 0 and now.hour >= 4:
        days_until_sunday = 7
    next_sunday = now.replace(hour=4, minute=0, second=0, microsecond=0) + timedelta(days=days_until_sunday)
    
    # First of next month at 5 AM
    if now.month == 12:
        next_month = now.replace(year=now.year + 1, month=1, day=1, hour=5, minute=0, second=0, microsecond=0)
    else:
        next_month = now.replace(month=now.month + 1, day=1, hour=5, minute=0, second=0, microsecond=0)
    
    return {
        "daily": {"cron": "0 3 * * *", "next_run": next_3am.isoformat() + 'Z'},
        "weekly": {"cron": "0 4 * * 0", "next_run": next_sunday.isoformat() + 'Z'},
        "monthly": {"cron": "0 5 1 * *", "next_run": next_month.isoformat() + 'Z'},
        "snapshot": {"cron": "0 * * * *", "next_run": next_hour.isoformat() + 'Z'}
    }

def get_storage_stats() -> Dict[str, Any]:
    """Get storage statistics"""
    import os
    from pathlib import Path
    
    backup_dir = Path(BACKUP_DIR)
    
    def get_dir_size(path: Path) -> int:
        """Get total size of directory in bytes"""
        if not path.exists():
            return 0
        total = 0
        try:
            for entry in path.rglob('*'):
                if entry.is_file():
                    total += entry.stat().st_size
        except Exception:
            pass
        return total
    
    try:
        daily_size = get_dir_size(backup_dir / 'daily')
        weekly_size = get_dir_size(backup_dir / 'weekly')
        monthly_size = get_dir_size(backup_dir / 'monthly')
        snapshot_size = get_dir_size(backup_dir / 'snapshots')
        total_size = daily_size + weekly_size + monthly_size + snapshot_size
        
        return {
            "total_size": total_size,
            "daily_size": daily_size,
            "weekly_size": weekly_size,
            "monthly_size": monthly_size,
            "snapshot_size": snapshot_size
        }
    except Exception as e:
        app.logger.error(f"Error getting storage stats: {e}")
        return {"total_size": 0}

def format_status_data(status: Dict[str, Any]) -> Dict[str, Any]:
    """Format status data for display"""
    formatted = status.copy()
    
    # Format backup data - handle both 'snapshot' and 'snapshots' keys
    backup_types = ['daily', 'weekly', 'monthly']
    
    # Check for snapshot or snapshots key in the actual data
    if 'snapshots' in formatted.get('backups', {}):
        formatted['backups']['snapshot'] = formatted['backups'].pop('snapshots')
    
    backup_types.append('snapshot')
    
    for backup_type in backup_types:
        if backup_type not in formatted.get('backups', {}):
            formatted.setdefault('backups', {})[backup_type] = {
                'status': 'unknown',
                'last_backup_size': 0,
                'last_backup_duration': 0,
                'error_message': ''
            }
        
        backup = formatted['backups'][backup_type]
        
        # Add human-readable formats
        backup['size_human'] = humanize.naturalsize(backup.get('last_backup_size', 0))
        
        duration = backup.get('last_backup_duration', 0)
        if duration > 0:
            backup['duration_human'] = f"{duration:.1f}s"
        else:
            backup['duration_human'] = "N/A"
        
        # Format timestamp
        if backup.get('last_backup_timestamp'):
            try:
                dt = datetime.fromisoformat(backup['last_backup_timestamp'].replace('Z', '+00:00'))
                backup['last_backup_timestamp'] = dt.strftime('%Y-%m-%d %H:%M:%S UTC')
            except:
                pass
    
    return formatted

@app.route('/')
def dashboard():
    """Render dashboard HTML"""
    status = get_status()
    schedule = get_schedule()
    storage = get_storage_stats()
    
    # Format schedule with human-readable next run times
    for backup_type, sched in schedule.items():
        if sched.get('next_run'):
            try:
                next_run = datetime.fromisoformat(sched['next_run'].replace('Z', '+00:00'))
                time_until = next_run - datetime.utcnow()
                sched['next_run_human'] = humanize.naturaltime(time_until)
            except:
                sched['next_run_human'] = 'Unknown'
        else:
            sched['next_run_human'] = 'Unknown'
    
    # Format storage data
    storage['total_human'] = humanize.naturalsize(storage.get('total_size', 0))
    storage['daily_human'] = humanize.naturalsize(storage.get('daily_size', 0))
    storage['weekly_human'] = humanize.naturalsize(storage.get('weekly_size', 0))
    storage['monthly_human'] = humanize.naturalsize(storage.get('monthly_size', 0))
    storage['snapshot_human'] = humanize.naturalsize(storage.get('snapshot_size', 0))
    
    # Calculate usage percentage (assume 10GB max for display)
    max_size = 10 * 1024 * 1024 * 1024  # 10GB
    storage['usage_percent'] = min(100, int((storage.get('total_size', 0) / max_size) * 100))
    
    formatted_status = format_status_data(status)
    
    return render_template_string(
        DASHBOARD_TEMPLATE,
        backups=formatted_status.get('backups', {}),
        schedule=schedule,
        storage=storage,
        now=datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')
    )

@app.route('/health')
def health():
    """Health check endpoint"""
    status = get_status()
    
    # Check if any backup has failed recently
    is_healthy = True
    for backup_type, backup_data in status.get('backups', {}).items():
        if backup_data.get('status') == 'error':
            is_healthy = False
            break
    
    return jsonify({
        'status': 'healthy' if is_healthy else 'unhealthy',
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    }), 200 if is_healthy else 503

@app.route('/api/status')
def api_status():
    """API endpoint for status data"""
    status = get_status()
    schedule = get_schedule()
    storage = get_storage_stats()
    
    return jsonify({
        'backups': status.get('backups', {}),
        'schedule': schedule,
        'storage': storage,
        'timestamp': datetime.utcnow().isoformat() + 'Z'
    })

@app.route('/metrics')
def metrics():
    """Prometheus metrics endpoint"""
    status = get_status()
    storage = get_storage_stats()
    
    metrics_text = []
    
    # Backup metrics
    for backup_type, backup_data in status.get('backups', {}).items():
        # Last success timestamp
        if backup_data.get('last_backup_timestamp'):
            try:
                dt = datetime.fromisoformat(backup_data['last_backup_timestamp'].replace('Z', '+00:00'))
                timestamp = int(dt.timestamp())
                metrics_text.append(f'falkordb_backup_last_success_timestamp{{type="{backup_type}"}} {timestamp}')
            except:
                pass
        
        # Backup size
        size = backup_data.get('last_backup_size', 0)
        metrics_text.append(f'falkordb_backup_size_bytes{{type="{backup_type}"}} {size}')
        
        # Backup duration
        duration = backup_data.get('last_backup_duration', 0)
        metrics_text.append(f'falkordb_backup_duration_seconds{{type="{backup_type}"}} {duration}')
        
        # Status (1 for success, 0 for error)
        status_value = 1 if backup_data.get('status') == 'success' else 0
        metrics_text.append(f'falkordb_backup_status{{type="{backup_type}"}} {status_value}')
    
    # Storage metrics
    metrics_text.append(f'falkordb_backup_storage_used_bytes {storage.get("total_size", 0)}')
    metrics_text.append(f'falkordb_backup_storage_daily_bytes {storage.get("daily_size", 0)}')
    metrics_text.append(f'falkordb_backup_storage_weekly_bytes {storage.get("weekly_size", 0)}')
    metrics_text.append(f'falkordb_backup_storage_monthly_bytes {storage.get("monthly_size", 0)}')
    metrics_text.append(f'falkordb_backup_storage_snapshot_bytes {storage.get("snapshot_size", 0)}')
    
    return '\n'.join(metrics_text) + '\n', 200, {'Content-Type': 'text/plain'}

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080, debug=False)