#!/usr/bin/env python3
"""
Maintenance script to find and merge duplicate entities in Graphiti.
This script identifies entities with similar names and merges them to reduce duplicates.
"""

import asyncio
import logging
from datetime import datetime
from time import time
from typing import List, Dict, Tuple
import numpy as np
import os
import httpx

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode
from graphiti_core.driver.driver import GraphDriver
from graphiti_core.llm_client import LLMClient
from graphiti_core.utils.maintenance.node_operations import dedupe_node_list
from graphiti_core.helpers import normalize_l2
from graphiti_core.embedder import EmbedderClient

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EntityDeduplicator:
    """Handles entity deduplication in Graphiti"""
    
    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.driver = graphiti.driver
        self.llm_client = graphiti.llm_client
        self.embedder = graphiti.embedder
        
    async def find_duplicate_candidates(self, 
                                      group_id: str = None,
                                      similarity_threshold: float = 0.92,
                                      name_similarity_threshold: float = 0.95) -> List[List[EntityNode]]:
        """Find groups of potentially duplicate entities based on name similarity"""
        logger.info("Finding duplicate entity candidates...")
        
        # Get all entities (or for specific group)
        query = """
        MATCH (n:Entity)
        WHERE ($group_id IS NULL OR n.group_id = $group_id)
        RETURN n.uuid as uuid, n.name as name, n.name_embedding as name_embedding,
               n.group_id as group_id, n.summary as summary, n.created_at as created_at,
               labels(n) as labels
        ORDER BY n.name
        """
        
        records, _, _ = await self.driver.execute_query(
            query,
            group_id=group_id
        )
        
        # Convert to EntityNode objects
        entities = []
        for record in records:
            entity_data = {
                "uuid": record.get("uuid"),
                "name": record.get("name"),
                "name_embedding": record.get("name_embedding"),
                "group_id": record.get("group_id"),
                "summary": record.get("summary"),
                "created_at": record.get("created_at"),
                "labels": record.get("labels", ["Entity"])
            }
            entities.append(EntityNode(**entity_data))
            
        logger.info(f"Found {len(entities)} total entities")
        
        # Group entities by potential duplicates
        duplicate_groups = []
        processed_uuids = set()
        
        for i, entity1 in enumerate(entities):
            if entity1.uuid in processed_uuids:
                continue
                
            current_group = [entity1]
            processed_uuids.add(entity1.uuid)
            
            for j, entity2 in enumerate(entities[i+1:], i+1):
                if entity2.uuid in processed_uuids:
                    continue
                    
                # Check name similarity
                if self._are_names_similar(entity1.name, entity2.name, name_similarity_threshold):
                    current_group.append(entity2)
                    processed_uuids.add(entity2.uuid)
                    continue
                    
                # Check embedding similarity if available
                if entity1.name_embedding and entity2.name_embedding:
                    similarity = np.dot(
                        normalize_l2(entity1.name_embedding),
                        normalize_l2(entity2.name_embedding)
                    )
                    if similarity >= similarity_threshold:
                        current_group.append(entity2)
                        processed_uuids.add(entity2.uuid)
                        
            # Only add groups with duplicates
            if len(current_group) > 1:
                duplicate_groups.append(current_group)
                
        logger.info(f"Found {len(duplicate_groups)} groups of potential duplicates")
        return duplicate_groups
        
    def _normalize_name(self, name: str) -> str:
        """Enhanced normalization for entity names"""
        # Convert to lowercase and strip
        normalized = name.lower().strip()
        
        # Replace underscores with spaces
        normalized = normalized.replace('_', ' ')
        
        # Remove common suffixes
        suffixes_to_remove = ['(system)', '(user)', '(bot)', '(ai)']
        for suffix in suffixes_to_remove:
            if normalized.endswith(suffix):
                normalized = normalized[:-len(suffix)].strip()
        
        # Remove special characters but keep alphanumeric and spaces
        import re
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        
        # Normalize multiple spaces to single space
        normalized = ' '.join(normalized.split())
        
        return normalized
    
    def _is_compound_name(self, name1: str, name2: str) -> bool:
        """Check if one name is a compound version of the other"""
        norm1 = self._normalize_name(name1)
        norm2 = self._normalize_name(name2)
        
        words1 = norm1.split()
        words2 = norm2.split()
        
        # If one has more words, it might be a compound
        if abs(len(words1) - len(words2)) >= 1:
            # Check if shorter is prefix of longer
            shorter = words1 if len(words1) < len(words2) else words2
            longer = words1 if len(words1) > len(words2) else words2
            
            # If shorter name is start of longer, they're likely different entities
            # e.g., "claude" vs "claude code", "github" vs "github actions"
            if ' '.join(longer[:len(shorter)]) == ' '.join(shorter):
                return True
        
        return False
    
    def _are_names_similar(self, name1: str, name2: str, threshold: float) -> bool:
        """Check if two names are similar enough to be duplicates"""
        # Normalize names with enhanced normalization
        norm1 = self._normalize_name(name1)
        norm2 = self._normalize_name(name2)
        
        # Exact match
        if norm1 == norm2:
            return True
        
        # Check if one is a compound name of the other (e.g., "claude" vs "claude code")
        if self._is_compound_name(name1, name2):
            return False  # Don't merge compound names
            
        # Check word overlap for multi-word names
        words1 = set(norm1.split())
        words2 = set(norm2.split())
        
        if len(words1) > 1 and len(words2) > 1:
            overlap = len(words1.intersection(words2))
            total = len(words1.union(words2))
            # Increase threshold for multi-word names to 0.95
            if overlap / total >= 0.95:
                return True
                
        return False
        
    def _should_auto_merge(self, duplicate_nodes: List[EntityNode], confidence_threshold: float = 0.95) -> bool:
        """Check if all nodes in group have high enough similarity to auto-merge without LLM"""
        if len(duplicate_nodes) < 2:
            return False
            
        # Check if all names are similar after normalization
        normalized_names = [self._normalize_name(node.name) for node in duplicate_nodes]
        base_name = normalized_names[0]
        
        # Debug logging for large groups
        if len(duplicate_nodes) > 100:
            unique_normalized = set(normalized_names)
            logger.info(f"Checking auto-merge for {len(duplicate_nodes)} nodes with {len(unique_normalized)} unique normalized names")
            logger.info(f"First 10 unique normalized names: {list(unique_normalized)[:10]}")
        
        # For large groups with a clear base pattern, check if most names match
        if len(duplicate_nodes) > 50:
            # Count how many names exactly match (no substring matching)
            matching_count = 0
            for norm_name in normalized_names:
                if norm_name == base_name:
                    matching_count += 1
            
            # Increase threshold to 95% and require exact matches
            match_ratio = matching_count / len(normalized_names)
            if match_ratio >= 0.95:
                logger.info(f"Auto-merging {len(duplicate_nodes)} nodes: {match_ratio:.1%} exactly match '{base_name}'")
                return True
            else:
                logger.info(f"Not auto-merging {len(duplicate_nodes)} nodes: only {match_ratio:.1%} exactly match '{base_name}'")
                return False
        
        # For smaller groups, require ALL to be exactly the same
        for norm_name in normalized_names[1:]:
            if norm_name != base_name:
                return False
                
        # Check embedding similarities if available for at least some nodes
        nodes_with_embeddings = [n for n in duplicate_nodes if n.name_embedding is not None]
        if len(nodes_with_embeddings) >= 2:
            # Check all pairs of nodes with embeddings have high similarity
            for i in range(len(nodes_with_embeddings)):
                for j in range(i + 1, len(nodes_with_embeddings)):
                    similarity = np.dot(
                        normalize_l2(nodes_with_embeddings[i].name_embedding),
                        normalize_l2(nodes_with_embeddings[j].name_embedding)
                    )
                    if similarity < confidence_threshold:
                        return False
        
        # If we have strong name similarity and either:
        # 1. No embeddings to check, or
        # 2. All available embeddings are similar
        # Then we should auto-merge
        return True
    
    async def merge_duplicate_group(self, duplicate_nodes: List[EntityNode]) -> Tuple[EntityNode, Dict[str, str]]:
        """Merge a group of duplicate nodes using LLM-based deduplication or auto-merge"""
        if len(duplicate_nodes) < 2:
            return duplicate_nodes[0], {}
            
        logger.info(f"Processing {len(duplicate_nodes)} duplicate nodes: {[n.name for n in duplicate_nodes]}")
        
        # Check if we should auto-merge based on high confidence
        if self._should_auto_merge(duplicate_nodes):
            logger.info(f"Auto-merging high-confidence duplicates (skipping LLM)")
            
            # Sort by creation date to keep the oldest as primary
            sorted_nodes = sorted(duplicate_nodes, key=lambda n: n.created_at or "")
            primary_node = sorted_nodes[0]
            
            # Create uuid map for all duplicates
            uuid_map = {}
            for node in sorted_nodes[1:]:
                uuid_map[node.uuid] = primary_node.uuid
                
            # Create a synthetic summary combining all names
            unique_names = list(set(n.name for n in duplicate_nodes))
            primary_node.summary = f"Entity representing: {', '.join(unique_names[:3])}"
            if len(unique_names) > 3:
                primary_node.summary += f" and {len(unique_names) - 3} more variations"
        else:
            # Use LLM for ambiguous cases
            logger.info(f"Using LLM to merge {len(duplicate_nodes)} nodes")
            resolved_nodes, uuid_map = await dedupe_node_list(
                self.llm_client,
                duplicate_nodes
            )
            
            # The primary node (first in resolved list) will be kept
            primary_node = resolved_nodes[0] if resolved_nodes else duplicate_nodes[0]
        
        # Update edges to point to primary node
        await self._update_edges_for_merged_nodes(primary_node.uuid, uuid_map)
        
        # Delete duplicate nodes
        await self._delete_duplicate_nodes(primary_node.uuid, uuid_map)
        
        return primary_node, uuid_map
        
    async def _update_edges_for_merged_nodes(self, primary_uuid: str, uuid_map: Dict[str, str]):
        """Update edges to point to the primary node instead of duplicates"""
        duplicate_uuids = [old_uuid for old_uuid, new_uuid in uuid_map.items() 
                          if new_uuid == primary_uuid and old_uuid != primary_uuid]
        
        if not duplicate_uuids:
            return
            
        # Update edges where duplicate is source
        update_source_query = """
        UNWIND $duplicate_uuids AS dup_uuid
        MATCH (n:Entity {uuid: dup_uuid})-[r]->(m)
        WHERE n.uuid <> $primary_uuid
        WITH r, m
        MATCH (primary:Entity {uuid: $primary_uuid})
        MERGE (primary)-[new_r:RELATES_TO]->(m)
        SET new_r = properties(r)
        DELETE r
        """
        
        # Update edges where duplicate is target
        update_target_query = """
        UNWIND $duplicate_uuids AS dup_uuid
        MATCH (m)-[r]->(n:Entity {uuid: dup_uuid})
        WHERE n.uuid <> $primary_uuid
        WITH r, m
        MATCH (primary:Entity {uuid: $primary_uuid})
        MERGE (m)-[new_r:RELATES_TO]->(primary)
        SET new_r = properties(r)
        DELETE r
        """
        
        # Execute updates
        await self.driver.execute_query(update_source_query, 
            duplicate_uuids=duplicate_uuids,
            primary_uuid=primary_uuid
        )
        
        await self.driver.execute_query(update_target_query, 
            duplicate_uuids=duplicate_uuids,
            primary_uuid=primary_uuid
        )
        
        logger.info(f"Updated edges for {len(duplicate_uuids)} duplicate nodes")
        
    async def _delete_duplicate_nodes(self, primary_uuid: str, uuid_map: Dict[str, str]):
        """Delete duplicate nodes that have been merged"""
        duplicate_uuids = [old_uuid for old_uuid, new_uuid in uuid_map.items() 
                          if new_uuid == primary_uuid and old_uuid != primary_uuid]
        
        if not duplicate_uuids:
            return
            
        delete_query = """
        UNWIND $duplicate_uuids AS dup_uuid
        MATCH (n:Entity {uuid: dup_uuid})
        WHERE n.uuid <> $primary_uuid
        DETACH DELETE n
        RETURN count(n) as deleted_count
        """
        
        records, _, _ = await self.driver.execute_query(delete_query, 
            duplicate_uuids=duplicate_uuids,
            primary_uuid=primary_uuid
        )
        
        deleted_count = records[0].get("deleted_count", 0) if records else 0
        logger.info(f"Deleted {deleted_count} duplicate nodes")
        
    async def run_deduplication(self, 
                              group_id: str = None,
                              dry_run: bool = False,
                              batch_size: int = 10,
                              max_groups: int = None) -> Dict[str, any]:
        """Run the full deduplication process"""
        start_time = datetime.now()
        
        # Find duplicate candidates
        duplicate_groups = await self.find_duplicate_candidates(group_id)
        
        # Limit groups if specified
        if max_groups is not None:
            duplicate_groups = duplicate_groups[:max_groups]
            logger.info(f"Limited to first {max_groups} groups for processing")
        
        if not duplicate_groups:
            logger.info("No duplicate entities found")
            return {
                "duration": str(datetime.now() - start_time),
                "groups_found": 0,
                "entities_merged": 0,
                "dry_run": dry_run
            }
            
        # Process in batches
        total_merged = 0
        merge_results = []
        
        for i in range(0, len(duplicate_groups), batch_size):
            batch = duplicate_groups[i:i + batch_size]
            
            logger.info(f"Processing batch {i//batch_size + 1} of {(len(duplicate_groups) + batch_size - 1)//batch_size}")
            
            for j, group in enumerate(batch):
                group_start_time = time()
                if dry_run:
                    # Just log what would be merged
                    logger.info(f"Would merge {len(group)} entities: {[n.name for n in group]}")
                    total_merged += len(group) - 1
                else:
                    # Actually merge
                    group_index = i + j + 1
                    total_groups = len(duplicate_groups)
                    logger.info(f"Processing group {group_index}/{total_groups} ({len(group)} entities to merge)")
                    primary_node, uuid_map = await self.merge_duplicate_group(group)
                    total_merged += len(uuid_map)
                    merge_results.append({
                        "primary": primary_node.name,
                        "merged_count": len(uuid_map)
                    })
                    group_end_time = time()
                    group_duration = group_end_time - group_start_time
                    logger.info(f"Completed group {group_index}/{total_groups} in {group_duration:.2f}s - Merged {len(uuid_map)} into '{primary_node.name}'")
                    
                    # Estimate remaining time
                    avg_time_per_group = (time() - start_time.timestamp()) / group_index
                    remaining_groups = total_groups - group_index
                    est_remaining_time = avg_time_per_group * remaining_groups
                    logger.info(f"Estimated time remaining: {est_remaining_time/60:.1f} minutes")
                    
        duration = datetime.now() - start_time
        
        result = {
            "duration": str(duration),
            "groups_found": len(duplicate_groups),
            "entities_merged": total_merged,
            "dry_run": dry_run
        }
        
        if not dry_run:
            result["merge_results"] = merge_results
            
            # Trigger centrality calculation if entities were merged
            if total_merged > 0:
                await self._trigger_centrality_calculation(group_id)
            
        logger.info(f"Deduplication complete: {result}")
        return result
        
    async def _trigger_centrality_calculation(self, group_id: str = None):
        """Trigger centrality calculation after deduplication"""
        # Get centrality service URL from environment or use default
        centrality_url = os.getenv('RUST_CENTRALITY_URL', 'http://graphiti-centrality-rs:3003')
        
        try:
            logger.info(f"Triggering centrality calculation for group: {group_id or 'all'}")
            
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{centrality_url}/centrality/all",
                    params={"group_id": group_id} if group_id else None,
                    timeout=30.0
                )
                
                if response.status_code == 200:
                    logger.info("Centrality calculation triggered successfully")
                else:
                    logger.warning(f"Centrality calculation request returned status {response.status_code}")
                    
        except Exception as e:
            logger.error(f"Failed to trigger centrality calculation: {e}")
            # Don't fail the deduplication if centrality fails
            pass


