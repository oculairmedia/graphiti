#!/usr/bin/env python3

import asyncio
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.graphiti import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver

async def simple_community_test():
    """Simple test to build communities in Graphiti."""
    
    print("🧪 Building Communities in Graphiti")
    print("=" * 50)
    
    # Initialize Graphiti with FalkorDB
    driver = FalkorDriver(
        host="localhost",
        port=6379,
        database="graphiti_migration"
    )
    
    graphiti = Graphiti(
        graph_driver=driver
    )
    
    try:
        print(f"⏰ Starting community building at {datetime.now()}")
        
        # Check nodes before community building
        print("📊 Checking current graph state...")
        node_count_result = await driver.execute_query(
            "MATCH (n) RETURN count(n) as node_count"
        )
        
        if node_count_result:
            node_count = node_count_result[0]['node_count']
            print(f"📍 Total nodes in graph: {node_count}")
        
        # Check for existing communities
        community_count_result = await driver.execute_query(
            "MATCH (c:CommunityNode) RETURN count(c) as community_count"
        )
        
        if community_count_result:
            existing_communities = community_count_result[0]['community_count']
            print(f"🏘️  Existing communities: {existing_communities}")
        
        # Build communities using Leiden algorithm
        print("\n🔍 Building communities with Leiden algorithm...")
        start_time = datetime.now()
        
        # Use the main group_id from our graph data
        await graphiti.build_communities(group_id="emmanuel_claude_tools")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"✅ Community detection completed in {duration:.2f} seconds")
        
        # Check results
        final_community_result = await driver.execute_query(
            "MATCH (c:CommunityNode) RETURN count(c) as community_count"
        )
        
        if final_community_result:
            final_communities = final_community_result[0]['community_count']
            print(f"🏘️  Total communities created: {final_communities}")
            
            # Get some sample communities
            sample_result = await driver.execute_query(
                "MATCH (c:CommunityNode) RETURN c.uuid, c.summary LIMIT 3"
            )
            
            if sample_result:
                print("\n📋 Sample Communities:")
                print("-" * 40)
                for community in sample_result:
                    uuid = community.get('c.uuid', 'Unknown')
                    summary = community.get('c.summary', 'No summary')
                    summary_preview = summary[:100] + "..." if len(summary) > 100 else summary
                    print(f"- {uuid}: {summary_preview}")
        
    except Exception as e:
        print(f"❌ Error during community building: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(simple_community_test())