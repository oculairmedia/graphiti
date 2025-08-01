#!/usr/bin/env python3
"""
Analysis script to examine duplicate entities in Graphiti FalkorDB.
Based on the deduplication script but only analyzes without modifying.
"""

import asyncio
import logging
from datetime import datetime
import numpy as np
import os
from collections import defaultdict
import re

from graphiti_core import Graphiti
from graphiti_core.nodes import EntityNode
from graphiti_core.helpers import normalize_l2

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class EntityAnalyzer:
    """Analyzes duplicate entities in Graphiti"""
    
    def __init__(self, graphiti: Graphiti):
        self.graphiti = graphiti
        self.driver = graphiti.driver
        self.embedder = graphiti.embedder
        
    async def analyze_all_duplicates(self):
        """Analyze all types of duplicates in the database"""
        
        # Get all entities using a query
        query = """
        MATCH (n:Entity)
        RETURN n
        LIMIT 10000
        """
        
        records, _, _ = await self.driver.execute_query(query)
        
        # Convert to EntityNode objects
        entity_nodes = []
        for record in records:
            # Access the node properties
            node_data = record['n']
            
            # Create a simple object with just the fields we need
            class SimpleEntityNode:
                def __init__(self, uuid, name, created_at=None, name_embedding=None):
                    self.uuid = uuid
                    self.name = name
                    self.created_at = created_at
                    self.name_embedding = name_embedding
            
            # Access properties directly from FalkorDB node
            node = SimpleEntityNode(
                uuid=node_data.properties.get('uuid') if hasattr(node_data, 'properties') else None,
                name=node_data.properties.get('name') if hasattr(node_data, 'properties') else None,
                created_at=node_data.properties.get('created_at') if hasattr(node_data, 'properties') else None,
                name_embedding=node_data.properties.get('name_embedding') if hasattr(node_data, 'properties') else None
            )
            
            # Skip nodes without required fields
            if not node.uuid or not node.name:
                continue
            entity_nodes.append(node)
        
        print(f"\n{'='*80}")
        print(f"DUPLICATE ENTITY ANALYSIS - {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"{'='*80}")
        print(f"\nTotal entities in database: {len(entity_nodes)}")
        
        # Analyze different types of duplicates
        await self._analyze_exact_duplicates(entity_nodes)
        await self._analyze_case_duplicates(entity_nodes)
        await self._analyze_normalized_duplicates(entity_nodes)
        await self._analyze_embedding_duplicates(entity_nodes)
        await self._analyze_potential_duplicates(entity_nodes)
        
    async def _analyze_exact_duplicates(self, entities: list[EntityNode]):
        """Find entities with exactly the same name"""
        print("\n\n=== EXACT NAME DUPLICATES ===")
        
        name_groups = defaultdict(list)
        for entity in entities:
            name_groups[entity.name].append(entity)
        
        exact_dupes = {name: nodes for name, nodes in name_groups.items() if len(nodes) > 1}
        
        if exact_dupes:
            print(f"\nFound {len(exact_dupes)} groups with exact name duplicates:")
            for name, nodes in sorted(exact_dupes.items(), key=lambda x: -len(x[1]))[:10]:
                print(f"\n'{name}' - {len(nodes)} occurrences:")
                for node in nodes[:3]:
                    print(f"  - ID: {node.uuid[:8]}... created: {node.created_at}")
                if len(nodes) > 3:
                    print(f"  ... and {len(nodes) - 3} more")
        else:
            print("\nNo exact name duplicates found")
            
    async def _analyze_case_duplicates(self, entities: list[EntityNode]):
        """Find entities that differ only in case"""
        print("\n\n=== CASE-INSENSITIVE DUPLICATES ===")
        
        lower_groups = defaultdict(list)
        for entity in entities:
            lower_groups[entity.name.lower()].append(entity)
        
        case_dupes = {}
        for lower_name, nodes in lower_groups.items():
            unique_names = {node.name for node in nodes}
            if len(unique_names) > 1:
                case_dupes[lower_name] = nodes
        
        if case_dupes:
            print(f"\nFound {len(case_dupes)} groups with case variations:")
            for lower_name, nodes in sorted(case_dupes.items(), key=lambda x: -len(x[1]))[:10]:
                unique_names = sorted({node.name for node in nodes})
                print(f"\n'{lower_name}' has {len(unique_names)} variations:")
                for name in unique_names[:5]:
                    count = sum(1 for n in nodes if n.name == name)
                    print(f"  - '{name}' ({count} occurrences)")
                if len(unique_names) > 5:
                    print(f"  ... and {len(unique_names) - 5} more variations")
        else:
            print("\nNo case-insensitive duplicates found")
            
    async def _analyze_normalized_duplicates(self, entities: list[EntityNode]):
        """Find entities that are the same after normalization"""
        print("\n\n=== NORMALIZED NAME DUPLICATES ===")
        print("(After removing special chars, normalizing spaces, etc.)")
        
        norm_groups = defaultdict(list)
        for entity in entities:
            normalized = self._normalize_name(entity.name)
            norm_groups[normalized].append(entity)
        
        norm_dupes = {}
        for norm_name, nodes in norm_groups.items():
            unique_names = {node.name for node in nodes}
            if len(unique_names) > 1:
                norm_dupes[norm_name] = nodes
        
        if norm_dupes:
            print(f"\nFound {len(norm_dupes)} groups that normalize to the same name:")
            for norm_name, nodes in sorted(norm_dupes.items(), key=lambda x: -len(x[1]))[:10]:
                unique_names = sorted({node.name for node in nodes})
                print(f"\nNormalizes to '{norm_name}':")
                for name in unique_names[:5]:
                    count = sum(1 for n in nodes if n.name == name)
                    print(f"  - '{name}' ({count} occurrences)")
                if len(unique_names) > 5:
                    print(f"  ... and {len(unique_names) - 5} more variations")
        else:
            print("\nNo normalized duplicates found")
            
    async def _analyze_embedding_duplicates(self, entities: list[EntityNode]):
        """Analyze entities by embedding similarity"""
        print("\n\n=== EMBEDDING SIMILARITY ANALYSIS ===")
        print("(Using cosine similarity of name embeddings)")
        
        # Group by similarity threshold ranges
        similarity_ranges = {
            "0.95-1.00": [],
            "0.90-0.95": [],
            "0.85-0.90": [],
            "0.80-0.85": [],
            "0.75-0.80": []
        }
        
        # Only check entities with embeddings
        entities_with_embeddings = [e for e in entities if e.name_embedding is not None and len(e.name_embedding) > 0]
        print(f"\nEntities with embeddings: {len(entities_with_embeddings)}/{len(entities)}")
        
        if len(entities_with_embeddings) < 2:
            print("Not enough entities with embeddings to analyze")
            return
            
        # Sample analysis (full comparison would be O(n²))
        sample_size = min(100, len(entities_with_embeddings))
        sample_entities = entities_with_embeddings[:sample_size]
        
        for i, entity1 in enumerate(sample_entities):
            for entity2 in sample_entities[i+1:]:
                if entity1.name != entity2.name:  # Skip exact matches
                    try:
                        # Convert to numpy arrays if needed
                        emb1 = np.array(entity1.name_embedding) if isinstance(entity1.name_embedding, list) else entity1.name_embedding
                        emb2 = np.array(entity2.name_embedding) if isinstance(entity2.name_embedding, list) else entity2.name_embedding
                        
                        similarity = np.dot(
                            normalize_l2(emb1),
                            normalize_l2(emb2)
                        )
                    except Exception as e:
                        print(f"Error computing similarity: {e}")
                        continue
                    
                    if similarity >= 0.75:
                        pair = (entity1.name, entity2.name, similarity)
                        if similarity >= 0.95:
                            similarity_ranges["0.95-1.00"].append(pair)
                        elif similarity >= 0.90:
                            similarity_ranges["0.90-0.95"].append(pair)
                        elif similarity >= 0.85:
                            similarity_ranges["0.85-0.90"].append(pair)
                        elif similarity >= 0.80:
                            similarity_ranges["0.80-0.85"].append(pair)
                        else:
                            similarity_ranges["0.75-0.80"].append(pair)
        
        print(f"\nSimilarity distribution (sample of {sample_size} entities):")
        for range_name, pairs in similarity_ranges.items():
            if pairs:
                print(f"\n{range_name}: {len(pairs)} pairs")
                for name1, name2, sim in pairs[:3]:
                    print(f"  - '{name1}' <-> '{name2}' (similarity: {sim:.3f})")
                if len(pairs) > 3:
                    print(f"  ... and {len(pairs) - 3} more pairs")
                    
    async def _analyze_potential_duplicates(self, entities: list[EntityNode]):
        """Analyze why some duplicates might be missed"""
        print("\n\n=== POTENTIAL MISSED DUPLICATES ===")
        
        # Look for common patterns that might be duplicates
        patterns = {
            "file_paths": defaultdict(list),  # Same filename, different paths
            "with_extensions": defaultdict(list),  # Same name with/without extension
            "with_quotes": defaultdict(list),  # Same name with different quotes
            "compound_names": defaultdict(list)  # e.g., "claude" vs "claude code"
        }
        
        for entity in entities:
            name = entity.name
            
            # Extract filename from path
            if '/' in name:
                filename = name.split('/')[-1]
                patterns["file_paths"][filename].append(entity)
            
            # Check for file extensions
            base_name = re.sub(r'\.(ts|tsx|js|jsx|py|sh|log|md|json|yaml|yml)$', '', name, flags=re.IGNORECASE)
            if base_name != name:
                patterns["with_extensions"][base_name.lower()].append(entity)
            
            # Check for quotes
            unquoted = name.strip('"\'`')
            if unquoted != name:
                patterns["with_quotes"][unquoted.lower()].append(entity)
            
            # Check for compound names
            words = name.lower().split()
            if len(words) >= 2:
                first_word = words[0]
                patterns["compound_names"][first_word].append(entity)
        
        # Report findings
        print("\n1. Same filename, different paths:")
        path_dupes = {k: v for k, v in patterns["file_paths"].items() if len(v) > 1}
        if path_dupes:
            for filename, nodes in sorted(path_dupes.items(), key=lambda x: -len(x[1]))[:5]:
                print(f"\n  '{filename}' appears in {len(nodes)} different paths:")
                unique_names = sorted({n.name for n in nodes})
                for name in unique_names[:3]:
                    print(f"    - '{name}'")
                if len(unique_names) > 3:
                    print(f"    ... and {len(unique_names) - 3} more")
        
        print("\n2. Same base name with/without extensions:")
        ext_dupes = {k: v for k, v in patterns["with_extensions"].items() if len(v) > 1}
        if ext_dupes:
            for base, nodes in sorted(ext_dupes.items(), key=lambda x: -len(x[1]))[:5]:
                unique_names = sorted({n.name for n in nodes})
                if len(unique_names) > 1:
                    print(f"\n  Base name '{base}':")
                    for name in unique_names[:3]:
                        print(f"    - '{name}'")
                    if len(unique_names) > 3:
                        print(f"    ... and {len(unique_names) - 3} more")
        
        print("\n3. Compound names (might be related but different entities):")
        compound_dupes = {k: v for k, v in patterns["compound_names"].items() 
                         if len(v) > 1 and len({n.name.lower() for n in v}) > 1}
        if compound_dupes:
            for prefix, nodes in sorted(compound_dupes.items(), key=lambda x: -len(x[1]))[:5]:
                unique_names = sorted({n.name for n in nodes})
                print(f"\n  Starting with '{prefix}':")
                for name in unique_names[:4]:
                    print(f"    - '{name}'")
                if len(unique_names) > 4:
                    print(f"    ... and {len(unique_names) - 4} more")
        
        print("\n\n=== DEDUPLICATION SETTINGS ===")
        print("Current deduplication thresholds:")
        print("  - Embedding similarity: 0.8 (cosine similarity)")
        print("  - Name similarity: 0.95 (for normalized names)")
        print("\nRecommendations:")
        print("  - Consider exact name matching for obvious duplicates")
        print("  - Add case-insensitive pre-filtering")
        print("  - Handle file paths specially (same filename = potential duplicate)")
        print("  - Be careful with compound names (e.g., 'claude' vs 'claude code')")
        
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
        normalized = re.sub(r'[^a-z0-9\s]', '', normalized)
        
        # Normalize multiple spaces to single space
        normalized = ' '.join(normalized.split())
        
        return normalized


async def main():
    """Main function to run the duplicate analysis"""
    try:
        # Initialize Graphiti with FalkorDB
        from graphiti_core.driver.falkordb_driver import FalkorDriver
        from graphiti_core.llm_client.config import LLMConfig
        from graphiti_core.llm_client.openai_generic_client import OpenAIGenericClient
        from openai import AsyncOpenAI
        
        # Create FalkorDB driver
        driver = FalkorDriver(
            host=os.getenv('FALKORDB_HOST', 'localhost'),
            port=int(os.getenv('FALKORDB_PORT', 6389)),
            database="graphiti_migration"
        )
        
        # Create a simple LLM client (we don't need it for analysis)
        custom_llm_config = LLMConfig(
            model="gpt-3.5-turbo",
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
        
        # Initialize Graphiti with the driver
        graphiti = Graphiti(
            graph_driver=driver,
            llm_client=llm_client,
            embedder=None,  # Will use default embedder
        )
        
        # Run analysis
        analyzer = EntityAnalyzer(graphiti)
        await analyzer.analyze_all_duplicates()
        
    except Exception as e:
        logger.error(f"Error during analysis: {e}", exc_info=True)
        raise
    finally:
        if 'graphiti' in locals() and graphiti.driver:
            await graphiti.driver.close()


if __name__ == "__main__":
    asyncio.run(main())