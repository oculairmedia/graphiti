#!/usr/bin/env python3
import asyncio
import websockets
import json
import datetime

async def test_graph_update():
    uri = "ws://localhost:3000/ws"
    
    async with websockets.connect(uri) as websocket:
        # Send a graph update event
        update_event = {
            "type": "graph:update",
            "data": {
                "operation": "add_nodes",
                "nodes": [
                    {
                        "id": f"test-node-{datetime.datetime.now().isoformat()}",
                        "label": "Test Node Added via WebSocket",
                        "node_type": "EntityNode",
                        "summary": "This node was added dynamically",
                        "properties": {
                            "degree_centrality": 0.5,
                            "color": "#ff0000",
                            "size": 15
                        }
                    }
                ],
                "timestamp": int(datetime.datetime.now().timestamp() * 1000)
            }
        }
        
        print(f"Sending update: {json.dumps(update_event, indent=2)}")
        await websocket.send(json.dumps(update_event))
        
        # Wait for response
        response = await websocket.recv()
        print(f"Received: {response}")
        
        # Send edge update
        edge_update = {
            "type": "graph:update", 
            "data": {
                "operation": "add_edges",
                "edges": [
                    {
                        "from": update_event["data"]["nodes"][0]["id"],
                        "to": "existing-node-1",  # Assuming this exists
                        "edge_type": "RELATES_TO",
                        "weight": 1.0
                    }
                ],
                "timestamp": int(datetime.datetime.now().timestamp() * 1000)
            }
        }
        
        print(f"Sending edge update: {json.dumps(edge_update, indent=2)}")
        await websocket.send(json.dumps(edge_update))
        
        response = await websocket.recv()
        print(f"Received: {response}")

if __name__ == "__main__":
    asyncio.run(test_graph_update())