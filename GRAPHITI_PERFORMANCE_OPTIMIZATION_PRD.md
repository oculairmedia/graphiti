# PRD: Graphiti Core Performance Optimization & Search Latency Reduction

## Executive Summary

This PRD outlines a comprehensive performance optimization strategy for Graphiti core, focusing on reducing search latency, improving query performance, and implementing intelligent caching mechanisms to enhance overall system responsiveness.

## Problem Statement

Current performance bottlenecks in Graphiti core include:

1. **Search Latency**: Multi-stage search operations (fulltext + similarity + BFS) create cumulative delays
2. **Embedding Generation**: Real-time embedding creation for queries adds 200-500ms latency
3. **Database Query Overhead**: Multiple sequential database queries without optimization
4. **Memory Inefficiency**: Lack of result caching and redundant computations
5. **Parallel Processing Gaps**: Underutilized concurrent execution opportunities

## Current Performance Analysis

### Search Pipeline Bottlenecks
```python
# Current search flow creates sequential delays:
async def search():
    query_vector = await embedder.create([query])  # 200-500ms
    edges, nodes, episodes, communities = await semaphore_gather(
        edge_search(),    # 100-300ms
        node_search(),    # 100-300ms  
        episode_search(), # 50-150ms
        community_search() # 50-150ms
    )
    # Total: 550-1400ms per search
```

### Identified Performance Issues
1. **Embedding Latency**: Every search requires real-time embedding generation
2. **Database Round-trips**: Multiple queries per search type (fulltext + similarity + BFS)
3. **Result Processing**: Inefficient deduplication and ranking algorithms
4. **Memory Usage**: No caching of frequent queries or embeddings
5. **Connection Overhead**: Database connection management inefficiencies

## Proposed Solutions

### 1. Intelligent Caching System

#### Query Embedding Cache
```python
class EmbeddingCache:
    """LRU cache for query embeddings with semantic similarity matching."""
    
    def __init__(self, max_size: int = 10000, similarity_threshold: float = 0.95):
        self.cache = {}
        self.similarity_threshold = similarity_threshold
        
    async def get_or_create_embedding(self, query: str) -> list[float]:
        # Check for exact match
        if query in self.cache:
            return self.cache[query]
            
        # Check for semantically similar queries
        similar_embedding = await self._find_similar_cached_query(query)
        if similar_embedding:
            return similar_embedding
            
        # Generate new embedding
        embedding = await self.embedder.create([query])
        self.cache[query] = embedding
        return embedding
```

#### Search Result Cache
```python
class SearchResultCache:
    """Time-based cache for search results with invalidation."""
    
    def __init__(self, ttl_seconds: int = 300):  # 5 minute TTL
        self.cache = {}
        self.ttl = ttl_seconds
        
    def get_cached_results(self, query_hash: str) -> Optional[SearchResults]:
        if query_hash in self.cache:
            result, timestamp = self.cache[query_hash]
            if time.time() - timestamp < self.ttl:
                return result
        return None
```

### 2. Database Query Optimization

#### Unified Search Queries
```python
# Replace multiple queries with single optimized query
async def unified_node_search(
    driver: GraphDriver,
    query: str,
    query_vector: list[float],
    search_filter: SearchFilters,
    group_ids: list[str],
    limit: int
) -> list[EntityNode]:
    """Single query combining fulltext, similarity, and BFS search."""
    
    query = """
    // Fulltext search
    CALL db.index.fulltext.queryNodes('node_name_and_summary', $query) 
    YIELD node AS ft_node, score AS ft_score
    
    // Similarity search  
    MATCH (sim_node:Entity)
    WHERE sim_node.group_id IN $group_ids
    WITH sim_node, vector.similarity.cosine(sim_node.name_embedding, $query_vector) AS sim_score
    WHERE sim_score > $min_score
    
    // BFS search (if origin nodes provided)
    OPTIONAL MATCH (origin:Entity)-[*1..$bfs_depth]-(bfs_node:Entity)
    WHERE origin.uuid IN $origin_uuids
    
    // Combine and rank results
    WITH COLLECT(DISTINCT {node: ft_node, score: ft_score, type: 'fulltext'}) +
         COLLECT(DISTINCT {node: sim_node, score: sim_score, type: 'similarity'}) +
         COLLECT(DISTINCT {node: bfs_node, score: 1.0, type: 'bfs'}) AS all_results
         
    UNWIND all_results AS result
    WITH result.node AS n, 
         SUM(result.score) AS combined_score,
         COLLECT(DISTINCT result.type) AS search_types
    ORDER BY combined_score DESC
    LIMIT $limit
    RETURN n, combined_score, search_types
    """
```

#### Connection Pooling & Prepared Statements
```python
class OptimizedGraphDriver:
    """Enhanced driver with connection pooling and query preparation."""
    
    def __init__(self):
        self.connection_pool = ConnectionPool(
            min_connections=5,
            max_connections=20,
            connection_timeout=30
        )
        self.prepared_statements = {}
        
    async def execute_prepared_query(self, query_name: str, **params):
        if query_name not in self.prepared_statements:
            self.prepared_statements[query_name] = await self.prepare_statement(query_name)
        return await self.prepared_statements[query_name].execute(**params)
```

