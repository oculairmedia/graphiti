#!/usr/bin/env python3

import asyncio
import os
import sys
from datetime import datetime

# Add the project root to the Python path
sys.path.insert(0, '/opt/stacks/graphiti')

from graphiti_core.graphiti import Graphiti
from graphiti_core.driver.falkordb_driver import FalkorDriver

async def minimal_community_test():
    """Minimal test to just build communities."""
    
    print("🧪 Minimal Community Test")
    print("=" * 30)
    
    driver = FalkorDriver(
        host="localhost",
        port=6379,
        database="graphiti_migration"
    )
    
    graphiti = Graphiti(graph_driver=driver)
    
    try:
        print(f"⏰ Starting at {datetime.now()}")
        
        # Just run community detection
        print("🔍 Building communities...")
        await graphiti.build_communities(group_ids=["emmanuel_claude_tools"])
        
        print("✅ Communities built successfully!")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
    
    finally:
        await driver.close()

if __name__ == "__main__":
    asyncio.run(minimal_community_test())