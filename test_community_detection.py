#!/usr/bin/env python3

import asyncio
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.graphiti import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver

async def test_community_detection():
    """Test Graphiti's community detection using the Leiden algorithm."""
    
    print("🧪 Testing Graphiti Community Detection")
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
        # Check initial state
        print(f"⏰ Starting community detection at {datetime.now()}")
        
        # Check if communities already exist
        existing_communities = await driver.get_nodes(
            node_type="CommunityNode"
        )
        print(f"📊 Existing communities: {len(existing_communities)}")
        
        # Build communities using Leiden algorithm
        print("🔍 Building communities with Leiden algorithm...")
        start_time = datetime.now()
        
        await graphiti.build_communities(group_id="emmanuel_claude_tools")
        
        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()
        
        print(f"✅ Community detection completed in {duration:.2f} seconds")
        
        # Check results
        communities = await driver.get_nodes(
            node_type="CommunityNode"
        )
        
        print(f"🏘️  Total communities detected: {len(communities)}")
        
        # Show community details
        if communities:
            print("\n📋 Community Details:")
            print("-" * 40)
            
            for i, community in enumerate(communities[:5]):  # Show first 5
                member_count = len(community.member_entities) if hasattr(community, 'member_entities') else 0
                summary_length = len(community.summary) if community.summary else 0
                
                print(f"Community {i+1}:")
                print(f"  - ID: {community.uuid}")
                print(f"  - Members: {member_count}")
                print(f"  - Summary length: {summary_length} characters")
                if community.summary and len(community.summary) > 100:
                    print(f"  - Summary preview: {community.summary[:100]}...")
                elif community.summary:
                    print(f"  - Summary: {community.summary}")
                print()
                
            if len(communities) > 5:
                print(f"... and {len(communities) - 5} more communities")
        
        # Show community size distribution
        if communities:
            member_counts = [len(c.member_entities) if hasattr(c, 'member_entities') else 0 for c in communities]
            print(f"📈 Community size stats:")
            print(f"  - Largest community: {max(member_counts)} members")
            print(f"  - Smallest community: {min(member_counts)} members")
            print(f"  - Average size: {sum(member_counts)/len(member_counts):.1f} members")
        
    except Exception as e:
        print(f"❌ Error during community detection: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(test_community_detection())