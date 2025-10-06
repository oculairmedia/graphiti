#!/usr/bin/env python3
"""
Worker Pipeline Diagnostic Script

Checks all components of the ingestion pipeline to identify why the worker has gone silent.
"""

import asyncio
import httpx
import msgpack
from datetime import datetime
from typing import Dict, Any

class Colors:
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    BLUE = '\033[94m'
    END = '\033[0m'
    BOLD = '\033[1m'

def print_header(text: str):
    print(f"\n{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{text}{Colors.END}")
    print(f"{Colors.BOLD}{Colors.BLUE}{'='*60}{Colors.END}\n")

def print_success(text: str):
    print(f"{Colors.GREEN}✓ {text}{Colors.END}")

def print_warning(text: str):
    print(f"{Colors.YELLOW}⚠ {text}{Colors.END}")

def print_error(text: str):
    print(f"{Colors.RED}✗ {text}{Colors.END}")

def print_info(text: str):
    print(f"{Colors.BLUE}ℹ {text}{Colors.END}")

async def check_queue_service() -> bool:
    """Check if queue service is accessible"""
    print_header("1. Queue Service Health Check")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8093/healthz")
            
            if response.status_code == 200:
                print_success("Queue service is healthy")
                return True
            else:
                print_error(f"Queue service returned status {response.status_code}")
                return False
    except Exception as e:
        print_error(f"Cannot connect to queue service: {e}")
        print_info("Check: docker-compose ps graphiti-queued")
        return False

async def check_queues() -> Dict[str, Any]:
    """List all queues and their status"""
    print_header("2. Queue Status")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://localhost:8093/queues")
            
            if response.status_code == 200:
                data = msgpack.unpackb(response.content, raw=False)
                queues = data.get("queues", [])
                
                if queues:
                    print_success(f"Found {len(queues)} queue(s):")
                    for q in queues:
                        print(f"  - {q['name']}")
                    return {q['name']: q for q in queues}
                else:
                    print_warning("No queues found")
                    return {}
            else:
                print_error(f"Failed to list queues: {response.status_code}")
                return {}
    except Exception as e:
        print_error(f"Error listing queues: {e}")
        return {}

async def check_queue_metrics(queue_name: str) -> Dict[str, Any]:
    """Get detailed metrics for a specific queue"""
    print_header(f"3. Queue Metrics: {queue_name}")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"http://localhost:8093/queue/{queue_name}/metrics",
                headers={"Accept": "application/json"}
            )
            
            if response.status_code == 200:
                metrics = response.json()
                
                # Extract key metrics
                visible = metrics.get('visible', 0)
                invisible = metrics.get('invisible', 0)
                total = visible + invisible
                
                print_info(f"Total messages: {total}")
                print_info(f"  Visible (ready): {visible}")
                print_info(f"  Invisible (processing): {invisible}")
                
                if invisible > 0 and visible == 0:
                    print_warning(f"All {invisible} messages are invisible (being processed or stuck)")
                    print_info("Messages will become visible again after visibility timeout expires")
                    print_info("Default visibility timeout: 1200 seconds (20 minutes)")
                elif visible > 0:
                    print_success(f"{visible} messages ready for processing")
                else:
                    print_info("Queue is empty")
                
                return metrics
            else:
                print_error(f"Failed to get metrics: {response.status_code}")
                return {}
    except Exception as e:
        print_error(f"Error getting metrics: {e}")
        return {}

async def check_ollama() -> bool:
    """Check if Ollama is accessible"""
    print_header("4. Ollama Service Check")
    
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get("http://192.168.50.80:11434/api/tags")
            
            if response.status_code == 200:
                data = response.json()
                models = data.get('models', [])
                print_success(f"Ollama is accessible with {len(models)} model(s)")
                for model in models[:3]:  # Show first 3
                    print(f"  - {model.get('name', 'unknown')}")
                return True
            else:
                print_error(f"Ollama returned status {response.status_code}")
                return False
    except Exception as e:
        print_error(f"Cannot connect to Ollama: {e}")
        print_info("Check if Ollama is running on 192.168.50.80:11434")
        return False

