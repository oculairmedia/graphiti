# Queue-based Message Processing Debug Strategy

## Problem Summary

**Issue**: Messages are successfully queued and picked up by workers, but no episodic nodes are being created in the FalkorDB database despite no visible errors.

**System Flow**: REST API → Queue → Worker → Graphiti → FalkorDB

**Status**: 
- ✅ Queue connectivity working
- ✅ Worker polling working  
- ✅ Message format fixed
- ❌ Database persistence failing silently

## Root Cause Analysis

### Primary Suspect: FalkorDB Transaction Handling

The FalkorDB driver has a critical flaw in transaction validation:

```python
# graphiti_core/driver/falkordb_driver.py
async def run(self, query: str | list, **kwargs: Any) -> Any:
    # ... execute query ...
    return None  # ⚠️ ALWAYS RETURNS None - No validation possible
```

**Impact**: No way to detect if database writes actually succeeded.

### Secondary Issues Identified

1. **Missing Return Value Validation**: Bulk operations don't verify node creation
2. **Silent Connection Failures**: No robust FalkorDB connection health checks
3. **Data Serialization Issues**: Potential silent failures in datetime/enum conversion
4. **Entity Extraction Edge Cases**: Empty entity results might prevent episodic node creation

## Debugging Strategy

### Phase 1: Immediate Validation (Priority 1) 🚨

#### 1.1 Database Connection Test

Create `test_database_writes.py`:

```python
import asyncio
from graphiti_core.driver.falkordb_driver import FalkorDriver
from datetime import datetime

async def test_database_connection():
    """Test basic FalkorDB connectivity and write operations"""
    driver = FalkorDriver(
        host="falkordb",  # Use your FalkorDB host
        port=6379,
        database="graphiti_migration"
    )
    
    print("=== Testing FalkorDB Connection ===")
    
    try:
        # Test 1: Basic connectivity
        result = await driver.execute_query("RETURN 1 as test")
        print(f"✅ Connection test: {result}")
        
        # Test 2: Node creation
        test_uuid = f"test-{datetime.now().timestamp()}"
        await driver.execute_query("""
            CREATE (n:TestNode {uuid: $uuid, name: $name, created_at: $created_at})
            RETURN n.uuid as uuid
        """, uuid=test_uuid, name="Test Node", created_at=datetime.now().isoformat())
        
        # Test 3: Verify node was created
        result = await driver.execute_query("""
            MATCH (n:TestNode {uuid: $uuid}) 
            RETURN count(n) as count, n.name as name
        """, uuid=test_uuid)
        print(f"✅ Node creation test: {result}")
        
        # Test 4: Episodic node creation (same as worker)
        episode_uuid = f"episode-{datetime.now().timestamp()}"
        await driver.execute_query("""
            CREATE (n:Episodic {
                uuid: $uuid, 
                name: $name, 
                group_id: $group_id,
                source: $source,
                content: $content,
                created_at: $created_at,
                valid_at: $valid_at
            })
            RETURN n.uuid as uuid
        """, 
        uuid=episode_uuid,
        name="Test Episode",
        group_id="test_group",
        source="message",
        content="Test episode content",
        created_at=datetime.now().isoformat(),
        valid_at=datetime.now().isoformat())
        
        # Test 5: Verify episodic node
        result = await driver.execute_query("""
            MATCH (n:Episodic {uuid: $uuid}) 
            RETURN count(n) as count
        """, uuid=episode_uuid)
        print(f"✅ Episodic node test: {result}")
        
        # Test 6: Check total episodic nodes
        result = await driver.execute_query("MATCH (n:Episodic) RETURN count(n) as total")
        print(f"📊 Total episodic nodes in database: {result}")
        
        # Cleanup
        await driver.execute_query("MATCH (n:TestNode) DELETE n")
        await driver.execute_query(f"MATCH (n:Episodic {{uuid: '{episode_uuid}'}}) DELETE n")
        
        print("✅ Database connection test PASSED")
        return True
        
    except Exception as e:
        print(f"❌ Database test FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    asyncio.run(test_database_connection())
```

**Run this first**: `python test_database_writes.py`

#### 1.2 Enhanced Worker Logging

Add comprehensive logging to `graphiti_core/ingestion/worker.py` in the `_process_episode` method:

