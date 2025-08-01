#!/usr/bin/env python3
"""
Enhanced maintenance script to find and merge duplicate entities in Graphiti.
This script uses a phased approach to catch obvious duplicates before using embeddings.
"""

import asyncio
import logging
from datetime import datetime
from time import time
from typing import List, Dict, Tuple, Set
import numpy as np
import os
import httpx
from collections import defaultdict
import re

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


class EnhancedEntityDeduplicator:
    """Enhanced entity deduplication with phased approach"""
    
    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.driver = graphiti.driver
        self.llm_client = graphiti.llm_client
        self.embedder = graphiti.embedder
        self.all_entities = []
        self.merge_stats = {
            'phase1_exact': 0,
            'phase2_case': 0,
            'phase3_normalized': 0,
            'phase4_embedding': 0,
            'total_merged': 0
        }
        
    async def load_all_entities(self, group_id: str = None) -> List[EntityNode]:
        """Load all entities from the database"""
        logger.info("Loading all entities from database...")
        
        # Build query based on group_id
        if group_id:
            query = """
            MATCH (n:Entity {group_id: $group_id})
            RETURN 
                n.uuid AS uuid,
                n.name AS name,
                n.group_id AS group_id,
                n.name_embedding AS name_embedding,
                n.created_at AS created_at,
                n.summary AS summary
            ORDER BY n.created_at DESC
            """
            # FalkorDB doesn't support parameters in the same way
            query = f"""
            MATCH (n:Entity)
            WHERE n.group_id = '{group_id}'
            RETURN 
                n.uuid AS uuid,
                n.name AS name,
                n.group_id AS group_id,
                n.name_embedding AS name_embedding,
                n.created_at AS created_at,
                n.summary AS summary
            ORDER BY n.created_at DESC
            """
            records, _, _ = await self.driver.execute_query(query)
        else:
            query = """
            MATCH (n:Entity)
            RETURN 
                n.uuid AS uuid,
                n.name AS name,
                n.group_id AS group_id,
                n.name_embedding AS name_embedding,
                n.created_at AS created_at,
                n.summary AS summary
            ORDER BY n.created_at DESC
            """
            records, _, _ = await self.driver.execute_query(query)
        
        # Convert to EntityNode objects
        entities = []
        for record in records:
            try:
                entity = EntityNode(
                    uuid=record['uuid'],
                    name=record['name'],
                    group_id=record['group_id'],
                    name_embedding=record.get('name_embedding'),
                    created_at=record.get('created_at'),
                    summary=record.get('summary')
                )
                entities.append(entity)
            except Exception as e:
                logger.error(f"Error creating EntityNode: {e}")
                continue
                
        logger.info(f"Loaded {len(entities)} entities")
        self.all_entities = entities
        return entities
        
    async def phase1_exact_duplicates(self, dry_run: bool = True) -> Dict[str, List[EntityNode]]:
        """Phase 1: Find and merge exact name matches"""
        logger.info("=" * 60)
        logger.info("PHASE 1: EXACT NAME MATCHING")
        logger.info("=" * 60)
        
        # Group by exact name
        exact_groups = defaultdict(list)
        for entity in self.all_entities:
            exact_groups[entity.name].append(entity)
        
        # Find groups with duplicates
        duplicate_groups = {name: entities for name, entities in exact_groups.items() 
                          if len(entities) > 1}
        
        total_entities = sum(len(entities) for entities in duplicate_groups.values())
        logger.info(f"Found {len(duplicate_groups)} groups with exact duplicates ({total_entities} entities total)")
        
        # Show top duplicates
        sorted_groups = sorted(duplicate_groups.items(), key=lambda x: -len(x[1]))
        for name, entities in sorted_groups[:10]:
            logger.info(f"  '{name}': {len(entities)} copies")
        
        if not dry_run and duplicate_groups:
            merged_count = 0
            for name, entities in duplicate_groups.items():
                if len(entities) > 1:
                    # Keep the oldest entity (or one with most connections)
                    primary = await self._select_primary_entity(entities)
                    duplicates = [e for e in entities if e.uuid != primary.uuid]
                    
                    if duplicates:
                        await self._merge_entities(primary, duplicates)
                        merged_count += len(duplicates)
                        
            self.merge_stats['phase1_exact'] = merged_count
            logger.info(f"Merged {merged_count} exact duplicates")
            
        return duplicate_groups
        
    async def phase2_case_insensitive(self, dry_run: bool = True) -> Dict[str, List[EntityNode]]:
        """Phase 2: Find and merge case-insensitive matches"""
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 2: CASE-INSENSITIVE MATCHING")
        logger.info("=" * 60)
        
        # Group by lowercase name
        case_groups = defaultdict(list)
        for entity in self.all_entities:
            case_groups[entity.name.lower()].append(entity)
        
        # Find groups with case variations
        case_duplicate_groups = {}
        for lower_name, entities in case_groups.items():
            unique_names = set(e.name for e in entities)
            if len(unique_names) > 1:  # Different cases
                case_duplicate_groups[lower_name] = entities
        
        total_entities = sum(len(entities) for entities in case_duplicate_groups.values())
        logger.info(f"Found {len(case_duplicate_groups)} groups with case variations ({total_entities} entities total)")
        
        # Show examples
        for lower_name, entities in list(case_duplicate_groups.items())[:10]:
            unique_names = set(e.name for e in entities)
            logger.info(f"  '{lower_name}': {unique_names}")
        
        if not dry_run and case_duplicate_groups:
            merged_count = 0
            for lower_name, entities in case_duplicate_groups.items():
                # Group by exact name within case group
                exact_subgroups = defaultdict(list)
                for entity in entities:
                    exact_subgroups[entity.name].append(entity)
                
                # Find the most common variant or oldest
                primary = await self._select_primary_entity(entities)
                duplicates = [e for e in entities if e.uuid != primary.uuid]
                
                if duplicates:
                    await self._merge_entities(primary, duplicates)
                    merged_count += len(duplicates)
                    
            self.merge_stats['phase2_case'] = merged_count
            logger.info(f"Merged {merged_count} case variations")
            
        return case_duplicate_groups
        
    async def phase3_normalized_names(self, dry_run: bool = True) -> Dict[str, List[EntityNode]]:
        """Phase 3: Find and merge normalized name matches"""
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 3: NORMALIZED NAME MATCHING")
        logger.info("=" * 60)
        
        # Group by normalized name
        norm_groups = defaultdict(list)
        for entity in self.all_entities:
            normalized = self._normalize_name(entity.name)
            if normalized:  # Skip empty normalizations
                norm_groups[normalized].append(entity)
        
        # Find groups with normalized duplicates
        norm_duplicate_groups = {}
        for norm_name, entities in norm_groups.items():
            unique_names = set(e.name for e in entities)
            if len(unique_names) > 1:  # Different original names
                # Skip if it's a compound name situation
                if not self._is_compound_group(entities):
                    norm_duplicate_groups[norm_name] = entities
        
        total_entities = sum(len(entities) for entities in norm_duplicate_groups.values())
        logger.info(f"Found {len(norm_duplicate_groups)} groups with normalized duplicates ({total_entities} entities total)")
        
        # Show examples
        for norm_name, entities in list(norm_duplicate_groups.items())[:10]:
            unique_names = set(e.name for e in entities)
            logger.info(f"  '{norm_name}' <- {unique_names}")
        
        if not dry_run and norm_duplicate_groups:
            merged_count = 0
            for norm_name, entities in norm_duplicate_groups.items():
                # Use LLM to decide which variant to keep
                primary = await self._select_primary_with_llm(entities)
                duplicates = [e for e in entities if e.uuid != primary.uuid]
                
                if duplicates:
                    await self._merge_entities(primary, duplicates)
                    merged_count += len(duplicates)
                    
            self.merge_stats['phase3_normalized'] = merged_count
            logger.info(f"Merged {merged_count} normalized duplicates")
            
        return norm_duplicate_groups
        
    async def phase4_embedding_similarity(self, dry_run: bool = True, 
                                        similarity_threshold: float = 0.85) -> Dict[str, List[EntityNode]]:
        """Phase 4: Find similar entities using embeddings"""
        logger.info("\n" + "=" * 60)
        logger.info("PHASE 4: EMBEDDING SIMILARITY")
        logger.info("=" * 60)
        
        # Only process entities with embeddings
        entities_with_embeddings = [e for e in self.all_entities 
                                   if e.name_embedding is not None and len(e.name_embedding) > 0]
        
        logger.info(f"Processing {len(entities_with_embeddings)} entities with embeddings")
        
        # Find similar pairs
        similar_groups = []
        processed = set()
        
        for i, entity1 in enumerate(entities_with_embeddings):
            if entity1.uuid in processed:
                continue
                
            group = [entity1]
            processed.add(entity1.uuid)
            
            for entity2 in entities_with_embeddings[i+1:]:
                if entity2.uuid in processed:
                    continue
                    
                # Skip if names are too different in structure
                if self._is_compound_name(entity1.name, entity2.name):
                    continue
                    
                try:
                    # Compute similarity
                    emb1 = np.array(entity1.name_embedding)
                    emb2 = np.array(entity2.name_embedding)
                    similarity = np.dot(normalize_l2(emb1), normalize_l2(emb2))
                    
                    if similarity >= similarity_threshold:
                        group.append(entity2)
                        processed.add(entity2.uuid)
                except Exception as e:
                    logger.error(f"Error computing similarity: {e}")
                    continue
            
            if len(group) > 1:
                similar_groups.append(group)
        
        logger.info(f"Found {len(similar_groups)} groups of similar entities")
        
        # Show examples
        for group in similar_groups[:10]:
            names = [e.name for e in group]
            logger.info(f"  Similar group: {names}")
        
        if not dry_run and similar_groups:
            merged_count = 0
            for group in similar_groups:
                # Use LLM to verify these should be merged
                if await self._verify_merge_with_llm(group):
                    primary = await self._select_primary_with_llm(group)
                    duplicates = [e for e in group if e.uuid != primary.uuid]
                    
                    if duplicates:
                        await self._merge_entities(primary, duplicates)
                        merged_count += len(duplicates)
                        
            self.merge_stats['phase4_embedding'] = merged_count
            logger.info(f"Merged {merged_count} similar entities")
            
        return {f"group_{i}": group for i, group in enumerate(similar_groups)}
        
    async def run_enhanced_deduplication(self, group_id: str = None, dry_run: bool = True):
        """Run all phases of deduplication"""
        start_time = time()
        
        # Load all entities
        await self.load_all_entities(group_id)
        
        if dry_run:
            logger.info("\n" + "=" * 60)
            logger.info("DRY RUN MODE - NO CHANGES WILL BE MADE")
            logger.info("=" * 60)
        
        # Run phases
        phase1_groups = await self.phase1_exact_duplicates(dry_run)
        
        # Remove merged entities from the pool for next phases
        if not dry_run and phase1_groups:
            merged_uuids = set()
            for entities in phase1_groups.values():
                merged_uuids.update(e.uuid for e in entities[1:])  # All but primary
            self.all_entities = [e for e in self.all_entities if e.uuid not in merged_uuids]
        
        phase2_groups = await self.phase2_case_insensitive(dry_run)
        
        if not dry_run and phase2_groups:
            merged_uuids = set()
            for entities in phase2_groups.values():
                merged_uuids.update(e.uuid for e in entities[1:])
            self.all_entities = [e for e in self.all_entities if e.uuid not in merged_uuids]
        
        phase3_groups = await self.phase3_normalized_names(dry_run)
        
        if not dry_run and phase3_groups:
            merged_uuids = set()
            for entities in phase3_groups.values():
                merged_uuids.update(e.uuid for e in entities[1:])
            self.all_entities = [e for e in self.all_entities if e.uuid not in merged_uuids]
        
        phase4_groups = await self.phase4_embedding_similarity(dry_run)
        
        # Calculate totals
        total_groups = (len(phase1_groups) + len(phase2_groups) + 
                       len(phase3_groups) + len(phase4_groups))
        
        if dry_run:
            total_to_merge = (sum(len(g) - 1 for g in phase1_groups.values()) +
                            sum(len(g) - 1 for g in phase2_groups.values()) +
                            sum(len(g) - 1 for g in phase3_groups.values()) +
                            sum(len(g) - 1 for g in phase4_groups.values()))
        else:
            total_to_merge = sum(self.merge_stats.values())
        
        duration = time() - start_time
        
        # Summary
        logger.info("\n" + "=" * 60)
        logger.info("DEDUPLICATION SUMMARY")
        logger.info("=" * 60)
        logger.info(f"Total duplicate groups found: {total_groups}")
        logger.info(f"Total entities to merge: {total_to_merge}")
        if not dry_run:
            logger.info(f"Phase 1 (exact): {self.merge_stats['phase1_exact']} merged")
            logger.info(f"Phase 2 (case): {self.merge_stats['phase2_case']} merged")
            logger.info(f"Phase 3 (normalized): {self.merge_stats['phase3_normalized']} merged")
            logger.info(f"Phase 4 (embedding): {self.merge_stats['phase4_embedding']} merged")
        logger.info(f"Duration: {duration:.2f} seconds")
        
        return {
            'duration': f"{duration:.2f}s",
            'groups_found': total_groups,
            'entities_merged': total_to_merge,
            'dry_run': dry_run,
            'stats': self.merge_stats if not dry_run else None
        }
        
    def _normalize_name(self, name: str) -> str:
        """Enhanced normalization for entity names"""
        # Convert to lowercase and strip
        normalized = name.lower().strip()
        
        # Replace underscores and hyphens with spaces
        normalized = normalized.replace('_', ' ').replace('-', ' ')
        
        # Remove common suffixes/prefixes
        patterns_to_remove = [
            r'\(system\)$', r'\(user\)$', r'\(assistant\)$', r'\(bot\)$',
            r'^\(system\)', r'^\(user\)', r'^\(assistant\)', r'^\(bot\)',
            r'\s*\(reasoning\)\s*', r'\s*\(agent\)\s*'
        ]
        
        for pattern in patterns_to_remove:
            normalized = re.sub(pattern, '', normalized, flags=re.IGNORECASE)
        
        # Remove special characters but keep alphanumeric and spaces
        normalized = re.sub(r'[^a-z0-9\s]', ' ', normalized)
        
        # Normalize multiple spaces to single space
        normalized = ' '.join(normalized.split())
        
        return normalized.strip()
    
    def _is_compound_name(self, name1: str, name2: str) -> bool:
        """Check if one name is a compound version of the other"""
        # Don't merge "BMO" with "BMO Corporate Travel"
        words1 = set(name1.lower().split())
        words2 = set(name2.lower().split())
        
        # If one is subset of other and lengths differ significantly
        if words1.issubset(words2) or words2.issubset(words1):
            if abs(len(words1) - len(words2)) >= 2:
                return True
                
        return False
    
    def _is_compound_group(self, entities: List[EntityNode]) -> bool:
        """Check if a group contains compound name relationships"""
        names = [e.name for e in entities]
        for i, name1 in enumerate(names):
            for name2 in names[i+1:]:
                if self._is_compound_name(name1, name2):
                    return True
        return False
        
    async def _select_primary_entity(self, entities: List[EntityNode]) -> EntityNode:
        """Select the best entity to keep from a group"""
        # Sort by: has embedding, has summary, oldest first
        def score_entity(e):
            score = 0
            if e.name_embedding is not None:
                score += 1000
            if e.summary:
                score += 100
            # Prefer older entities (lower timestamp = higher score)
            if e.created_at:
                score -= int(e.created_at.timestamp())
            return score
        
        return max(entities, key=score_entity)
        
    async def _select_primary_with_llm(self, entities: List[EntityNode]) -> EntityNode:
        """Use LLM to select the best variant"""
        # For now, use the same logic as _select_primary_entity
        # Could be enhanced to ask LLM which name variant is best
        return await self._select_primary_entity(entities)
        
    async def _verify_merge_with_llm(self, entities: List[EntityNode]) -> bool:
        """Verify with LLM that entities should be merged"""
        # For now, return True
        # Could be enhanced to ask LLM if these are truly the same entity
        return True
        
    async def _merge_entities(self, primary: EntityNode, duplicates: List[EntityNode]):
        """Merge duplicate entities into the primary one"""
        duplicate_uuids = [d.uuid for d in duplicates]
        
        if not duplicate_uuids:
            return
            
        # Update edges where duplicate is source - using MERGE and RELATES_TO
        update_source_query = f"""
        UNWIND ['{duplicate_uuids[0]}'] AS dup_uuid
        MATCH (n:Entity {{uuid: dup_uuid}})-[r]->(m)
        WHERE n.uuid <> '{primary.uuid}'
        WITH r, m
        MATCH (primary:Entity {{uuid: '{primary.uuid}'}})
        MERGE (primary)-[new_r:RELATES_TO]->(m)
        SET new_r = properties(r)
        DELETE r
        """
        
        # Update edges where duplicate is target
        update_target_query = f"""
        UNWIND ['{duplicate_uuids[0]}'] AS dup_uuid
        MATCH (m)-[r]->(n:Entity {{uuid: dup_uuid}})
        WHERE n.uuid <> '{primary.uuid}'
        WITH r, m
        MATCH (primary:Entity {{uuid: '{primary.uuid}'}})
        MERGE (m)-[new_r:RELATES_TO]->(primary)
        SET new_r = properties(r)
        DELETE r
        """
        
        # Process each duplicate
        for dup_uuid in duplicate_uuids:
            try:
                # Update source edges
                source_query = update_source_query.replace(duplicate_uuids[0], dup_uuid)
                await self.driver.execute_query(source_query)
                
                # Update target edges
                target_query = update_target_query.replace(duplicate_uuids[0], dup_uuid)
                await self.driver.execute_query(target_query)
                
            except Exception as e:
                logger.warning(f"Error updating edges for {dup_uuid}: {e}")
        
        # Delete duplicate nodes using DETACH DELETE
        delete_query = f"""
        UNWIND {duplicate_uuids} AS dup_uuid
        MATCH (n:Entity {{uuid: dup_uuid}})
        WHERE n.uuid <> '{primary.uuid}'
        DETACH DELETE n
        RETURN count(n) as deleted_count
        """
        
        try:
            records, _, _ = await self.driver.execute_query(delete_query)
            deleted_count = records[0].get("deleted_count", 0) if records else 0
            logger.info(f"Merged {deleted_count} entities into '{primary.name}'")
        except Exception as e:
            logger.error(f"Error deleting duplicate nodes: {e}")