async def peek_queue_messages(queue_name: str, count: int = 5):
    """Peek at messages in the queue without removing them"""
    print_header(f"5. Peek Queue Messages: {queue_name}")
    
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            # Poll with very short visibility timeout (1 second) to peek
            response = await client.post(
                f"http://localhost:8093/queue/{queue_name}/messages/poll",
                content=msgpack.packb({
                    "count": count,
                    "visibility_timeout_secs": 1
                }),
                headers={"Content-Type": "application/msgpack"}
            )
            
            if response.status_code == 200:
                data = msgpack.unpackb(response.content, raw=False)
                messages = data.get('messages', [])
                
                if messages:
                    print_success(f"Found {len(messages)} message(s):")
                    for i, msg in enumerate(messages, 1):
                        msg_id = msg.get('id')
                        payload = msg.get('payload', {})
                        
                        # Try to decode task type
                        task_type = payload.get('type', 'unknown')
                        task_id = payload.get('id', 'unknown')
                        
                        print(f"\n  Message {i}:")
                        print(f"    ID: {msg_id}")
                        print(f"    Task Type: {task_type}")
                        print(f"    Task ID: {task_id}")
                        
                        # Show payload keys
                        if isinstance(payload, dict):
                            print(f"    Payload keys: {list(payload.keys())}")
                else:
                    print_info("No visible messages in queue")
                    
            elif response.status_code == 204:
                print_info("Queue is empty (no messages)")
            else:
                print_error(f"Failed to poll messages: {response.status_code}")
                
    except Exception as e:
        print_error(f"Error peeking at messages: {e}")

async def check_worker_health():
    """Try to check worker health endpoint if available"""
    print_header("6. Worker Health Check")
    
    # Try common worker ports
    ports = [8000, 8001, 8002, 8003]
    
    for port in ports:
        try:
            async with httpx.AsyncClient(timeout=2.0) as client:
                response = await client.get(f"http://localhost:{port}/health")
                
                if response.status_code == 200:
                    print_success(f"Worker health endpoint found on port {port}")
                    return True
        except:
            continue
    
    print_warning("No worker health endpoint found")
    print_info("Worker may not expose a health endpoint")
    return False

async def diagnose():
    """Run all diagnostic checks"""
    print(f"\n{Colors.BOLD}Worker Pipeline Diagnostic Tool{Colors.END}")
    print(f"Timestamp: {datetime.now().isoformat()}\n")
    
    # 1. Check queue service
    queue_ok = await check_queue_service()
    if not queue_ok:
        print_error("\n❌ Queue service is not accessible. Cannot continue diagnostics.")
        print_info("Fix: docker-compose restart graphiti-queued")
        return
    
    # 2. List queues
    queues = await check_queues()
    
    # 3. Check each queue's metrics
    for queue_name in queues.keys():
        metrics = await check_queue_metrics(queue_name)
        
        # 5. Peek at messages
        await peek_queue_messages(queue_name, count=3)
    
    # 4. Check Ollama
    await check_ollama()
    
    # 6. Check worker health
    await check_worker_health()
    
    # Summary and recommendations
    print_header("Diagnostic Summary & Recommendations")
    
    if not queues:
        print_warning("No queues found - worker may not have initialized yet")
        print_info("Action: Check worker logs: docker-compose logs graphiti-worker")
    
    for queue_name, queue_info in queues.items():
        metrics = await check_queue_metrics(queue_name)
        
        visible = metrics.get('visible', 0)
        invisible = metrics.get('invisible', 0)
        
        if invisible > 0 and visible == 0:
            print_warning(f"\n{queue_name}: All messages are invisible (stuck in processing)")
            print_info("Possible causes:")
            print_info("  1. Worker is processing a long-running task")
            print_info("  2. Worker crashed mid-processing")
            print_info("  3. Worker is waiting for external service (Ollama, DB)")
            print_info("\nActions:")
            print_info("  1. Check worker logs: docker-compose logs --tail=100 graphiti-worker")
            print_info("  2. Wait for visibility timeout (20 minutes)")
            print_info("  3. Restart worker: docker-compose restart graphiti-worker")
        
        elif visible > 0:
            print_success(f"\n{queue_name}: {visible} messages ready for processing")
            print_info("Actions:")
            print_info("  1. Check if worker is running: docker-compose ps graphiti-worker")
            print_info("  2. Check worker logs: docker-compose logs -f graphiti-worker")
            print_info("  3. Verify worker can connect to queue service")
        
        else:
            print_success(f"\n{queue_name}: Queue is empty - no work to do")
    
    print("\n" + "="*60 + "\n")

if __name__ == "__main__":
    asyncio.run(diagnose())

