"""
Copyright 2024, Zep Software, Inc.

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import logging
from typing import Any, Optional

from graphiti_core.driver.driver import GraphDriver
from graphiti_core.graphiti_types import GraphitiClients
from graphiti_core.llm_client.client import LLMClient
from graphiti_core.relevance import RelevanceScorer, ScoringConfig
from graphiti_core.search.search import search
from graphiti_core.search.search_config import SearchConfig, SearchResults
from graphiti_core.search.search_filters import SearchFilters

logger = logging.getLogger(__name__)


class RelevanceEnhancedSearch:
    """Search with integrated relevance scoring and feedback."""
    
    def __init__(
        self,
        clients: GraphitiClients,
        scorer: Optional[RelevanceScorer] = None,
        config: Optional[ScoringConfig] = None
    ):
        self.clients = clients
        self.config = config or ScoringConfig()
        
        # Initialize scorer if not provided
        if scorer:
            self.scorer = scorer
        else:
            self.scorer = RelevanceScorer(
                clients.driver,
                clients.llm_client if hasattr(clients, 'llm_client') else None,
                self.config
            )
    
    async def search_with_relevance(
        self,
        query: str,
        group_ids: Optional[list[str]] = None,
        search_config: Optional[SearchConfig] = None,
        search_filter: Optional[SearchFilters] = None,
        center_node_uuid: Optional[str] = None,
        bfs_origin_node_uuids: Optional[list[str]] = None,
        query_vector: Optional[list[float]] = None,
        include_relevance_scores: bool = True,
        apply_relevance_filter: bool = True,
        auto_update_scores: bool = False
    ) -> SearchResults:
        """
        Perform search with relevance scoring integration.
        
        Args:
            query: Search query
            group_ids: Group IDs to search within
            search_config: Search configuration
            search_filter: Search filters
            center_node_uuid: Center node for distance-based reranking
            bfs_origin_node_uuids: Origin nodes for BFS
            query_vector: Pre-computed query embedding
            include_relevance_scores: Include historical relevance scores
            apply_relevance_filter: Filter results by minimum relevance
            auto_update_scores: Automatically update usage counts
            
        Returns:
            SearchResults with relevance enhancements
        """
        # Perform base search
        results = await search(
            self.clients,
            query,
            group_ids,
            search_config or SearchConfig(),
            search_filter or SearchFilters(),
            center_node_uuid,
            bfs_origin_node_uuids,
            query_vector
        )
        
        if not include_relevance_scores and not apply_relevance_filter:
            return results
        
        # Enhance results with relevance scores
        enhanced_results = await self._enhance_with_relevance(
            results,
            query,
            apply_relevance_filter,
            auto_update_scores
        )
        
        return enhanced_results
    
    async def _enhance_with_relevance(
        self,
        results: SearchResults,
        query: str,
        apply_filter: bool,
        auto_update: bool
    ) -> SearchResults:
        """Enhance search results with relevance scoring."""
        driver = self.clients.driver
        
        # Process entity nodes
        if results.entity_nodes:
            enhanced_nodes = []
            for node in results.entity_nodes:
                # Load feedback for the node
                feedback = await self.scorer._load_feedback(node.uuid)
                
                if feedback:
                    # Apply decay if enabled
                    if self.config.enable_decay:
                        feedback.apply_decay(self.config.half_life_days)
                    
                    effective_score = feedback.get_effective_score()
                    
                    # Filter by minimum relevance if enabled
                    if apply_filter and effective_score < self.config.min_relevance_threshold:
                        continue
                    
                    # Add relevance data to node attributes
                    node.attributes['relevance_score'] = effective_score
                    node.attributes['usage_count'] = feedback.usage_count
                    node.attributes['last_accessed'] = feedback.last_accessed
                    
                    # Update usage count if enabled
                    if auto_update:
                        feedback.usage_count += 1
                        feedback.last_accessed = feedback.last_accessed
                        await self.scorer._save_feedback(feedback)
                
                enhanced_nodes.append(node)
            
            # Sort by relevance score if available
            enhanced_nodes.sort(
                key=lambda n: n.attributes.get('relevance_score', 0.0),
                reverse=True
            )
            results.entity_nodes = enhanced_nodes
        
        # Process edges similarly
        if results.entity_edges:
            enhanced_edges = []
            for edge in results.entity_edges:
                feedback = await self.scorer._load_feedback(edge.uuid)
                
                if feedback:
                    if self.config.enable_decay:
                        feedback.apply_decay(self.config.half_life_days)
                    
                    effective_score = feedback.get_effective_score()
                    
                    if apply_filter and effective_score < self.config.min_relevance_threshold:
                        continue
                    
                    # Store relevance data (edges don't have attributes dict)
                    # We'll add it as a temporary field
                    edge._relevance_score = effective_score
                    edge._usage_count = feedback.usage_count
                    
                    if auto_update:
                        feedback.usage_count += 1
                        feedback.last_accessed = feedback.last_accessed
                        await self.scorer._save_feedback(feedback)
                
                enhanced_edges.append(edge)
            
            enhanced_edges.sort(
                key=lambda e: getattr(e, '_relevance_score', 0.0),
                reverse=True
            )
            results.entity_edges = enhanced_edges
        
        return results
    
    async def apply_relevance_boost(
        self,
        results: SearchResults,
        semantic_scores: Optional[dict[str, float]] = None,
        keyword_scores: Optional[dict[str, float]] = None,
        graph_scores: Optional[dict[str, float]] = None
    ) -> SearchResults:
        """
        Apply relevance boosting using multiple score sources.
        
        Args:
            results: Search results to boost
            semantic_scores: Semantic similarity scores by ID
            keyword_scores: Keyword (BM25) scores by ID
            graph_scores: Graph traversal scores by ID
            
        Returns:
            Results reranked with combined scores
        """
        if results.entity_nodes:
            node_scores = {}
            
            for node in results.entity_nodes:
                # Load historical score
                feedback = await self.scorer._load_feedback(node.uuid)
                historical_score = feedback.get_effective_score() if feedback else None
                
                # Combine scores
                combined = await self.scorer.combine_scores(
                    node.uuid,
                    semantic_scores.get(node.uuid) if semantic_scores else None,
                    keyword_scores.get(node.uuid) if keyword_scores else None,
                    graph_scores.get(node.uuid) if graph_scores else None,
                    historical_score
                )
                
                node_scores[node.uuid] = combined
                node.attributes['combined_relevance'] = combined
            
            # Sort by combined score
            results.entity_nodes.sort(
                key=lambda n: node_scores.get(n.uuid, 0.0),
                reverse=True
            )
        
        return results
    
    async def apply_rrf_reranking(
        self,
        semantic_results: list[str],
        keyword_results: list[str],
        graph_results: Optional[list[str]] = None,
        historical_results: Optional[list[str]] = None
    ) -> list[tuple[str, float]]:
        """
        Apply Reciprocal Rank Fusion to combine multiple result lists.
        
        Args:
            semantic_results: IDs ranked by semantic similarity
            keyword_results: IDs ranked by keyword search
            graph_results: IDs ranked by graph traversal
            historical_results: IDs ranked by historical relevance
            
        Returns:
            List of (id, rrf_score) tuples
        """
        rankings = {
            "semantic": semantic_results,
            "keyword": keyword_results
        }
        
        if graph_results:
            rankings["graph"] = graph_results
        
        if historical_results:
            rankings["historical"] = historical_results
        
        return await self.scorer.apply_reciprocal_rank_fusion(
            rankings,
            self.config.rrf_k
        )
    
    async def get_high_relevance_memories(
        self,
        group_ids: list[str],
        limit: int = 100
    ) -> list[dict[str, Any]]:
        """
        Get memories with high relevance scores for caching.
        
        Args:
            group_ids: Group IDs to query
            limit: Maximum number of results
            
        Returns:
            List of high-relevance memories
        """
        driver = self.clients.driver
        
        query = """
        MATCH (n:Entity)
        WHERE n.group_id IN $group_ids
          AND n.avg_relevance >= $threshold
        RETURN 
            n.uuid AS id,
            n.name AS content,
            n.avg_relevance AS relevance,
            n.usage_count AS usage,
            n.last_accessed AS last_accessed,
            n.summary AS summary
        ORDER BY n.avg_relevance DESC
        LIMIT $limit
        """
        
        records, _, _ = await driver.execute_query(
            query,
            group_ids=group_ids,
            threshold=self.config.high_relevance_threshold,
            limit=limit,
            routing_='r'
        )
        
        return [dict(record) for record in records]