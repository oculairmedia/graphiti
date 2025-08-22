#!/usr/bin/env python3
"""Test script for queued service."""

import json
import msgpack
import requests
from datetime import datetime

QUEUED_URL = "http://localhost:8093"

def test_queued():
    """Test basic queued operations."""
    
    # Create queue
    print("Creating queue 'ingestion'...")
    response = requests.put(
        f"{QUEUED_URL}/queue/ingestion",
        data=msgpack.packb({}),
        headers={"Content-Type": "application/msgpack"}
    )
    print(f"  Status: {response.status_code}")
    
    # Push messages
    print("\nPushing messages...")
    messages = [
        {"contents": json.dumps({"type": "text", "data": "Test document 1"}), "visibility_timeout_secs": 0},
        {"contents": json.dumps({"type": "text", "data": "Test document 2"}), "visibility_timeout_secs": 0},
        {"contents": json.dumps({"type": "text", "data": "Test document 3"}), "visibility_timeout_secs": 0},
    ]
    response = requests.post(
        f"{QUEUED_URL}/queue/ingestion/messages/push",
        data=msgpack.packb({"messages": messages}),
        headers={"Content-Type": "application/msgpack"}
    )
    print(f"  Status: {response.status_code}")
    if response.status_code == 200:
        data = msgpack.unpackb(response.content, raw=False)
        print(f"  Response: {data}")
    else:
        print(f"  Error: {response.text}")
    
    # Poll messages
    print("\nPolling messages...")
    response = requests.post(
        f"{QUEUED_URL}/queue/ingestion/messages/poll",
        data=msgpack.packb({"visibility_timeout_secs": 30, "count": 2}),
        headers={"Content-Type": "application/msgpack"}
    )
    print(f"  Status: {response.status_code}")
    if response.status_code != 200:
        print(f"  Error: {response.text}")
    elif response.status_code == 200:
        data = msgpack.unpackb(response.content, raw=False)
        print(f"  Received {len(data.get('messages', []))} messages")
        
        # Delete processed messages
        if data.get('messages'):
            print("\nDeleting processed messages...")
            delete_msgs = [
                {"id": msg["id"], "poll_tag": msg["poll_tag"]} 
                for msg in data["messages"]
            ]
            response = requests.post(
                f"{QUEUED_URL}/queue/ingestion/messages/delete",
                data=msgpack.packb({"messages": delete_msgs}),
                headers={"Content-Type": "application/msgpack"}
            )
            print(f"  Status: {response.status_code}")
    
    # Check queue stats
    print("\nListing queues...")
    response = requests.get(f"{QUEUED_URL}/queues")
    if response.status_code == 200:
        data = msgpack.unpackb(response.content, raw=False)
        print(f"  Queues: {data}")

if __name__ == "__main__":
    test_queued()