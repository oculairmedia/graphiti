#!/usr/bin/env python3
"""
Graphiti Relevance Feedback Performance Optimizer
Implements caching, batching, and async processing for improved performance
"""

import asyncio
import json
import redis
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from functools import lru_cache
from concurrent.futures import ThreadPoolExecutor
import hashlib
import pickle

class PerformanceOptimizer:
    """Optimizes relevance feedback system performance"""
    
    def __init__(self, redis_host='localhost', redis_port=6389):
        self.redis_client = redis.Redis(host=redis_host, port=redis_port, decode_responses=False)
        self.cache_ttl = 3600  # 1 hour cache TTL
        self.batch_size = 100
        self.executor = ThreadPoolExecutor(max_workers=4)
        
    # 1. MEMORY CACHING LAYER
    @lru_cache(maxsize=1000)
    def get_cached_relevance(self, memory_id: str) -> Optional[float]:
        """In-memory LRU cache for frequently accessed scores"""
        return self._get_redis_cached_score(memory_id)
    
    def _get_redis_cached_score(self, memory_id: str) -> Optional[float]:
        """Redis-based distributed cache"""
        cache_key = f"relevance:cache:{memory_id}"
        cached = self.redis_client.get(cache_key)
        if cached:
            return float(cached)
        return None
    
    def set_cached_relevance(self, memory_id: str, score: float):
        """Set score in both memory and Redis cache"""
        cache_key = f"relevance:cache:{memory_id}"
        self.redis_client.setex(cache_key, self.cache_ttl, str(score))
        # Clear LRU cache to force refresh
        if hasattr(self.get_cached_relevance, 'cache_clear'):
            self.get_cached_relevance.cache_clear()
    
    # 2. BATCH PROCESSING
    async def batch_update_scores(self, memory_scores: Dict[str, float]) -> Dict[str, bool]:
        """Batch update relevance scores for multiple memories"""
        results = {}
        
        # Process in batches
        items = list(memory_scores.items())
        for i in range(0, len(items), self.batch_size):
            batch = dict(items[i:i + self.batch_size])
            
            # Build batch query
            query, params = self._build_batch_update_query(batch)
            
            # Execute async
            try:
                await self._execute_batch_query_with_params(query, params)
                for memory_id in batch:
                    results[memory_id] = True
                    self.set_cached_relevance(memory_id, batch[memory_id])
            except Exception as e:
                print(f"Batch update failed: {e}")
                for memory_id in batch:
                    results[memory_id] = False
                    
        return results
    
    def _build_batch_update_query(self, batch: Dict[str, float]) -> str:
        """Build optimized batch update Cypher query"""
        # Use UNWIND for batch processing
        params = []
        for memory_id, score in batch.items():
            params.append({
                'uuid': memory_id,
                'score': score,
                'timestamp': datetime.utcnow().isoformat()
            })
        
        query = """
            UNWIND $params as param
            MATCH (n {uuid: param.uuid})
            SET n.avg_relevance = param.score,
                n.usage_count = COALESCE(n.usage_count, 0) + 1,
                n.last_scored = param.timestamp
            RETURN COUNT(n) as updated
        """
        
        return query, params
    
    async def _execute_batch_query_with_params(self, query: str, params: List[Dict]):
        """Execute batch query asynchronously with parameters"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._run_graph_query_with_params,
            query,
            {'params': params}
        )
    
    async def _execute_batch_query(self, query: str, batch: Dict[str, float]):
        """Execute batch query asynchronously"""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            self.executor,
            self._run_graph_query,
            query
        )
    
    def _run_graph_query(self, query: str):
        """Execute graph query in thread pool"""
        from redis.commands.graph import Graph
        graph = Graph(self.redis_client, 'graphiti_migration')
        return graph.query(query)
    
    def _run_graph_query_with_params(self, query: str, params: Dict):
        """Execute graph query with parameters in thread pool"""
        from redis.commands.graph import Graph
        graph = Graph(self.redis_client, 'graphiti_migration')
        return graph.query(query, params)
    
    # 3. QUERY OPTIMIZATION
    def create_relevance_index(self):
        """Create indexes for faster relevance queries"""
        queries = [
            "CREATE INDEX ON :EntityNode(avg_relevance)",
            "CREATE INDEX ON :EntityNode(usage_count)",
            "CREATE INDEX ON :EntityNode(last_scored)",
            "CREATE INDEX ON :FactNode(avg_relevance)",
            "CREATE INDEX ON :FactNode(usage_count)"
        ]
        
        from redis.commands.graph import Graph
        graph = Graph(self.redis_client, 'graphiti_migration')
        
        for query in queries:
            try:
                graph.query(query)
                print(f"✅ Created index: {query}")
            except Exception as e:
                if "already exists" not in str(e):
                    print(f"⚠️ Index creation failed: {e}")
    
    # 4. PREFETCHING & PRECOMPUTATION
    async def prefetch_high_relevance_nodes(self, threshold: float = 0.7) -> List[Dict]:
        """Prefetch and cache high-relevance nodes"""
        query = f"""
            MATCH (n)
            WHERE n.avg_relevance >= {threshold}
            RETURN n.uuid as id, n.avg_relevance as score, n.content as content
            ORDER BY n.avg_relevance DESC
            LIMIT 100
        """
        
        result = await self._execute_batch_query(query, {})
        
        # Cache results if we got any
        nodes = []
        if result and result.result_set:
            for row in result.result_set:
                node = {
                    'id': row[0] if len(row) > 0 else None,
                    'score': row[1] if len(row) > 1 else 0,
                    'content': row[2] if len(row) > 2 else ''
                }
                if node['id']:
                    self.set_cached_relevance(node['id'], node['score'])
                    nodes.append(node)
            
        return nodes
    
    # 5. CONNECTION POOLING
    def setup_connection_pool(self, max_connections: int = 10):
        """Setup Redis connection pool for better concurrency"""
        pool = redis.ConnectionPool(
            host='localhost',
            port=6389,
            max_connections=max_connections,
            decode_responses=False
        )
        self.redis_client = redis.Redis(connection_pool=pool)
        print(f"✅ Connection pool setup with {max_connections} connections")
    
    # 6. ASYNC FEEDBACK PROCESSOR
    async def process_feedback_async(self, feedback_data: Dict) -> Dict:
        """Process feedback asynchronously with all optimizations"""
        query_id = feedback_data.get('query_id')
        memory_scores = feedback_data.get('memory_scores', {})
        
        # Check cache first
        cached_results = {}
        uncached = {}
        
        for memory_id, score in memory_scores.items():
            cached_score = self.get_cached_relevance(memory_id)
            if cached_score is not None:
                cached_results[memory_id] = cached_score
            else:
                uncached[memory_id] = score
        
        # Batch update uncached scores
        if uncached:
            update_results = await self.batch_update_scores(uncached)
            
        return {
            'query_id': query_id,
            'cached': len(cached_results),
            'updated': len(uncached),
            'total': len(memory_scores),
            'success': True
        }
    
    # 7. BULK OPERATIONS
    async def bulk_recalculate_relevance(self, decay_factor: float = 0.95):
        """Bulk recalculate all relevance scores with decay"""
        query = f"""
            MATCH (n)
            WHERE n.avg_relevance IS NOT NULL
            SET n.avg_relevance = n.avg_relevance * {decay_factor}
            RETURN COUNT(n) as updated
        """
        
        result = await self._execute_batch_query(query, {})
        print(f"✅ Bulk updated {result} nodes with decay factor {decay_factor}")
        
        # Clear all caches
        self.redis_client.delete(*self.redis_client.keys("relevance:cache:*"))
        if hasattr(self.get_cached_relevance, 'cache_clear'):
            self.get_cached_relevance.cache_clear()
            
        return result
    
    # 8. MONITORING & METRICS
    def get_performance_metrics(self) -> Dict:
        """Get current performance metrics"""
        from redis.commands.graph import Graph
        graph = Graph(self.redis_client, 'graphiti_migration')
        
        metrics_query = """
            MATCH (n)
            WHERE n.avg_relevance IS NOT NULL
            RETURN 
                COUNT(n) as total_scored,
                AVG(n.avg_relevance) as avg_score,
                MAX(n.usage_count) as max_uses,
                MIN(n.avg_relevance) as min_score,
                MAX(n.avg_relevance) as max_score
        """
        
        result = graph.query(metrics_query)
        
        cache_stats = {
            'cache_keys': len(self.redis_client.keys("relevance:cache:*")),
            'lru_info': self.get_cached_relevance.cache_info() if hasattr(self.get_cached_relevance, 'cache_info') else None
        }
        
        return {
            'graph_metrics': result.result_set[0] if result.result_set else {},
            'cache_stats': cache_stats,
            'connection_pool': {
                'active': self.redis_client.connection_pool.connection_kwargs
            }
        }


async def main():
    """Test and demonstrate performance optimizations"""
    print("🚀 Graphiti Relevance Performance Optimizer")
    print("=" * 60)
    
    optimizer = PerformanceOptimizer()
    
    # 1. Setup optimizations
    print("\n1️⃣ Setting up optimizations...")
    optimizer.setup_connection_pool(max_connections=10)
    optimizer.create_relevance_index()
    
    # 2. Test batch updates
    print("\n2️⃣ Testing batch updates...")
    test_scores = {
        f"test_memory_{i}": 0.5 + (i * 0.01) 
        for i in range(10)
    }
    
    results = await optimizer.batch_update_scores(test_scores)
    print(f"  ✅ Batch updated {sum(results.values())} memories")
    
    # 3. Test prefetching
    print("\n3️⃣ Testing prefetch...")
    high_relevance = await optimizer.prefetch_high_relevance_nodes(threshold=0.5)
    print(f"  ✅ Prefetched {len(high_relevance)} high-relevance nodes")
    
    # 4. Test async processing
    print("\n4️⃣ Testing async feedback processing...")
    feedback = {
        'query_id': 'perf_test_001',
        'memory_scores': test_scores
    }
    
    result = await optimizer.process_feedback_async(feedback)
    print(f"  ✅ Processed: {result}")
    
    # 5. Show metrics
    print("\n5️⃣ Performance Metrics:")
    metrics = optimizer.get_performance_metrics()
    print(json.dumps(metrics, indent=2, default=str))
    
    print("\n✅ Performance optimizations complete!")
    
    return optimizer


if __name__ == "__main__":
    optimizer = asyncio.run(main())