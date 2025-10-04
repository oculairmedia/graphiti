# Graphiti-Queued API Reference

Quick reference for accessing queue data via the graphiti-queued service.

## Base URL

- **Host:** `http://localhost:8093`
- **Container:** `http://graphiti-queued:8080`

## Quick Commands

```bash
# List all queues
curl http://localhost:8093/queues

# Get memory_replay queue metrics (JSON)
curl -H "Accept: application/json" \
  http://localhost:8093/queue/memory_replay/metrics | jq

# Get ingestion queue metrics
curl -H "Accept: application/json" \
  http://localhost:8093/queue/ingestion/metrics | jq

# Health check
curl http://localhost:8093/healthz
```

## Core Endpoints

### List All Queues
```bash
GET /queues
```

**Example:**
```bash
curl http://localhost:8093/queues
```

**Response:**
```json
{
  "queues": [
    {"name": "ingestion"},
    {"name": "memory_replay"}
  ]
}
```

### Get Queue Metrics
```bash
GET /queue/{queue_name}/metrics
```

**Example:**
```bash
# JSON format
curl -H "Accept: application/json" \
  http://localhost:8093/queue/memory_replay/metrics | jq

# Prometheus format (default)
curl http://localhost:8093/queue/memory_replay/metrics
```

**Metrics include:**
- Queue depth (pending messages)
- Processing rate
- Error rate
- Average latency
- Throughput statistics

### Poll Messages
```bash
POST /queue/{queue_name}/messages/poll
```

Retrieve messages from queue (with visibility timeout).

**Example:**
```bash
# Poll 10 messages with 30 second visibility timeout
curl -X POST http://localhost:8093/queue/memory_replay/messages/poll \
  -H "Content-Type: application/msgpack" \
  --data-binary '{"count": 10, "visibility_timeout": 30}'
```

### Push Messages
```bash
POST /queue/{queue_name}/messages/push
```

Add messages to the queue.

### Delete Messages
```bash
POST /queue/{queue_name}/messages/delete
```

Remove specific messages from the queue.

### Update Messages
```bash
POST /queue/{queue_name}/messages/update
```

Update message properties (e.g., visibility timeout).

## Queue Management

### Create Queue
```bash
PUT /queue/{queue_name}
```

### Delete Queue
```bash
DELETE /queue/{queue_name}
```

### Suspend Queue
```bash
# Get suspend status
GET /queue/{queue_name}/suspend

# Set suspend status
POST /queue/{queue_name}/suspend
```

### Throttle Queue
```bash
# Get throttle status
GET /queue/{queue_name}/throttle

# Set throttle status
POST /queue/{queue_name}/throttle
```

## Health Check

```bash
GET /healthz
```

**Example:**
```bash
curl http://localhost:8093/healthz
```

## Python Client Usage

```python
from graphiti_core.ingestion.queue_client import QueuedClient
import asyncio

async def check_queue():
    client = QueuedClient(base_url="http://localhost:8093")
    
    # List all queues
    queues = await client.list_queues()
    print(f"Available queues: {queues}")
    
    # Get stats
    stats = await client.get_stats()
    print(f"Queue stats: {stats}")
    
    # Poll messages (peek without removing)
    messages = await client.poll(
        queue_name="memory_replay",
        count=10,
        visibility_timeout=1  # Short timeout for peeking
    )
    print(f"Found {len(messages)} messages")
    
    # Check specific queue
    for msg_id, task, metadata in messages:
        print(f"Task {msg_id}: {task.type} - {task.payload}")
    
    await client.close()

asyncio.run(check_queue())
```

## Common Queue Names

- **`ingestion`** - Main ingestion queue for episodes, entities, edges
- **`memory_replay`** - Memory replay queue for re-processing episodes

## Response Formats

The queue service supports multiple response formats:

### JSON (Recommended)
```bash
curl -H "Accept: application/json" \
  http://localhost:8093/queue/memory_replay/metrics
```

### MessagePack (Default)
```bash
curl http://localhost:8093/queue/memory_replay/metrics
```

### Prometheus (Metrics only)
```bash
curl -H "Accept: text/plain" \
  http://localhost:8093/queue/memory_replay/metrics
```

## Port Configuration

| Environment | Host Port | Container Port |
|-------------|-----------|----------------|
| Development | 8093      | 8080           |
| Docker      | 8093      | 8080           |

Set via `QUEUE_PORT` environment variable in `.env`:
```bash
QUEUE_PORT=8093
```

## Authentication

Some endpoints may require API key authentication. Check your configuration for:
- `QUEUED_API_KEY` environment variable
- API key header: `X-API-Key: your-key-here`

## Troubleshooting

### Connection Refused
```bash
# Check if service is running
docker-compose ps graphiti-queued

# Check logs
docker-compose logs graphiti-queued

# Restart service
docker-compose restart graphiti-queued
```

### Empty Queue List
```bash
# Queues are created on first use
# Try pushing a message to create the queue
curl -X PUT http://localhost:8093/queue/memory_replay
```

### MessagePack Decoding Issues
```bash
# Use JSON format instead
curl -H "Accept: application/json" http://localhost:8093/queues | jq
```

## Related Documentation

- **Memory Replay System:** `docs/11-memory-replay-operations.md`
- **Queue Client:** `graphiti_core/ingestion/queue_client.py`
- **Worker System:** `docs/ingestion-queue-worker-triage.md`

## Quick Reference Table

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/queues` | GET | List all queues |
| `/queue/{name}/metrics` | GET | Get queue metrics |
| `/queue/{name}/messages/poll` | POST | Retrieve messages |
| `/queue/{name}/messages/push` | POST | Add messages |
| `/queue/{name}/messages/delete` | POST | Remove messages |
| `/queue/{name}/messages/update` | POST | Update messages |
| `/queue/{name}` | PUT | Create queue |
| `/queue/{name}` | DELETE | Delete queue |
| `/queue/{name}/suspend` | GET/POST | Suspend control |
| `/queue/{name}/throttle` | GET/POST | Throttle control |
| `/healthz` | GET | Health check |