async def main():
    """Main function to run enhanced entity deduplication"""
    # Initialize Graphiti with FalkorDB
    from graphiti_core.driver.falkordb_driver import FalkorDriver
    from graphiti_core.llm_client.config import LLMConfig
    from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
    from openai import AsyncOpenAI
    import os
    
    # Create FalkorDB driver
    driver = FalkorDriver(
        host=os.getenv('FALKORDB_HOST', 'localhost'),
        port=int(os.getenv('FALKORDB_PORT', 6389)),
        database="graphiti_migration"
    )
    
    # Create LLM client
    custom_llm_config = LLMConfig(
        model="gemma3:12b",
        temperature=0.0
    )
    
    ollama_client = AsyncOpenAI(
        base_url=os.getenv('OLLAMA_BASE_URL', 'http://100.81.139.20:11434/v1'),
        api_key="ollama"
    )
    
    llm_client = OpenAIGenericClient(
        config=custom_llm_config,
        cache=False,
        client=ollama_client
    )
    
    # Initialize Graphiti
    graphiti = Graphiti(
        graph_driver=driver,
        llm_client=llm_client,
        embedder=None,  # Will use default embedder
    )
    
    # Create enhanced deduplicator
    deduplicator = EnhancedEntityDeduplicator(graphiti)
    
    # Run dry run first
    logger.info("Running dry run to preview changes...")
    dry_run_result = await deduplicator.run_enhanced_deduplication(
        group_id="claude_conversations",
        dry_run=True
    )
    
    print(f"\nDry run complete: {dry_run_result}")
    
    # Ask for confirmation
    if dry_run_result["entities_merged"] > 0:
        response = input(f"\nProceed with merging {dry_run_result['entities_merged']} entities? (y/n): ")
        
        if response.lower() == 'y':
            logger.info("Running actual deduplication...")
            result = await deduplicator.run_enhanced_deduplication(
                group_id="claude_conversations",
                dry_run=False
            )
            print(f"\nDeduplication complete: {result}")
            
            # Trigger centrality calculation
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "http://graphiti-centrality-rs:3003/centrality/all",
                        params={"group_id": "claude_conversations"},
                        timeout=30.0
                    )
                    if response.status_code == 200:
                        logger.info("Centrality calculation triggered successfully")
            except Exception as e:
                logger.error(f"Failed to trigger centrality calculation: {e}")
        else:
            print("Deduplication cancelled")
    else:
        print("No duplicates found")


if __name__ == "__main__":
    asyncio.run(main())