async def main():
    """Main function to run entity deduplication"""
    # Initialize Graphiti with FalkorDB
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from openai import AsyncOpenAI
    import os
    
    # Create FalkorDB driver
    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),  # Use environment variable or localhost
        port=int(os.getenv('FALKORDB_PORT', 6389)),  # Use environment variable or external port
        database="graphiti_migration"  # Correct database name
    )
    
    # Create a custom LLM client with gemma3:12b for deduplication
    custom_llm_config = LLMConfig(
        model="gemma3:12b",  # Using gemma3 for better accuracy
        small_model="gemma3:12b",
        temperature=0.0  # Deterministic for deduplication
    )
    
    # Create Ollama client directly
    ollama_client = AsyncOpenAI(
        base_url=os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1'),
        api_key="ollama"  # Ollama doesn't require a real key
    )
    
    llm_client = OpenAIGenericClient(
        config=custom_llm_config,
        cache=False,
        client=ollama_client
    )
    
    # Initialize Graphiti with the driver
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,  # Use our custom LLM client
        embedder=None,  # Will use default embedder
    )
    
    # Create deduplicator
    deduplicator = EntityDeduplicator(graphiti)
    
    # Run deduplication
    # First do a dry run to see what would be merged
    logger.info("Running dry run to identify duplicates...")
    dry_run_result = await deduplicator.run_deduplication(
        group_id="claude_conversations",  # Focus on Claude conversation entities
        dry_run=True
    )
    
    print(f"\nDry run results: {dry_run_result}")
    
    # Ask for confirmation
    if dry_run_result["entities_merged"] > 0:
        # For now, automatically proceed with the merge
        print(f"\nFound {dry_run_result['entities_merged']} entities to merge. Proceeding with merge...")
        
        if True:  # response.lower() == 'y':
            logger.info("Running actual deduplication...")
            result = await deduplicator.run_deduplication(
                group_id="claude_conversations",
                dry_run=False
                # Process all groups
            )
            print(f"\nDeduplication complete: {result}")
        else:
            print("Deduplication cancelled")
    else:
        print("No duplicates found")


if __name__ == "__main__":
    asyncio.run(main())