```python
async def _process_episode(self, task: IngestionTask):
    """Process an episode ingestion task"""
    payload = task.payload
    
    logger.info(f"=== EPISODE PROCESSING START ===")
    logger.info(f"Task ID: {task.id}")
    logger.info(f"Worker ID: {self.worker_id}")
    logger.info(f"Payload keys: {list(payload.keys())}")
    logger.info(f"Payload content preview: {str(payload)[:200]}...")
    
    try:
        # ... existing validation code ...
        
        logger.info(f"About to call add_episode with:")
        logger.info(f"  group_id: {effective_group_id}")
        logger.info(f"  name: {payload.get('name')}")
        logger.info(f"  content length: {len(payload.get('content', ''))}")
        logger.info(f"  timestamp: {timestamp}")
        
        result = await self.graphiti.add_episode(
            group_id=effective_group_id,
            name=payload.get('name'),
            episode_body=payload.get('content'),
            reference_time=timestamp,
            source=EpisodeType.message,
            source_description=payload.get('source_description')
        )
        
        logger.info(f"=== ADD_EPISODE RESULT ===")
        logger.info(f"Result type: {type(result)}")
        logger.info(f"Result is None: {result is None}")
        
        if result:
            logger.info(f"Episode UUID: {result.episode.uuid if result.episode else 'None'}")
            logger.info(f"Episode name: {result.episode.name if result.episode else 'None'}")
            logger.info(f"Nodes count: {len(result.nodes) if result.nodes else 0}")
            logger.info(f"Edges count: {len(result.edges) if result.edges else 0}")
            
            # CRITICAL: Verify in database immediately
            if result.episode and result.episode.uuid:
                verification_query = """
                MATCH (n:Episodic {uuid: $uuid}) 
                RETURN count(n) as count, n.name as name
                """
                try:
                    db_result = await self.graphiti.driver.execute_query(
                        verification_query, 
                        uuid=result.episode.uuid
                    )
                    logger.info(f"🔍 DATABASE VERIFICATION: {db_result}")
                    
                    if db_result and len(db_result[0]) > 0 and db_result[0][0].get('count', 0) > 0:
                        logger.info(f"✅ Episode {result.episode.uuid} CONFIRMED in database")
                    else:
                        logger.error(f"❌ Episode {result.episode.uuid} NOT FOUND in database!")
                        
                except Exception as verify_error:
                    logger.error(f"❌ Database verification failed: {verify_error}")
        else:
            logger.error(f"❌ add_episode returned None or empty result!")
            
        logger.info(f"=== EPISODE PROCESSING END ===")
        
    except Exception as e:
        logger.error(f"❌ Episode processing failed: {e}")
        logger.error(f"Exception type: {type(e)}")
        import traceback
        logger.error(f"Traceback: {traceback.format_exc()}")
        raise
```

#### 1.3 FalkorDB Query Logging

Modify `graphiti_core/driver/falkordb_driver.py` to log all queries:

```python
async def run(self, query: str | list, **kwargs: Any) -> Any:
    logger.info(f"🔧 EXECUTING FALKORDB QUERY")
    logger.info(f"Query type: {type(query)}")
    
    if isinstance(query, list):
        logger.info(f"Query list length: {len(query)}")
        for i, (cypher, params) in enumerate(query):
            logger.info(f"Query {i}: {str(cypher)[:100]}...")
            logger.info(f"Params {i}: {params}")
            params = convert_datetimes_to_strings(params)
            try:
                result = await self.graph.query(str(cypher), params)
                logger.info(f"Query {i} result: {result}")
            except Exception as e:
                logger.error(f"Query {i} failed: {e}")
                raise
    else:
        logger.info(f"Single query: {str(query)[:100]}...")
        params = dict(kwargs)
        logger.info(f"Query params: {params}")
        params = convert_datetimes_to_strings(params)
        try:
            result = await self.graph.query(str(query), params)
            logger.info(f"Query result: {result}")
        except Exception as e:
            logger.error(f"Query failed: {e}")
            raise
    
    return None
```

### Phase 2: System Monitoring (Priority 2) 📊

#### 2.1 FalkorDB Container Health

