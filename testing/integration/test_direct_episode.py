import asyncio
import os
import logging
from datetime import datetime
from graphiti_core.nodes import EpisodeType

# Configure logging to capture debug output
logging.basicConfig(level=logging.DEBUG, format='%(levelname)s:%(name)s:%(message)s')

async def test_direct_episode_creation():
    """Test episode creation exactly like the worker does"""
    
    # Set environment variables like worker
    os.environ["DRIVER_TYPE"] = "falkordb"
    os.environ["FALKORDB_HOST"] = "localhost"
    os.environ["FALKORDB_PORT"] = "6379" 
    os.environ["FALKORDB_DATABASE"] = "graphiti_migration"
    
    print("=== Testing Direct Episode Creation ===")
    
    try:
        # Initialize exactly like worker does
        from graphiti_core.client_factory import GraphitiClientFactory
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.graphiti import Graphiti
        
        # Create clients
        llm_client = GraphitiClientFactory.create_llm_client()
        embedder = GraphitiClientFactory.create_embedder()
        
        # Create driver
        falkor_driver = FalkorDriver(
            host="localhost",
            port=6379,
            database="graphiti_migration"
        )
        
        # Create Graphiti instance
        graphiti = Graphiti(
            llm_client=llm_client,
            embedder=embedder,
            graph_driver=falkor_driver
        )
        
        print(f"✅ Graphiti instance created")
        print(f"Driver type: {type(graphiti.driver)}")
        print(f"LLM client type: {type(graphiti.llm_client)}")
        print(f"Embedder type: {type(graphiti.embedder)}")
        
        # Test exactly like worker with unique content
        import time
        unique_suffix = str(int(time.time() * 1000))  # millisecond timestamp
        result = await graphiti.add_episode(
            group_id="debug_test_group",
            name=f"Debug Test Episode {unique_suffix}",
            episode_body=f"This is a debug test episode {unique_suffix} to verify database writes",
            reference_time=datetime.now(),
            source=EpisodeType.message,
            source_description="Direct debug test"
        )
        
        print(f"=== Episode Creation Result ===")
        print(f"Result type: {type(result)}")
        print(f"Result is None: {result is None}")
        
        if result:
            print(f"Episode exists: {hasattr(result, 'episode')}")
            if hasattr(result, 'episode') and result.episode:
                print(f"Episode UUID: {result.episode.uuid}")
                print(f"Episode name: {result.episode.name}")
                print(f"Episode group_id: {result.episode.group_id}")
            
            print(f"Nodes exists: {hasattr(result, 'nodes')}")
            if hasattr(result, 'nodes'):
                print(f"Nodes count: {len(result.nodes) if result.nodes else 0}")
            
            print(f"Edges exists: {hasattr(result, 'edges')}")
            if hasattr(result, 'edges'):
                print(f"Edges count: {len(result.edges) if result.edges else 0}")
            
            # Verify in database
            if hasattr(result, 'episode') and result.episode and result.episode.uuid:
                print(f"\n=== Database Verification ===")
                count_result = await graphiti.driver.execute_query(
                    "MATCH (n:Episodic {uuid: $uuid}) RETURN count(n) as count, n.name as name, n.group_id as group_id",
                    uuid=result.episode.uuid
                )
                print(f"Episode verification: {count_result}")
                
                if count_result and len(count_result[0]) > 0 and count_result[0][0].get('count', 0) > 0:
                    print(f"✅ Episode {result.episode.uuid} CONFIRMED in database")
                else:
                    print(f"❌ Episode {result.episode.uuid} NOT FOUND in database!")
        else:
            print(f"❌ add_episode returned None or empty result!")
            
        # Check total count
        print(f"\n=== Final Database State ===")
        total_result = await graphiti.driver.execute_query(
            "MATCH (n:Episodic) RETURN count(n) as total"
        )
        print(f"Total episodic nodes: {total_result}")
        
        # List all episodic nodes
        all_episodes = await graphiti.driver.execute_query(
            "MATCH (n:Episodic) RETURN n.uuid as uuid, n.name as name, n.group_id as group_id LIMIT 5"
        )
        print(f"Recent episodes: {all_episodes}")
        
    except Exception as e:
        print(f"❌ Direct episode test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_episode_creation())