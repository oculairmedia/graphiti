#!/usr/bin/env python3
"""
Advanced Graphiti Integration Hook for Claude Code

This hook provides deep integration with Graphiti's Python API,
enabling semantic search, entity extraction, and knowledge graph traversal.
"""

import json
import sys
import os
import re
import asyncio
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging

# Add Graphiti to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

try:
    from graphiti_core import Graphiti
    from graphiti_core.nodes import EntityNode, EpisodeNode
    from graphiti_core.edges import EntityEdge, EpisodeEntityEdge
    from graphiti_core.search import SearchConfig, SearchMethod
    GRAPHITI_AVAILABLE = True
except ImportError:
    GRAPHITI_AVAILABLE = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('/tmp/graphiti-hook.log'),
        logging.StreamHandler(sys.stderr) if os.getenv('DEBUG') else logging.NullHandler()
    ]
)
logger = logging.getLogger(__name__)


class GraphitiHook:
    """Advanced Graphiti integration for Claude Code"""
    
    def __init__(self):
        self.graphiti = None
        self.search_config = SearchConfig(
            search_methods=[SearchMethod.HYBRID],
            similarity_threshold=0.7,
            limit=10,
            include_metadata=True
        )
        
    async def initialize(self):
        """Initialize Graphiti connection"""
        if not GRAPHITI_AVAILABLE:
            logger.warning("Graphiti library not available")
            return False
            
        try:
            # Initialize Graphiti with environment config
            self.graphiti = Graphiti(
                neo4j_uri=os.getenv("NEO4J_URI", "bolt://localhost:7687"),
                neo4j_user=os.getenv("NEO4J_USER", "neo4j"),
                neo4j_password=os.getenv("NEO4J_PASSWORD", "password")
            )
            await self.graphiti.initialize()
            logger.info("Graphiti initialized successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to initialize Graphiti: {e}")
            return False
    
    async def close(self):
        """Close Graphiti connection"""
        if self.graphiti:
            await self.graphiti.close()
    
    def analyze_prompt(self, prompt: str) -> Tuple[bool, str, List[str]]:
        """
        Analyze prompt to determine if Graphiti search is needed
        Returns: (should_search, search_type, entities)
        """
        prompt_lower = prompt.lower()
        
        # Check for explicit knowledge requests
        knowledge_patterns = [
            (r"(?i)what (?:do you |did you |do we )?(?:know|remember) about (.*)", "entity"),
            (r"(?i)(?:tell me|explain|describe) (?:about |the )?(.*?)(?:\?|$)", "entity"),
            (r"(?i)(?:search|find|look for) (.*) in (?:the )?(?:knowledge|graph|memory)", "search"),
            (r"(?i)(?:recall|remember) (?:when|what|how) (.*)", "episode"),
            (r"(?i)(?:history|context|background) (?:of|about|for) (.*)", "history"),
            (r"(?i)(?:related to|connected to|associated with) (.*)", "relationship"),
        ]
        
        for pattern, search_type in knowledge_patterns:
            match = re.search(pattern, prompt)
            if match:
                query = match.group(1).strip()
                # Extract potential entities (capitalized words)
                entities = [w for w in query.split() if w and w[0].isupper()]
                return True, search_type, entities
        
        # Check for implicit knowledge needs
        if any(kw in prompt_lower for kw in ["previous", "earlier", "before", "last time", "context"]):
            return True, "temporal", []
        
        return False, "", []
    
    async def search_entities(self, query: str) -> List[EntityNode]:
        """Search for entities in the knowledge graph"""
        if not self.graphiti:
            return []
            
        try:
            results = await self.graphiti.search(
                query=query,
                search_type="entity",
                config=self.search_config
            )
            return results.get("entities", [])
        except Exception as e:
            logger.error(f"Entity search failed: {e}")
            return []
    
    async def search_episodes(self, query: str, time_range: Optional[int] = None) -> List[EpisodeNode]:
        """Search for episodes, optionally within a time range"""
        if not self.graphiti:
            return []
            
        try:
            config = self.search_config.copy()
            if time_range:
                # Add temporal filter for recent episodes
                config.time_filter = {
                    "start": datetime.now() - timedelta(days=time_range),
                    "end": datetime.now()
                }
            
            results = await self.graphiti.search(
                query=query,
                search_type="episode",
                config=config
            )
            return results.get("episodes", [])
        except Exception as e:
            logger.error(f"Episode search failed: {e}")
            return []
    
    async def get_entity_relationships(self, entity_id: str) -> List[EntityEdge]:
        """Get all relationships for an entity"""
        if not self.graphiti:
            return []
            
        try:
            return await self.graphiti.get_entity_edges(entity_id)
        except Exception as e:
            logger.error(f"Failed to get relationships: {e}")
            return []
    
    async def get_entity_context(self, entity_name: str) -> Dict[str, Any]:
        """Get comprehensive context for an entity"""
        entities = await self.search_entities(entity_name)
        if not entities:
            return {}
        
        entity = entities[0]
        context = {
            "entity": entity.to_dict(),
            "relationships": [],
            "episodes": []
        }
        
        # Get relationships
        edges = await self.get_entity_relationships(entity.id)
        context["relationships"] = [edge.to_dict() for edge in edges[:5]]
        
        # Get related episodes
        episodes = await self.search_episodes(entity_name, time_range=30)
        context["episodes"] = [ep.to_dict() for ep in episodes[:3]]
        
        return context
    
    def format_context(self, search_type: str, results: Any) -> str:
        """Format search results as context for Claude"""
        if not results:
            return ""
        
        lines = ["<!-- Graphiti Knowledge Graph Context -->"]
        lines.append(f"<!-- Search Type: {search_type} -->")
        lines.append("<graphiti-context>")
        
        if search_type == "entity" and isinstance(results, list):
            lines.append("\n## Entities Found:")
            for entity in results[:5]:
                lines.append(f"\n### {entity.name}")
                lines.append(f"- Type: {entity.entity_type}")
                lines.append(f"- Created: {entity.created_at}")
                if hasattr(entity, 'summary') and entity.summary:
                    lines.append(f"- Summary: {entity.summary[:200]}")
                if hasattr(entity, 'properties') and entity.properties:
                    lines.append(f"- Properties: {json.dumps(entity.properties, indent=2)}")
        
        elif search_type == "episode" and isinstance(results, list):
            lines.append("\n## Episodes:")
            for episode in results[:3]:
                lines.append(f"\n### {episode.name}")
                lines.append(f"- Created: {episode.created_at}")
                if hasattr(episode, 'content') and episode.content:
                    lines.append(f"- Content: {episode.content[:300]}...")
                if hasattr(episode, 'summary') and episode.summary:
                    lines.append(f"- Summary: {episode.summary}")
        
        elif search_type == "context" and isinstance(results, dict):
            if "entity" in results:
                entity = results["entity"]
                lines.append(f"\n## Entity: {entity.get('name', 'Unknown')}")
                lines.append(f"- Type: {entity.get('entity_type', 'Unknown')}")
                if entity.get('summary'):
                    lines.append(f"- Summary: {entity['summary']}")
            
            if "relationships" in results and results["relationships"]:
                lines.append("\n## Relationships:")
                for rel in results["relationships"]:
                    lines.append(f"- {rel.get('relationship_type', '?')}: {rel.get('target_name', '?')}")
            
            if "episodes" in results and results["episodes"]:
                lines.append("\n## Related Episodes:")
                for ep in results["episodes"]:
                    lines.append(f"- {ep.get('name', 'Unknown')}: {ep.get('summary', '')[:100]}")
        
        lines.append("\n</graphiti-context>")
        return "\n".join(lines)
    
    async def process_prompt(self, prompt: str) -> str:
        """Process a user prompt and return relevant context"""
        should_search, search_type, entities = self.analyze_prompt(prompt)
        
        if not should_search:
            return ""
        
        # Initialize if needed
        if not self.graphiti:
            if not await self.initialize():
                return ""
        
        context = ""
        
        try:
            if search_type == "entity" and entities:
                # Search for specific entities
                all_results = []
                for entity_name in entities[:3]:  # Limit to 3 entities
                    results = await self.search_entities(entity_name)
                    all_results.extend(results)
                context = self.format_context("entity", all_results)
            
            elif search_type == "episode":
                # Search for episodes
                query = " ".join(entities) if entities else prompt
                results = await self.search_episodes(query, time_range=30)
                context = self.format_context("episode", results)
            
            elif search_type == "context" and entities:
                # Get comprehensive context for first entity
                entity_context = await self.get_entity_context(entities[0])
                context = self.format_context("context", entity_context)
            
            elif search_type == "temporal":
                # Get recent episodes
                results = await self.search_episodes("", time_range=7)
                context = self.format_context("episode", results)
            
            else:
                # General search
                query = " ".join(entities) if entities else prompt[:100]
                entity_results = await self.search_entities(query)
                episode_results = await self.search_episodes(query, time_range=30)
                
                combined = {
                    "entities": entity_results,
                    "episodes": episode_results
                }
                context = self.format_context("combined", combined)
                
        except Exception as e:
            logger.error(f"Error processing prompt: {e}")
            context = f"<!-- Graphiti search error: {e} -->"
        
        return context


