#!/usr/bin/env python3
"""
Test script to debug why entity extraction is failing when messages are sent to Graphiti
"""

import asyncio
import requests
import json
from datetime import datetime
import logging

# Configure logging to see all debug output
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Test configuration
GRAPHITI_URL = "http://localhost:8003"  # Adjust if needed
TEST_GROUP_ID = "test_entity_extraction"

def send_test_message(content: str, role: str = "user"):
    """Send a test message to Graphiti and observe the response"""
    
    endpoint = f"{GRAPHITI_URL}/messages"
    
    payload = {
        "messages": [{
            "content": content,
            "role_type": role,
            "role": "test_user",
            "name": f"Test_{datetime.now().isoformat()}",
            "source_description": "Entity Extraction Test",
            "timestamp": datetime.now().isoformat()
        }],
        "group_id": TEST_GROUP_ID
    }
    
    logger.info(f"Sending payload to {endpoint}:")
    logger.info(json.dumps(payload, indent=2))
    
    try:
        response = requests.post(endpoint, json=payload, timeout=30)
        logger.info(f"Response status: {response.status_code}")
        logger.info(f"Response body: {response.text}")
        
        if response.status_code == 200 or response.status_code == 201:
            return response.json()
        else:
            logger.error(f"Error response: {response.text}")
            return None
            
    except Exception as e:
        logger.error(f"Request failed: {e}")
        return None

async def check_extraction_results(episode_content: str):
    """Check if entities were extracted from the episode"""
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    
    driver = FalkorDriver(
        host="localhost",
        port=6389,
        database="graphiti_migration"
    )
    
    # Wait longer for processing with new model
    logger.info("Waiting 50 seconds for entity extraction to complete...")
    await asyncio.sleep(50)
    
    # Find the episode we just created
    query = """
    MATCH (ep:Episodic)
    WHERE ep.group_id = $group_id 
    AND ep.content CONTAINS $content_snippet
    RETURN ep.uuid as uuid, ep.content as content, ep.created_at as created_at
    ORDER BY ep.created_at DESC
    LIMIT 1
    """
    
    records, _, _ = await driver.execute_query(
        query,
        group_id=TEST_GROUP_ID,
        content_snippet=episode_content[:50]
    )
    
    if not records:
        logger.error("Episode not found in database!")
        return
        
    episode = records[0]
    logger.info(f"Found episode: {episode['uuid']}")
    
    # Check if it has entities
    entity_query = """
    MATCH (ep:Episodic {uuid: $uuid})-[:MENTIONS]->(e:Entity)
    RETURN e.name as name, e.uuid as uuid
    """
    
    entity_records, _, _ = await driver.execute_query(
        entity_query,
        uuid=episode['uuid']
    )
    
    if entity_records:
        logger.info(f"✅ Found {len(entity_records)} entities:")
        for e in entity_records:
            logger.info(f"  - {e['name']} ({e['uuid']})")
    else:
        logger.warning("❌ No entities found for this episode!")
        
    return len(entity_records) if entity_records else 0

async def test_with_server_logs():
    """Test entity extraction with different message types"""
    
    test_messages = [
        # Simple technical content
        "I'm working with GraphCanvas component in React to visualize graph data using Cosmograph library.",
        
        # Code-related content
        "The EntityDeduplicator class in maintenance_dedupe_entities.py uses LLM to merge duplicate entities.",
        
        # Tool usage content
        "Claude read file: /opt/stacks/graphiti/frontend/src/components/GraphCanvas.tsx which contains React components for graph visualization.",
        
        # Mixed content
        "I modified the FalkorDB driver to support Redis connections on port 6389 for the graphiti_migration database.",
    ]
    
    results = []
    
    for i, message in enumerate(test_messages):
        logger.info(f"\n{'='*60}")
        logger.info(f"Test {i+1}: {message[:100]}...")
        logger.info(f"{'='*60}")
        
        # Send message
        response = send_test_message(message)
        
        if response:
            # Check extraction results
            entity_count = await check_extraction_results(message)
            results.append({
                "message": message[:100],
                "entities_found": entity_count,
                "response": response
            })
        else:
            results.append({
                "message": message[:100],
                "entities_found": 0,
                "response": None,
                "error": "Failed to send message"
            })
        
        # Add delay between tests
        await asyncio.sleep(2)
            
    # Summary
    logger.info(f"\n{'='*60}")
    logger.info("SUMMARY")
    logger.info(f"{'='*60}")
    
    for i, result in enumerate(results):
        status = "✅" if result["entities_found"] > 0 else "❌"
        logger.info(f"{status} Test {i+1}: {result['entities_found']} entities - {result['message']}...")

async def trace_server_processing():
    """Try to trace what's happening in the server"""
    
    # First, let's check server logs
    logger.info("\nChecking server configuration and logs...")
    
    # Check if server is running
    try:
        health_response = requests.get(f"{GRAPHITI_URL}/health", timeout=5)
        logger.info(f"Server health check: {health_response.status_code}")
    except:
        logger.error("Server not responding at {GRAPHITI_URL}")
        return
        
    # Check server configuration endpoint if available
    try:
        config_response = requests.get(f"{GRAPHITI_URL}/config", timeout=5)
        if config_response.status_code == 200:
            logger.info(f"Server config: {json.dumps(config_response.json(), indent=2)}")
    except:
        logger.info("No config endpoint available")

async def main():
    """Run all tests"""
    
    logger.info("Starting entity extraction debugging...")
    
    # Test with server logs
    await test_with_server_logs()
    
    # Trace server processing
    await trace_server_processing()
    
    # Additional debugging - check async worker
    logger.info("\n\nDEBUGGING NOTES:")
    logger.info("1. Check server logs: docker-compose logs graph")
    logger.info("2. The async worker might not be processing tasks")
    logger.info("3. Entity extraction might be disabled in config")
    logger.info("4. LLM calls might be failing")
    
    # Let's also check if there's a queue or worker status
    logger.info("\nTo debug further:")
    logger.info("- Add logging to /opt/stacks/graphiti/server/graph_service/routers/ingest.py")
    logger.info("- Check the async_worker implementation")
    logger.info("- Monitor LLM server (Ollama) for extraction requests")

if __name__ == "__main__":
    asyncio.run(main())