#!/usr/bin/env python3

"""
Test Chutes AI batch processing with robust Pydantic-based parsing.

This test implements best practices from Pydantic and Pydantic AI documentation
for parsing structured output from LLMs, including:
- Multiple parsing strategies with fallback chain
- Partial JSON parsing for incomplete responses
- Proper error handling and recovery
- Type-safe validation with Pydantic models
"""

import asyncio
import json
import logging
import os
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

# Add parent directory to path
sys.path.append(str(Path(__file__).parent.parent.parent))

from pydantic import BaseModel, Field, ValidationError, field_validator
from pydantic_core import from_json

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ============================================================================
# Pydantic Models for Structured Output
# ============================================================================

class ExtractedEntity(BaseModel):
    """Single extracted entity with validation."""
    name: str = Field(..., min_length=1, description="Entity name")
    type: str = Field(..., description="Entity type (person, organization, etc.)")
    episode_index: int = Field(..., ge=0, description="Index of episode this entity came from")
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ensure name is not just whitespace."""
        if not v.strip():
            raise ValueError("Entity name cannot be empty or whitespace")
        return v.strip()


class ExtractedRelationship(BaseModel):
    """Single extracted relationship with validation."""
    source: str = Field(..., min_length=1, description="Source entity name")
    target: str = Field(..., min_length=1, description="Target entity name")
    relation_type: str = Field(..., description="Type of relationship")
    episode_index: int = Field(..., ge=0, description="Index of episode this relationship came from")
    
    @field_validator('source', 'target')
    @classmethod
    def validate_entity_names(cls, v: str) -> str:
        """Ensure entity names are not just whitespace."""
        if not v.strip():
            raise ValueError("Entity name cannot be empty or whitespace")
        return v.strip()


class EpisodeExtraction(BaseModel):
    """Extraction results for a single episode."""
    episode_index: int = Field(..., ge=0)
    entities: List[ExtractedEntity] = Field(default_factory=list)
    relationships: List[ExtractedRelationship] = Field(default_factory=list)
    
    def is_empty(self) -> bool:
        """Check if this episode has no extractions."""
        return len(self.entities) == 0 and len(self.relationships) == 0


class BatchExtractionResult(BaseModel):
    """Complete batch extraction results."""
    episodes: List[EpisodeExtraction] = Field(default_factory=list)
    total_entities: int = Field(default=0)
    total_relationships: int = Field(default=0)
    parsing_metadata: Dict[str, Any] = Field(default_factory=dict)
    
    def calculate_totals(self):
        """Calculate total counts from episodes."""
        self.total_entities = sum(len(ep.entities) for ep in self.episodes)
        self.total_relationships = sum(len(ep.relationships) for ep in self.episodes)


# ============================================================================
# Robust JSON Parser with Multiple Strategies
# ============================================================================

class RobustJSONParser:
    """
    Robust JSON parser implementing best practices from Pydantic documentation.
    Uses multiple strategies with fallback chain for parsing LLM outputs.
    """
    
    def __init__(self):
        self.strategies = [
            self._parse_clean_json,
            self._parse_markdown_json,
            self._parse_with_cleanup,
            self._parse_partial_json,
            self._parse_with_regex_extraction,
            self._parse_individual_episodes,
            self._parse_with_recovery
        ]
        
    def parse(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """
        Parse content using multiple strategies until one succeeds.
        
        Args:
            content: Raw LLM output to parse
            expected_episodes: Number of episodes we expect to find
            
        Returns:
            BatchExtractionResult with parsed data
        """
        errors = []
        
        for strategy in self.strategies:
            try:
                logger.debug(f"Trying parsing strategy: {strategy.__name__}")
                result = strategy(content, expected_episodes)
                
                # Validate we got reasonable results
                if self._validate_result(result, expected_episodes):
                    logger.info(f"Successfully parsed with strategy: {strategy.__name__}")
                    result.parsing_metadata['strategy'] = strategy.__name__
                    return result
                else:
                    logger.debug(f"Strategy {strategy.__name__} returned invalid results")
                    
            except Exception as e:
                logger.debug(f"Strategy {strategy.__name__} failed: {e}")
                errors.append((strategy.__name__, str(e)))
        
        # If all strategies fail, return empty result with error info
        logger.warning(f"All parsing strategies failed. Errors: {errors}")
        return BatchExtractionResult(
            episodes=[EpisodeExtraction(episode_index=i) for i in range(expected_episodes)],
            parsing_metadata={'errors': errors, 'strategy': 'fallback_empty'}
        )
    
    def _validate_result(self, result: BatchExtractionResult, expected_episodes: int) -> bool:
        """Validate that parsing result is reasonable."""
        # Check we have the right number of episodes
        if len(result.episodes) != expected_episodes:
            return False
            
        # Check at least some episodes have content
        non_empty = sum(1 for ep in result.episodes if not ep.is_empty())
        if non_empty == 0:
            return False
            
        # Check episode indices are correct
        for i, ep in enumerate(result.episodes):
            if ep.episode_index != i:
                return False
                
        return True
    
    def _parse_clean_json(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """Strategy 1: Parse clean JSON directly."""
        data = json.loads(content)
        return self._convert_to_result(data, expected_episodes)
    
    def _parse_markdown_json(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """Strategy 2: Extract JSON from markdown code blocks."""
        # Look for ```json ... ``` blocks
        pattern = r'```json\s*(.*?)\s*```'
        matches = re.findall(pattern, content, re.DOTALL)
        
        if matches:
            # Try each JSON block found
            for json_str in matches:
                try:
                    data = json.loads(json_str)
                    return self._convert_to_result(data, expected_episodes)
                except:
                    continue
                    
        raise ValueError("No valid JSON found in markdown blocks")
    
    def _parse_with_cleanup(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """Strategy 3: Clean up common JSON formatting issues."""
        # Remove common prefixes/suffixes
        cleaned = content.strip()
        
        # Remove "Here is the extraction:" type prefixes
        prefixes = [
            "Here is the extraction:",
            "Here are the results:",
            "Extraction results:",
            "JSON output:",
            "```", "json", "JSON:"
        ]
        for prefix in prefixes:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):].strip()
        
        # Remove trailing markdown markers
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3].strip()
            
        # Fix common JSON issues
        # Replace single quotes with double quotes
        cleaned = re.sub(r"'([^']*)'", r'"\1"', cleaned)
        
        # Fix trailing commas
        cleaned = re.sub(r',\s*}', '}', cleaned)
        cleaned = re.sub(r',\s*]', ']', cleaned)
        
        data = json.loads(cleaned)
        return self._convert_to_result(data, expected_episodes)
    
    def _parse_partial_json(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """Strategy 4: Use Pydantic's partial JSON parsing."""
        try:
            # Use pydantic_core's from_json with allow_partial
            data = from_json(content, allow_partial=True)
            return self._convert_to_result(data, expected_episodes)
        except Exception as e:
            # Try with trailing-strings mode for incomplete strings
            data = from_json(content, allow_partial='trailing-strings')
            return self._convert_to_result(data, expected_episodes)
    
    def _parse_with_regex_extraction(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """Strategy 5: Extract structured data using regex patterns."""
        result = BatchExtractionResult()
        
        # Pattern for episode blocks
        episode_pattern = r'Episode\s+(\d+)[:\s]*\n(.*?)(?=Episode\s+\d+|$)'
        episode_matches = re.findall(episode_pattern, content, re.DOTALL | re.IGNORECASE)
        
        for episode_idx, episode_content in episode_matches:
            idx = int(episode_idx)
            if idx >= expected_episodes:
                continue
                
            episode = EpisodeExtraction(episode_index=idx)
            
            # Extract entities
            entity_pattern = r'(?:Entity|Person|Organization|Location|Technology):\s*([^,\n]+)(?:\s*\(([^)]+)\))?'
            for match in re.finditer(entity_pattern, episode_content, re.IGNORECASE):
                name = match.group(1).strip()
                entity_type = match.group(2).strip() if match.group(2) else "unknown"
                if name:
                    episode.entities.append(ExtractedEntity(
                        name=name,
                        type=entity_type,
                        episode_index=idx
                    ))
            
            # Extract relationships
            rel_pattern = r'([^,\n]+)\s+(?:->|→|relates to|connected to)\s+([^,\n]+)(?:\s*\(([^)]+)\))?'
            for match in re.finditer(rel_pattern, episode_content, re.IGNORECASE):
                source = match.group(1).strip()
                target = match.group(2).strip()
                rel_type = match.group(3).strip() if match.group(3) else "RELATED_TO"
                if source and target:
                    episode.relationships.append(ExtractedRelationship(
                        source=source,
                        target=target,
                        relation_type=rel_type,
                        episode_index=idx
                    ))
            
            result.episodes.append(episode)
        
        # Fill in missing episodes
        existing_indices = {ep.episode_index for ep in result.episodes}
        for i in range(expected_episodes):
            if i not in existing_indices:
                result.episodes.append(EpisodeExtraction(episode_index=i))
        
        # Sort by index
        result.episodes.sort(key=lambda x: x.episode_index)
        result.calculate_totals()
        
        return result
    
    def _parse_individual_episodes(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """Strategy 6: Try to parse each episode individually."""
        result = BatchExtractionResult()
        
        # Try to find JSON arrays or objects for each episode
        json_pattern = r'(\{[^{}]*\}|\[[^\[\]]*\])'
        json_matches = re.findall(json_pattern, content)
        
        episode_idx = 0
        for json_str in json_matches:
            if episode_idx >= expected_episodes:
                break
                
            try:
                data = json.loads(json_str)
                episode = EpisodeExtraction(episode_index=episode_idx)
                
                # Try to extract entities and relationships from the data
                if isinstance(data, dict):
                    # Look for entities key
                    for key in ['entities', 'entity', 'extracted_entities']:
                        if key in data:
                            entities = data[key]
                            if isinstance(entities, list):
                                for e in entities:
                                    if isinstance(e, dict) and 'name' in e:
                                        episode.entities.append(ExtractedEntity(
                                            name=e['name'],
                                            type=e.get('type', 'unknown'),
                                            episode_index=episode_idx
                                        ))
                    
                    # Look for relationships key
                    for key in ['relationships', 'relations', 'edges']:
                        if key in data:
                            relationships = data[key]
                            if isinstance(relationships, list):
                                for r in relationships:
                                    if isinstance(r, dict) and 'source' in r and 'target' in r:
                                        episode.relationships.append(ExtractedRelationship(
                                            source=r['source'],
                                            target=r['target'],
                                            relation_type=r.get('type', r.get('relation_type', 'RELATED_TO')),
                                            episode_index=episode_idx
                                        ))
                
                result.episodes.append(episode)
                episode_idx += 1
                
            except:
                continue
        
        # Fill in missing episodes
        while len(result.episodes) < expected_episodes:
            result.episodes.append(EpisodeExtraction(episode_index=len(result.episodes)))
        
        result.calculate_totals()
        return result
    
    def _parse_with_recovery(self, content: str, expected_episodes: int) -> BatchExtractionResult:
        """Strategy 7: Best-effort recovery parsing."""
        result = BatchExtractionResult()
        
        # Create empty episodes
        for i in range(expected_episodes):
            result.episodes.append(EpisodeExtraction(episode_index=i))
        
        # Try to extract any entities we can find
        entity_patterns = [
            r'"name":\s*"([^"]+)"',
            r'(?:Entity|Person|Organization):\s*([^,\n]+)',
            r'\b([A-Z][a-z]+ [A-Z][a-z]+)\b',  # Proper names
        ]
        
        entities_found = []
        for pattern in entity_patterns:
            for match in re.finditer(pattern, content):
                name = match.group(1).strip()
                if name and len(name) > 2:
                    entities_found.append(name)
        
        # Distribute entities across episodes
        if entities_found:
            entities_per_episode = max(1, len(entities_found) // expected_episodes)
            for i, entity_name in enumerate(entities_found):
                episode_idx = min(i // entities_per_episode, expected_episodes - 1)
                result.episodes[episode_idx].entities.append(ExtractedEntity(
                    name=entity_name,
                    type="unknown",
                    episode_index=episode_idx
                ))
        
        result.calculate_totals()
        return result
    
    def _convert_to_result(self, data: Any, expected_episodes: int) -> BatchExtractionResult:
        """Convert parsed data to BatchExtractionResult."""
        result = BatchExtractionResult()
        
        # Handle different data structures
        if isinstance(data, dict):
            # Look for episodes key
            if 'episodes' in data:
                episodes_data = data['episodes']
            elif 'results' in data:
                episodes_data = data['results']
            elif 'extractions' in data:
                episodes_data = data['extractions']
            else:
                # Treat the whole dict as a single episode
                episodes_data = [data]
        elif isinstance(data, list):
            episodes_data = data
        else:
            raise ValueError(f"Unexpected data type: {type(data)}")
        
        # Parse each episode
        for i, episode_data in enumerate(episodes_data):
            if i >= expected_episodes:
                break
                
            episode = EpisodeExtraction(episode_index=i)
            
            if isinstance(episode_data, dict):
                # Extract entities
                entities = episode_data.get('entities', episode_data.get('extracted_entities', []))
                if isinstance(entities, list):
                    for e in entities:
                        if isinstance(e, dict) and 'name' in e:
                            try:
                                episode.entities.append(ExtractedEntity(
                                    name=e['name'],
                                    type=e.get('type', e.get('entity_type', 'unknown')),
                                    episode_index=i
                                ))
                            except ValidationError:
                                continue
                
                # Extract relationships
                relationships = episode_data.get('relationships', episode_data.get('relations', []))
                if isinstance(relationships, list):
                    for r in relationships:
                        if isinstance(r, dict) and 'source' in r and 'target' in r:
                            try:
                                episode.relationships.append(ExtractedRelationship(
                                    source=r['source'],
                                    target=r['target'],
                                    relation_type=r.get('relation_type', r.get('type', 'RELATED_TO')),
                                    episode_index=i
                                ))
                            except ValidationError:
                                continue
            
            result.episodes.append(episode)
        
        # Fill in any missing episodes
        existing_indices = {ep.episode_index for ep in result.episodes}
        for i in range(expected_episodes):
            if i not in existing_indices:
                result.episodes.append(EpisodeExtraction(episode_index=i))
        
        # Sort by index and calculate totals
        result.episodes.sort(key=lambda x: x.episode_index)
        result.calculate_totals()
        
        return result


# ============================================================================
# Chutes AI Client with Robust Parsing
# ============================================================================

class ChutesClientRobust:
    """Chutes AI client with robust parsing capabilities."""
    
    def __init__(self, api_key: str, model: str = "zai-org/GLM-4.5-FP8"):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://llm.chutes.ai/v1"
        self.parser = RobustJSONParser()
        
    async def extract_batch(self, episodes: List[str]) -> BatchExtractionResult:
        """
        Extract entities and relationships from a batch of episodes.
        
        Args:
            episodes: List of episode texts to process
            
        Returns:
            BatchExtractionResult with all extracted data
        """
        import httpx
        
        prompt = self._create_batch_prompt(episodes)
        
        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                response = await client.post(
                    f"{self.base_url}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": self._get_system_prompt(len(episodes))},
                            {"role": "user", "content": prompt}
                        ],
                        "temperature": 0.3,
                        "max_tokens": 4096,
                        "response_format": {"type": "json_object"}  # Request JSON format
                    }
                )
                response.raise_for_status()
                
                data = response.json()
                
                # Extract content from response
                content = self._extract_content(data)
                
                # Parse with robust parser
                result = self.parser.parse(content, len(episodes))
                
                # Add API metadata
                result.parsing_metadata['api_call'] = 'success'
                result.parsing_metadata['model'] = self.model
                
                return result
                
            except Exception as e:
                logger.error(f"API call failed: {e}")
                # Return empty result on API failure
                return BatchExtractionResult(
                    episodes=[EpisodeExtraction(episode_index=i) for i in range(len(episodes))],
                    parsing_metadata={'api_call': 'failed', 'error': str(e)}
                )
    
    def _get_system_prompt(self, batch_size: int) -> str:
        """Get system prompt optimized for JSON output."""
        return f"""You are an expert entity and relationship extractor.
You will process {batch_size} episodes and extract ALL entities and relationships.

CRITICAL: You MUST return valid JSON in this exact format:
{{
    "episodes": [
        {{
            "entities": [
                {{"name": "Entity Name", "type": "entity_type"}}
            ],
            "relationships": [
                {{"source": "Entity1", "target": "Entity2", "relation_type": "RELATIONSHIP_TYPE"}}
            ]
        }}
    ]
}}

Rules:
1. Return ONLY valid JSON, no other text
2. Process ALL {batch_size} episodes
3. Extract ALL entities and relationships from each episode
4. Use SCREAMING_SNAKE_CASE for relationship types
5. Entity types: person, organization, location, technology, event, concept"""
    
    def _create_batch_prompt(self, episodes: List[str]) -> str:
        """Create prompt for batch extraction."""
        prompt = f"Extract entities and relationships from these {len(episodes)} episodes:\n\n"
        
        for i, episode in enumerate(episodes):
            prompt += f"Episode {i}:\n{episode}\n\n"
        
        prompt += "\nReturn the extraction results as valid JSON."
        return prompt
    
    def _extract_content(self, response_data: dict) -> str:
        """Extract content from API response."""
        try:
            message = response_data['choices'][0]['message']
            
            # Try content field first
            content = message.get('content', '')
            
            # Check reasoning_content for GLM-4.5-FP8
            if not content.strip() and 'reasoning_content' in message:
                content = message['reasoning_content']
                logger.debug("Using reasoning_content field from GLM response")
            
            return content
            
        except (KeyError, IndexError) as e:
            logger.error(f"Failed to extract content from response: {e}")
            return "{}"


# ============================================================================
# Test Runner
# ============================================================================

async def test_robust_batch_parsing():
    """Test the robust batch parsing system."""
    
    # Test episodes with varying complexity
    test_episodes = [
        "Alice from TechCorp met with Bob from DataSystems to discuss the new AI platform. They plan to integrate machine learning capabilities by Q2.",
        "The quantum computing research at MIT is led by Dr. Sarah Chen. Her team collaborates with IBM Research on developing new quantum algorithms.",
        "Microsoft announced Azure OpenAI Service expansion. The service now supports GPT-4 and DALL-E 3 models for enterprise customers.",
        "Emma Thompson, CEO of StartupXYZ, secured $10M funding from Venture Partners. The company focuses on blockchain solutions for supply chain.",
        "The conference in San Francisco featured talks by Google researchers on transformer architectures and Meta's work on computer vision."
    ]
    
    # Get API key
    api_key = os.getenv('CHUTES_API_KEY')
    if not api_key:
        logger.error("CHUTES_API_KEY not set")
        return
    
    client = ChutesClientRobust(api_key)
    
    logger.info("=" * 80)
    logger.info("Testing Robust Batch Parsing with Chutes AI")
    logger.info("=" * 80)
    
    # Test with batches of different sizes
    batch_sizes = [2, 3, 5]
    
    for batch_size in batch_sizes:
        batch = test_episodes[:batch_size]
        
        logger.info(f"\nTesting batch of {batch_size} episodes...")
        
        start_time = datetime.now()
        result = await client.extract_batch(batch)
        duration = (datetime.now() - start_time).total_seconds()
        
        logger.info(f"Parsing completed in {duration:.2f}s")
        logger.info(f"Parsing strategy used: {result.parsing_metadata.get('strategy', 'unknown')}")
        logger.info(f"Total entities extracted: {result.total_entities}")
        logger.info(f"Total relationships extracted: {result.total_relationships}")
        
        # Show per-episode results
        for episode in result.episodes:
            logger.info(f"  Episode {episode.episode_index}: "
                       f"{len(episode.entities)} entities, "
                       f"{len(episode.relationships)} relationships")
            
            # Show some extracted data
            if episode.entities:
                entity_names = [e.name for e in episode.entities[:3]]
                logger.info(f"    Sample entities: {', '.join(entity_names)}")
            
            if episode.relationships:
                rel = episode.relationships[0]
                logger.info(f"    Sample relationship: {rel.source} -> {rel.target} ({rel.relation_type})")
        
        # Calculate extraction rate
        expected_min_entities = batch_size * 2  # At least 2 entities per episode
        extraction_rate = (result.total_entities / expected_min_entities) * 100 if expected_min_entities > 0 else 0
        logger.info(f"Extraction rate: {extraction_rate:.1f}% of expected minimum")
        
        logger.info("-" * 40)
    
    logger.info("\n" + "=" * 80)
    logger.info("Testing complete!")
    
    # Test error recovery
    logger.info("\n" + "=" * 80)
    logger.info("Testing Error Recovery Capabilities")
    logger.info("=" * 80)
    
    # Test with malformed responses
    parser = RobustJSONParser()
    
    test_cases = [
        ("Clean JSON", '{"episodes": [{"entities": [{"name": "Alice", "type": "person"}]}]}'),
        ("Markdown JSON", '```json\n{"episodes": [{"entities": [{"name": "Bob", "type": "person"}]}]}\n```'),
        ("Partial JSON", '{"episodes": [{"entities": [{"name": "Charlie", "type": "pers'),
        ("Mixed text", 'Here are the results:\nEpisode 0:\nEntity: David (person)\nEntity: TechCorp (organization)'),
        ("Malformed", "This is not valid JSON at all but mentions Alice and Bob"),
    ]
    
    for name, test_content in test_cases:
        logger.info(f"\nTesting: {name}")
        result = parser.parse(test_content, expected_episodes=1)
        logger.info(f"  Strategy: {result.parsing_metadata.get('strategy', 'unknown')}")
        logger.info(f"  Entities found: {result.total_entities}")
        if result.total_entities > 0 and result.episodes:
            entities = result.episodes[0].entities
            if entities:
                logger.info(f"  First entity: {entities[0].name}")


if __name__ == "__main__":
    asyncio.run(test_robust_batch_parsing())