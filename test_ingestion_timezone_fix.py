#!/usr/bin/env python3
"""Test that ingestion correctly adds timezone to valid_at timestamps."""

import asyncio
from datetime import datetime, timezone
from graphiti_core import Graphiti
from graphiti_core.nodes import EpisodicNode
from graphiti_core.edges import EpisodeType
from graphiti_core.driver import FalkorDriver
from graphiti_core.llm_client import LLMClient, OpenAIClient
from graphiti_core.embedder import OpenAIEmbedder

async def test_ingestion_timezone_handling():
    """Test that naive reference_time gets timezone info."""
    
    print("=" * 60)
    print("TESTING INGESTION TIMEZONE HANDLING")
    print("=" * 60)
    
    # Initialize components
    driver = FalkorDriver(
        host="localhost",
        port=6379,
        database="test_ingestion_tz"
    )
    
    llm = OpenAIClient()  # Or mock for testing
    embedder = OpenAIEmbedder()
    
    graphiti = Graphiti(driver, llm, embedder)
    
    # Test cases
    test_cases = [
        ("Naive datetime", datetime(2024, 8, 15, 9, 30, 0)),
        ("Aware datetime (UTC)", datetime(2024, 8, 15, 9, 30, 0, tzinfo=timezone.utc)),
    ]
    
    for description, reference_time in test_cases:
        print(f"\n{description}:")
        print(f"  Input reference_time: {reference_time}")
        print(f"  Has timezone: {reference_time.tzinfo is not None}")
        
        # Add episode with the reference_time
        name = f"Test_{description.replace(' ', '_')}"
        result = await graphiti.add_episode(
            name=name,
            episode_body="Test content for timezone validation",
            reference_time=reference_time,
            source=EpisodeType.text,
            source_description="Test"
        )
        
        # Retrieve the episode to check valid_at format
        episode = await EpisodicNode.get_by_uuid(driver, result.episode.uuid)
        
        print(f"  Stored valid_at: {episode.valid_at}")
        print(f"  Has timezone in stored value: {episode.valid_at.tzinfo is not None}")
        
        # Check the ISO format
        iso_str = episode.valid_at.isoformat()
        has_tz_suffix = '+00:00' in iso_str or 'Z' in iso_str
        print(f"  ISO format: {iso_str}")
        print(f"  Has timezone suffix: {'✅' if has_tz_suffix else '❌'}")
        
        # Also check created_at for comparison
        created_iso = episode.created_at.isoformat()
        print(f"  created_at format: {created_iso}")
    
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print("Both naive and timezone-aware reference_time values")
    print("should result in valid_at with +00:00 timezone suffix")
    
    # Clean up test database
    await driver.close()

# Note: This would need actual LLM/embedder setup to run completely
print("Test script created. Would need full Graphiti setup to execute.")
print("\nThe fix ensures that all valid_at timestamps will have timezone info")
print("by calling ensure_utc(reference_time) during episode creation.")