### 3. Parallel Processing Enhancements

#### Async Pipeline Optimization
```python
class SearchPipeline:
    """Optimized search pipeline with intelligent parallelization."""
    
    async def execute_search(self, query: str, config: SearchConfig) -> SearchResults:
        # Stage 1: Parallel embedding and cache lookup
        embedding_task = asyncio.create_task(self.get_query_embedding(query))
        cache_task = asyncio.create_task(self.check_result_cache(query, config))
        
        embedding, cached_result = await asyncio.gather(embedding_task, cache_task)
        
        if cached_result:
            return cached_result
            
        # Stage 2: Parallel search execution with optimized queries
        search_tasks = [
            self.unified_node_search(query, embedding, config),
            self.unified_edge_search(query, embedding, config),
            self.episode_search(query, config),
            self.community_search(query, embedding, config)
        ]
        
        results = await asyncio.gather(*search_tasks, return_exceptions=True)
        
        # Stage 3: Parallel result processing
        final_results = await self.process_and_rank_results(results, config)
        
        # Cache results for future use
        await self.cache_results(query, config, final_results)
        
        return final_results
```

### 4. Memory & Resource Optimization

#### Smart Result Limiting
```python
class AdaptiveSearchLimits:
    """Dynamically adjust search limits based on performance metrics."""
    
    def __init__(self):
        self.performance_history = {}
        self.target_latency_ms = 200
        
    def get_optimal_limit(self, search_type: str, base_limit: int) -> int:
        avg_latency = self.get_average_latency(search_type)
        
        if avg_latency > self.target_latency_ms:
            # Reduce limit to improve performance
            return max(base_limit // 2, 10)
        elif avg_latency < self.target_latency_ms * 0.5:
            # Increase limit for better results
            return min(base_limit * 2, 1000)
            
        return base_limit
```

#### Memory-Efficient Processing
```python
class StreamingResultProcessor:
    """Process search results in streams to reduce memory usage."""
    
    async def process_large_resultset(self, query_results: AsyncIterator) -> SearchResults:
        processed_nodes = []
        
        async for batch in self.batch_iterator(query_results, batch_size=100):
            # Process in small batches to control memory usage
            batch_processed = await self.process_batch(batch)
            processed_nodes.extend(batch_processed)
            
            # Yield control to prevent blocking
            await asyncio.sleep(0)
            
        return SearchResults(nodes=processed_nodes)
```

## Implementation Plan

### Phase 1: Core Caching (Weeks 1-2)
1. Implement embedding cache with LRU eviction
2. Add search result cache with TTL-based invalidation
3. Create cache warming strategies for common queries
4. Add cache hit/miss metrics and monitoring

### Phase 2: Query Optimization (Weeks 3-4)
1. Develop unified search queries for each entity type
2. Implement connection pooling and prepared statements
3. Add query performance monitoring and slow query logging
4. Optimize database indexes for search patterns

### Phase 3: Parallel Processing (Weeks 5-6)
1. Refactor search pipeline for maximum parallelization
2. Implement adaptive search limits based on performance
3. Add streaming result processing for large datasets
4. Create performance benchmarking and regression testing

### Phase 4: Advanced Optimizations (Weeks 7-8)
1. Implement semantic query similarity matching
2. Add predictive caching based on user patterns
3. Create performance dashboard and alerting
4. Optimize memory usage and garbage collection

## Performance Targets

### Latency Reduction Goals
- **Search Latency**: Reduce from 550-1400ms to 100-300ms (70% improvement)
- **Embedding Generation**: Reduce cache misses from 100% to <20%
- **Database Queries**: Reduce query count per search by 60%
- **Memory Usage**: Reduce peak memory usage by 40%

### Success Metrics
1. **P95 Search Latency** < 300ms
2. **Cache Hit Rate** > 80% for embeddings, >60% for search results
3. **Database Connection Utilization** < 70%
4. **Memory Growth Rate** < 5% per hour under load
5. **Concurrent Search Capacity** > 100 searches/second

## Risk Mitigation

### Performance Risks
1. **Cache Memory Usage**: Implement LRU eviction and memory monitoring
2. **Cache Invalidation**: Use TTL and event-based invalidation strategies
3. **Database Load**: Implement circuit breakers and rate limiting
4. **Complexity**: Maintain backward compatibility and gradual rollout

### Monitoring & Alerting
1. **Performance Dashboards**: Real-time latency and throughput metrics
2. **Cache Monitoring**: Hit rates, memory usage, eviction patterns
3. **Database Monitoring**: Query performance, connection pool status
4. **Error Tracking**: Cache failures, timeout errors, performance regressions

## Future Enhancements

1. **Machine Learning**: Predictive caching based on user behavior patterns
2. **Distributed Caching**: Redis-based shared cache for multi-instance deployments
3. **Query Optimization**: AI-powered query plan optimization
4. **Hardware Acceleration**: GPU-accelerated similarity computations
