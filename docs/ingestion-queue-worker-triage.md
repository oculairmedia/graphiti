## Ingestion Queue/Worker Disconnect — Triage Notes

### TL;DR
- Worker is polling but discards messages that don’t match its expected schema, so it reports no tasks to process
- Test submitter pushes a different JSON shape than the worker/QueuedClient expect
- Because parsing fails, the worker never acknowledges (deletes) those messages
- Your group_id fix is deployed; to validate it quickly, bypass the queue or use QueuedClient to push correctly formatted tasks

### What the worker expects (message schema)
QueuedClient wraps each message so the worker can sort by priority and deserialize the task:

- The HTTP body to queued is MessagePack: { "messages": [ { contents, visibility_timeout_secs } ] }
- contents is a JSON string with the shape:

```json
{
  "priority": 1,
  "task": "{\n  \"id\": \"...\",\n  \"type\": \"episode\",\n  \"payload\": { ... },\n  \"group_id\": \"...\",\n  \"priority\": 1,\n  \"retry_count\": 0,\n  \"max_retries\": 3,\n  \"created_at\": \"2025-08-21T12:34:56.000000\",\n  \"visibility_timeout\": 300,\n  \"metadata\": {}\n}"
}
```

Notes:
- The inner "task" field is itself a JSON string produced by IngestionTask.to_json()
- type and priority are serialized as values (type is a string enum, priority is an int)
- created_at is ISO8601

### What the current test submitter sends (mismatch)
Current submitter pushes something like:

```json
{
  "type": "episode",
  "data": {
    "content": "...",
    "timestamp": "...",
    "source": "test_submission",
    "name": "Test Episode"
  }
}
```

Problems:
- No priority wrapper: contents must be { "priority": <int>, "task": "<json string>" }
- The inner object must be a full IngestionTask JSON string (with id, created_at, payload, etc.)
- Uses data instead of payload

Result: When worker polls, it does json.loads(contents) and expects contents["task"]. It then calls IngestionTask.from_json(contents["task"]). Because the structure isn’t there, parsing fails and the message is skipped (not acknowledged).

### Fastest ways to validate the group_id fix

Option A — Bypass the queue and call Graphiti directly
- Call graphiti.add_episode or save_entity_node with a known group_id and verify behavior
- This validates the group_id path independently of queue formatting

Option B — Use QueuedClient to push correctly formatted tasks
- This guarantees the envelope and task schema match what the worker expects

Minimal example:

```python
from graphiti_core.ingestion.queue_client import QueuedClient, IngestionTask, TaskType, TaskPriority
import asyncio, uuid
from datetime import datetime

async def main():
    qc = QueuedClient(base_url="http://localhost:8093")
    t = IngestionTask(
        id=str(uuid.uuid4()),
        type=TaskType.EPISODE,
        payload={
            "content": "Hello",
            "timestamp": datetime.utcnow().isoformat(),
            "group_id": "g1",
            "name": "Test Episode"
        },
        group_id="g1",
        priority=TaskPriority.NORMAL,
    )
    await qc.push([t], queue_name="ingestion")
    await qc.close()

asyncio.run(main())
```

If the worker is running, you should see logs indicating it polled and processed the task, and the queue item will be deleted (acked).

### Diagnostics checklist
- Worker logs: look for "Failed to parse message {id}" originating from QueuedClient.poll; this indicates malformed contents
- Queue depth: GET /queues or QueuedClient.list_queues() to confirm messages exist but aren’t consumed
- Ack behavior: When formatted correctly, you should see delete calls succeeding after processing

### Remediation
1) Update all producers to either:
   - Use QueuedClient.push to ensure correct envelope and task JSON, or
   - Replicate the exact envelope: contents = json.dumps({"priority": <int>, "task": IngestionTask(...).to_json()})
2) Standardize on payload rather than data for task body
3) Optionally add a compatibility branch in poll() to detect legacy shapes and log a clear warning, but prefer fixing producers

### Code references
- docs/ingestion-queue-design.md — design and message structure notes
- graphiti_core/ingestion/queue_client.py — IngestionTask, push(), poll(), delete(), update()
- graphiti_core/ingestion/worker.py — Worker poll loop and task processing
- submit_to_queue.py — Current test submitter (does not match required envelope)

