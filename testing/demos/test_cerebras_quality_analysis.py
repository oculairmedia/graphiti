#!/usr/bin/env python3
"""
Cerebras Quality Analysis Test
Tests entity extraction, relationship detection, and summary generation quality
No database required - focuses on LLM output quality
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any
from datetime import datetime
from pydantic import BaseModel, Field

# Add path for imports
import sys
sys.path.append('/opt/stacks/graphiti')

from graphiti_core.llm_client.cerebras_client import CerebrasClient
from graphiti_core.llm_client.config import LLMConfig
from graphiti_core.prompts import models

# Test data with expected outputs
TEST_EPISODES = [
    {
        "name": "tech_meeting",
        "content": "Alice from Microsoft and Bob from Google met in Seattle on January 15, 2024 to discuss AI collaboration. They agreed to share research on large language models and set up monthly sync meetings. The project budget was set at $5 million.",
        "expected_entities": ["Alice", "Bob", "Microsoft", "Google", "Seattle", "AI collaboration", "large language models"],
        "expected_relationships": [
            ("Alice", "works at", "Microsoft"),
            ("Bob", "works at", "Google"),
            ("Alice", "met with", "Bob"),
            ("Microsoft", "collaborates with", "Google")
        ]
    },
    {
        "name": "product_launch",
        "content": "Sarah announced that DataCorp will launch CloudSync 2.0 on March 1st. The new version includes real-time collaboration, end-to-end encryption, and supports up to 10TB storage. The pricing starts at $99/month for teams. Beta testing showed 40% performance improvement over version 1.0.",
        "expected_entities": ["Sarah", "DataCorp", "CloudSync 2.0", "real-time collaboration", "encryption", "10TB storage"],
        "expected_relationships": [
            ("Sarah", "works at", "DataCorp"),
            ("DataCorp", "launches", "CloudSync 2.0"),
            ("CloudSync 2.0", "includes", "real-time collaboration"),
            ("CloudSync 2.0", "includes", "encryption")
        ]
    },
    {
        "name": "research_findings",
        "content": "Dr. Chen's team at MIT discovered a new quantum algorithm that reduces computation time by 60%. The algorithm, named QuantumBoost, can solve NP-complete problems faster than classical computers. IBM and Intel have expressed interest in licensing the technology.",
        "expected_entities": ["Dr. Chen", "MIT", "quantum algorithm", "QuantumBoost", "IBM", "Intel", "NP-complete problems"],
        "expected_relationships": [
            ("Dr. Chen", "works at", "MIT"),
            ("Dr. Chen", "discovered", "quantum algorithm"),
            ("quantum algorithm", "named", "QuantumBoost"),
            ("IBM", "interested in", "QuantumBoost"),
            ("Intel", "interested in", "QuantumBoost")
        ]
    }
]

class QualityMetrics:
    """Track quality metrics for evaluation."""
    
    def __init__(self):
        self.entity_precision = 0.0
        self.entity_recall = 0.0
        self.relationship_precision = 0.0
        self.relationship_recall = 0.0
        self.summary_coherence = 0.0
        self.extraction_errors = []
        self.timing = {}
    
    def calculate_precision_recall(self, extracted: List[str], expected: List[str]) -> tuple:
        """Calculate precision and recall for lists."""
        extracted_set = set(str(e).lower() for e in extracted)
        expected_set = set(str(e).lower() for e in expected)
        
        if not extracted_set:
            return 0.0, 0.0
            
        true_positives = len(extracted_set & expected_set)
        precision = true_positives / len(extracted_set) if extracted_set else 0
        recall = true_positives / len(expected_set) if expected_set else 0
        
        return precision, recall

async def test_entity_extraction(client: CerebrasClient, episode: Dict) -> Dict[str, Any]:
    """Test entity extraction quality."""
    print(f"\n  Testing entity extraction for: {episode['name']}")
    
    start = time.time()
    try:
        # Use the actual entity extraction prompt format
        messages = [
            {"role": "system", "content": "You are an AI assistant that extracts entities and relationships from text."},
            {"role": "user", "content": f"Extract all entities and their relationships from the following text:\n\n{episode['content']}"}
        ]
        
        response = await client.generate_response(
            messages=messages,
            response_model=models.EntityExtractionResponse
        )
        
        extraction_time = time.time() - start
        
        # Extract entity names
        extracted_entities = [entity.name for entity in response.entities] if response else []
        
        # Calculate metrics
        metrics = QualityMetrics()
        precision, recall = metrics.calculate_precision_recall(
            extracted_entities, 
            episode['expected_entities']
        )
        
        print(f"    ✓ Extracted {len(extracted_entities)} entities in {extraction_time:.2f}s")
        print(f"    📊 Precision: {precision:.2%}, Recall: {recall:.2%}")
        
        # Show what was found vs expected
        if precision < 1.0 or recall < 1.0:
            extracted_set = set(e.lower() for e in extracted_entities)
            expected_set = set(e.lower() for e in episode['expected_entities'])
            missed = expected_set - extracted_set
            extra = extracted_set - expected_set
            
            if missed:
                print(f"    ⚠️  Missed entities: {', '.join(missed)}")
            if extra:
                print(f"    ℹ️  Extra entities: {', '.join(extra)}")
        
        return {
            "success": True,
            "entities": extracted_entities,
            "precision": precision,
            "recall": recall,
            "f1_score": 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0,
            "time": extraction_time,
            "response": response
        }
        
    except Exception as e:
        print(f"    ✗ Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

async def test_relationship_extraction(client: CerebrasClient, episode: Dict, entity_response) -> Dict[str, Any]:
    """Test relationship extraction quality."""
    print(f"\n  Testing relationship extraction for: {episode['name']}")
    
    if not entity_response or not entity_response.get('success'):
        print("    ⚠️  Skipping - no entities extracted")
        return {"success": False, "error": "No entities available"}
    
    start = time.time()
    try:
        response = entity_response.get('response')
        if not response:
            return {"success": False, "error": "No response object"}
            
        # Extract relationships from the response
        extracted_relationships = []
        for entity in response.entities:
            for edge in entity.entity_edges:
                rel = (entity.name, edge.relation_type, edge.target_entity)
                extracted_relationships.append(rel)
        
        extraction_time = time.time() - start
        
        # Normalize for comparison
        extracted_normalized = [
            (s.lower(), r.lower(), t.lower()) 
            for s, r, t in extracted_relationships
        ]
        expected_normalized = [
            (s.lower(), r.lower(), t.lower()) 
            for s, r, t in episode['expected_relationships']
        ]
        
        # Calculate metrics
        metrics = QualityMetrics()
        # For relationships, we check exact matches
        matches = sum(1 for rel in extracted_normalized if any(
            all(word in rel_str for word in exp_str.split())
            for rel_str in [' '.join(rel)]
            for exp_str in [' '.join(exp)]
            for exp in expected_normalized
        ))
        
        precision = matches / len(extracted_normalized) if extracted_normalized else 0
        recall = matches / len(expected_normalized) if expected_normalized else 0
        
        print(f"    ✓ Extracted {len(extracted_relationships)} relationships in {extraction_time:.2f}s")
        print(f"    📊 Precision: {precision:.2%}, Recall: {recall:.2%}")
        
        if len(extracted_relationships) < 5:
            for rel in extracted_relationships:
                print(f"      • {rel[0]} --[{rel[1]}]--> {rel[2]}")
        
        return {
            "success": True,
            "relationships": extracted_relationships,
            "precision": precision,
            "recall": recall,
            "f1_score": 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0,
            "time": extraction_time
        }
        
    except Exception as e:
        print(f"    ✗ Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

async def test_summary_generation(client: CerebrasClient, episode: Dict) -> Dict[str, Any]:
    """Test summary generation quality."""
    print(f"\n  Testing summary generation for: {episode['name']}")
    
    start = time.time()
    try:
        messages = [
            {"role": "system", "content": "You are an AI assistant that creates concise summaries."},
            {"role": "user", "content": f"Summarize the following in 2-3 sentences:\n\n{episode['content']}"}
        ]
        
        response = await client.generate_response(messages=messages)
        generation_time = time.time() - start
        
        # Analyze summary quality
        summary_length = len(response.split()) if response else 0
        has_key_entities = sum(1 for entity in episode['expected_entities'][:3] 
                              if entity.lower() in response.lower()) if response else 0
        
        quality_score = min(1.0, has_key_entities / 3)  # How many of top 3 entities mentioned
        
        print(f"    ✓ Generated {summary_length}-word summary in {generation_time:.2f}s")
        print(f"    📊 Quality score: {quality_score:.2%} (key entities mentioned)")
        
        if summary_length < 100:  # Only show if reasonably short
            print(f"    📝 Summary: {response[:200]}...")
        
        return {
            "success": True,
            "summary": response,
            "word_count": summary_length,
            "quality_score": quality_score,
            "time": generation_time
        }
        
    except Exception as e:
        print(f"    ✗ Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

async def main():
    """Run comprehensive quality analysis."""
    print("=" * 60)
    print("🔬 CEREBRAS QUALITY ANALYSIS TEST")
    print("=" * 60)
    print(f"Model: qwen-3-coder-480b")
    print(f"Start: {datetime.now().isoformat()}\n")
    
    # Initialize client
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("❌ CEREBRAS_API_KEY not set")
        return
    
    config = LLMConfig(
        api_key=api_key,
        model="qwen-3-coder-480b",
        base_url="https://api.cerebras.ai/v1",
        temperature=0.1,
        max_tokens=1000
    )
    client = CerebrasClient(config=config)
    print("✓ Cerebras client initialized\n")
    
    all_results = []
    
    for episode in TEST_EPISODES:
        print(f"\n{'='*50}")
        print(f"📄 Episode: {episode['name']}")
        print(f"{'='*50}")
        
        results = {"episode": episode['name']}
        
        # Test entity extraction
        entity_result = await test_entity_extraction(client, episode)
        results["entities"] = entity_result
        
        # Test relationship extraction (uses entity results)
        rel_result = await test_relationship_extraction(client, episode, entity_result)
        results["relationships"] = rel_result
        
        # Test summary generation
        summary_result = await test_summary_generation(client, episode)
        results["summary"] = summary_result
        
        all_results.append(results)
    
    # Calculate overall metrics
    print(f"\n{'='*60}")
    print("📊 OVERALL QUALITY METRICS")
    print(f"{'='*60}")
    
    # Entity metrics
    entity_scores = [r["entities"]["f1_score"] for r in all_results if r["entities"].get("success")]
    avg_entity_f1 = sum(entity_scores) / len(entity_scores) if entity_scores else 0
    
    # Relationship metrics
    rel_scores = [r["relationships"]["f1_score"] for r in all_results if r["relationships"].get("success")]
    avg_rel_f1 = sum(rel_scores) / len(rel_scores) if rel_scores else 0
    
    # Summary metrics
    summary_scores = [r["summary"]["quality_score"] for r in all_results if r["summary"].get("success")]
    avg_summary_quality = sum(summary_scores) / len(summary_scores) if summary_scores else 0
    
    # Timing metrics
    entity_times = [r["entities"]["time"] for r in all_results if r["entities"].get("success")]
    avg_entity_time = sum(entity_times) / len(entity_times) if entity_times else 0
    
    print(f"\n🎯 Quality Scores:")
    print(f"  • Entity Extraction F1: {avg_entity_f1:.2%}")
    print(f"  • Relationship Extraction F1: {avg_rel_f1:.2%}")
    print(f"  • Summary Quality: {avg_summary_quality:.2%}")
    print(f"  • Overall Quality: {(avg_entity_f1 + avg_rel_f1 + avg_summary_quality) / 3:.2%}")
    
    print(f"\n⏱️  Performance:")
    print(f"  • Avg Entity Extraction: {avg_entity_time:.2f}s")
    print(f"  • Total API calls: {len(all_results) * 3}")
    
    print(f"\n💡 Analysis:")
    if avg_entity_f1 < 0.7:
        print("  ⚠️  Entity extraction needs improvement (F1 < 70%)")
    if avg_rel_f1 < 0.5:
        print("  ⚠️  Relationship extraction needs improvement (F1 < 50%)")
    if avg_summary_quality < 0.6:
        print("  ⚠️  Summary generation needs improvement (Quality < 60%)")
    
    if avg_entity_f1 > 0.8 and avg_rel_f1 > 0.6:
        print("  ✅ Quality is acceptable for production use")
    else:
        print("  ⚠️  Consider using Ollama for better quality at the cost of speed")
    
    # Save detailed results
    with open("cerebras_quality_results.json", "w") as f:
        json.dump({
            "timestamp": datetime.now().isoformat(),
            "model": "qwen-3-coder-480b",
            "metrics": {
                "entity_f1": avg_entity_f1,
                "relationship_f1": avg_rel_f1,
                "summary_quality": avg_summary_quality,
                "avg_response_time": avg_entity_time
            },
            "details": all_results
        }, f, indent=2, default=str)
    
    print(f"\n💾 Detailed results saved to cerebras_quality_results.json")
    print("=" * 60)

if __name__ == "__main__":
    asyncio.run(main())