async def main():
    """Main entry point"""
    try:
        # Read input
        input_data = json.load(sys.stdin)
        hook_event = input_data.get("hook_event_name", "")
        
        # Only process UserPromptSubmit and SessionStart
        if hook_event not in ["UserPromptSubmit", "SessionStart"]:
            sys.exit(0)
        
        hook = GraphitiHook()
        
        if hook_event == "UserPromptSubmit":
            prompt = input_data.get("prompt", "")
            context = await hook.process_prompt(prompt)
            
            if context:
                output = {
                    "hookSpecificOutput": {
                        "hookEventName": "UserPromptSubmit",
                        "additionalContext": context
                    }
                }
                print(json.dumps(output))
        
        elif hook_event == "SessionStart" and input_data.get("source") == "resume":
            # Load recent context on resume
            context = await hook.process_prompt("recent updates and context")
            
            if context:
                output = {
                    "hookSpecificOutput": {
                        "hookEventName": "SessionStart",
                        "additionalContext": context
                    }
                }
                print(json.dumps(output))
        
        await hook.close()
        sys.exit(0)
        
    except json.JSONDecodeError as e:
        logger.error(f"Invalid JSON input: {e}")
        print(f"Error: Invalid JSON input: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        logger.error(f"Hook error: {e}")
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())