```bash
# Monitor FalkorDB logs in real-time
docker logs falkordb --tail 100 -f

# Check FalkorDB memory usage
docker stats falkordb

# Connect directly to FalkorDB
docker exec -it falkordb redis-cli
# In Redis CLI:
GRAPH.QUERY graphiti_migration "MATCH (n:Episodic) RETURN count(n)"
GRAPH.QUERY graphiti_migration "MATCH (n) RETURN labels(n), count(n)"
```

#### 2.2 Worker Container Monitoring

```bash
# Monitor worker logs with enhanced logging
docker logs graphiti-worker-1 --tail 100 -f

# Check worker resource usage
docker stats graphiti-worker-1
```

### Phase 3: Direct Testing (Priority 3) 🧪

#### 3.1 Isolated Episode Creation Test

Create `test_direct_episode.py`:

```python
import asyncio
import os
from datetime import datetime
from graphiti_core.graphiti_types import EpisodeType

async def test_direct_episode_creation():
    """Test episode creation exactly like the worker does"""
    
    # Set environment variables like worker
    os.environ["DRIVER_TYPE"] = "falkordb"
    os.environ["FALKORDB_HOST"] = "falkordb"  # or your host
    os.environ["FALKORDB_PORT"] = "6379"
    os.environ["FALKORDB_DATABASE"] = "graphiti_migration"
    
    # Initialize exactly like worker does
    from worker.zep_graphiti import ZepGraphiti
    from graphiti_core.client_factory import GraphitiClientFactory
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    
    # Create clients
    llm_client = GraphitiClientFactory.create_llm_client()
    embedder = GraphitiClientFactory.create_embedder()
    
    # Create driver
    falkor_driver = FalkorDriver(
        host="falkordb",
        port=6379,
        database="graphiti_migration"
    )
    
    # Create Graphiti instance
    graphiti = ZepGraphiti(
        uri=None,
        llm_client=llm_client,
        embedder=embedder,
        graph_driver=falkor_driver
    )
    
    print("=== Testing Direct Episode Creation ===")
    
    try:
        # Test exactly like worker
        result = await graphiti.add_episode(
            group_id="debug_test_group",
            name="Debug Test Episode",
            episode_body="This is a debug test episode to verify database writes",
            reference_time=datetime.now(),
            source=EpisodeType.message,
            source_description="Direct debug test"
        )
        
        print(f"✅ Episode creation result: {result}")
        print(f"Episode UUID: {result.episode.uuid if result and result.episode else 'None'}")
        print(f"Nodes created: {len(result.nodes) if result and result.nodes else 0}")
        
        # Verify in database
        if result and result.episode:
            count_result = await graphiti.driver.execute_query(
                "MATCH (n:Episodic {uuid: $uuid}) RETURN count(n) as count",
                uuid=result.episode.uuid
            )
            print(f"Database verification: {count_result}")
            
        # Check total count
        total_result = await graphiti.driver.execute_query(
            "MATCH (n:Episodic) RETURN count(n) as total"
        )
        print(f"Total episodic nodes: {total_result}")
        
    except Exception as e:
        print(f"❌ Direct episode test failed: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_direct_episode_creation())
```

## Expected Outcomes

### If Database Connection Test Fails
- **Issue**: FalkorDB connectivity problems
- **Action**: Check FalkorDB container status, network connectivity, credentials

### If Database Test Passes but Worker Fails
- **Issue**: Worker configuration or Graphiti initialization problems  
- **Action**: Compare worker initialization with test script

### If Queries Execute but No Nodes Created
- **Issue**: Transaction rollback or query parameter problems
- **Action**: Examine query parameters and FalkorDB transaction handling

### If Everything Appears to Work but Database is Empty
- **Issue**: Silent transaction failures or wrong database
- **Action**: Verify database name, check FalkorDB persistence settings

## Next Steps

1. **Run Phase 1 tests immediately** - Start with database connection test
2. **Enable enhanced logging** - Deploy worker with additional logging
3. **Monitor in real-time** - Watch logs during message processing
4. **Compare results** - Direct test vs worker behavior

## Success Criteria

- Database connection test creates and verifies nodes ✅
- Worker logs show successful add_episode calls ✅  
- Database verification confirms node creation ✅
- FalkorDB queries return expected node counts ✅

This strategy will systematically identify where in the pipeline data is being lost and provide concrete evidence of the root cause.
