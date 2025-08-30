#!/usr/bin/env python3
"""
Cerebras Structured Output Quality Test
Tests entity extraction and relationship detection using Cerebras' structured output capabilities
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Any
from datetime import datetime
from cerebras.cloud.sdk import Cerebras

# Test scenarios with expected outputs
TEST_EPISODES = [
    {
        "name": "tech_meeting",
        "content": "Alice from Microsoft and Bob from Google met in Seattle on January 15, 2024 to discuss AI collaboration. They agreed to share research on large language models and set up monthly sync meetings. The project budget was set at $5 million.",
        "expected_entities": ["Alice", "Bob", "Microsoft", "Google", "Seattle", "AI collaboration", "large language models"],
        "expected_relationships": [
            ("Alice", "works_at", "Microsoft"),
            ("Bob", "works_at", "Google"), 
            ("Alice", "met_with", "Bob"),
            ("Microsoft", "collaborates_with", "Google")
        ]
    },
    {
        "name": "product_launch", 
        "content": "Sarah announced that DataCorp will launch CloudSync 2.0 on March 1st. The new version includes real-time collaboration, end-to-end encryption, and supports up to 10TB storage. The pricing starts at $99/month for teams.",
        "expected_entities": ["Sarah", "DataCorp", "CloudSync 2.0", "real-time collaboration", "encryption", "10TB storage"],
        "expected_relationships": [
            ("Sarah", "works_at", "DataCorp"),
            ("DataCorp", "launches", "CloudSync 2.0"),
            ("CloudSync 2.0", "includes", "real-time collaboration")
        ]
    }
]

# JSON Schemas for structured outputs
entity_extraction_schema = {
    "type": "object",
    "properties": {
        "entities": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "type": {"type": "string"},
                    "description": {"type": "string"}
                },
                "required": ["name", "type"],
                "additionalProperties": False
            }
        },
        "relationships": {
            "type": "array", 
            "items": {
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "relation": {"type": "string"},
                    "target": {"type": "string"},
                    "confidence": {"type": "number"}
                },
                "required": ["source", "relation", "target"],
                "additionalProperties": False
            }
        }
    },
    "required": ["entities", "relationships"],
    "additionalProperties": False
}

summary_schema = {
    "type": "object",
    "properties": {
        "summary": {"type": "string"},
        "key_points": {
            "type": "array",
            "items": {"type": "string"}
        },
        "word_count": {"type": "integer"}
    },
    "required": ["summary", "key_points"],
    "additionalProperties": False
}

def calculate_precision_recall(extracted: List[str], expected: List[str]) -> tuple:
    """Calculate precision and recall."""
    extracted_set = set(str(e).lower() for e in extracted)
    expected_set = set(str(e).lower() for e in expected)
    
    if not extracted_set:
        return 0.0, 0.0
        
    true_positives = len(extracted_set & expected_set)
    precision = true_positives / len(extracted_set) if extracted_set else 0
    recall = true_positives / len(expected_set) if expected_set else 0
    
    return precision, recall

async def test_entity_extraction(client: Cerebras, episode: Dict) -> Dict[str, Any]:
    """Test structured entity extraction."""
    print(f"\n  🔍 Testing entity extraction: {episode['name']}")
    
    start = time.time()
    try:
        response = client.chat.completions.create(
            model="llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system", 
                    "content": "You are an expert at extracting entities and relationships from text. Extract all meaningful entities (people, organizations, locations, concepts) and their relationships."
                },
                {
                    "role": "user",
                    "content": f"Extract entities and relationships from this text:\n\n{episode['content']}"
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "entity_extraction", 
                    "strict": True,
                    "schema": entity_extraction_schema
                }
            },
            temperature=0.1
        )
        
        extraction_time = time.time() - start
        
        # Parse the structured response
        result = json.loads(response.choices[0].message.content)
        
        entities = [entity["name"] for entity in result["entities"]]
        relationships = [(rel["source"], rel["relation"], rel["target"]) for rel in result["relationships"]]
        
        # Calculate entity metrics
        entity_precision, entity_recall = calculate_precision_recall(entities, episode['expected_entities'])
        entity_f1 = 2 * (entity_precision * entity_recall) / (entity_precision + entity_recall) if (entity_precision + entity_recall) > 0 else 0
        
        # Calculate relationship metrics (simplified matching)
        rel_matches = 0
        for extracted_rel in relationships:
            for expected_rel in episode['expected_relationships']:
                if (extracted_rel[0].lower() in expected_rel[0].lower() or expected_rel[0].lower() in extracted_rel[0].lower()) and \
                   (extracted_rel[2].lower() in expected_rel[2].lower() or expected_rel[2].lower() in extracted_rel[2].lower()):
                    rel_matches += 1
                    break
        
        rel_precision = rel_matches / len(relationships) if relationships else 0
        rel_recall = rel_matches / len(episode['expected_relationships']) if episode['expected_relationships'] else 0
        rel_f1 = 2 * (rel_precision * rel_recall) / (rel_precision + rel_recall) if (rel_precision + rel_recall) > 0 else 0
        
        print(f"    ✓ Extracted {len(entities)} entities, {len(relationships)} relationships ({extraction_time:.2f}s)")
        print(f"    📊 Entity F1: {entity_f1:.2%}, Relationship F1: {rel_f1:.2%}")
        
        # Show what was found
        if len(entities) <= 8:
            print(f"    🏷️  Entities: {', '.join(entities)}")
        if len(relationships) <= 5:
            for rel in relationships:
                print(f"      • {rel[0]} --[{rel[1]}]--> {rel[2]}")
        
        return {
            "success": True,
            "entities": entities,
            "relationships": relationships, 
            "entity_precision": entity_precision,
            "entity_recall": entity_recall,
            "entity_f1": entity_f1,
            "rel_precision": rel_precision,
            "rel_recall": rel_recall,
            "rel_f1": rel_f1,
            "time": extraction_time,
            "raw_response": result
        }
        
    except Exception as e:
        print(f"    ✗ Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

async def test_summary_generation(client: Cerebras, episode: Dict) -> Dict[str, Any]:
    """Test structured summary generation."""
    print(f"\n  📝 Testing summary generation: {episode['name']}")
    
    start = time.time()
    try:
        response = client.chat.completions.create(
            model="llama-4-scout-17b-16e-instruct",
            messages=[
                {
                    "role": "system",
                    "content": "You are an expert at creating concise, informative summaries. Create a summary with key points."
                },
                {
                    "role": "user", 
                    "content": f"Summarize this text in 2-3 sentences and extract 3-5 key points:\n\n{episode['content']}"
                }
            ],
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "summary_generation",
                    "strict": True,
                    "schema": summary_schema
                }
            },
            temperature=0.1
        )
        
        generation_time = time.time() - start
        result = json.loads(response.choices[0].message.content)
        
        summary = result["summary"]
        key_points = result["key_points"]
        word_count = len(summary.split()) if summary else 0
        
        # Quality assessment - check if key entities are mentioned
        entities_mentioned = sum(1 for entity in episode['expected_entities'][:5] 
                                if entity.lower() in summary.lower()) if summary else 0
        quality_score = entities_mentioned / min(5, len(episode['expected_entities']))
        
        print(f"    ✓ Generated {word_count}-word summary with {len(key_points)} key points ({generation_time:.2f}s)")
        print(f"    📊 Quality score: {quality_score:.2%} (key entities mentioned)")
        
        if word_count < 150:
            print(f"    📄 Summary: {summary}")
        
        return {
            "success": True,
            "summary": summary,
            "key_points": key_points,
            "word_count": word_count, 
            "quality_score": quality_score,
            "time": generation_time,
            "raw_response": result
        }
        
    except Exception as e:
        print(f"    ✗ Error: {str(e)}")
        return {
            "success": False,
            "error": str(e),
            "time": time.time() - start
        }

async def main():
    """Run structured output quality tests."""
    print("=" * 70)
    print("🧠 CEREBRAS STRUCTURED OUTPUT QUALITY TEST")
    print("=" * 70)
    print(f"Model: llama-4-scout-17b-16e-instruct")
    print(f"Start: {datetime.now().isoformat()}\n")
    
    # Initialize client
    api_key = os.environ.get("CEREBRAS_API_KEY")
    if not api_key:
        print("❌ CEREBRAS_API_KEY not set")
        return
    
    client = Cerebras(api_key=api_key)
    print("✓ Cerebras client initialized")
    
    all_results = []
    
    for episode in TEST_EPISODES:
        print(f"\n{'='*50}")
        print(f"📄 Episode: {episode['name']}")
        print(f"Content: {episode['content'][:100]}...")
        print(f"{'='*50}")
        
        results = {"episode": episode['name']}
        
        # Test structured entity extraction
        entity_result = await test_entity_extraction(client, episode)
        results["entities"] = entity_result
        
        # Test structured summary generation
        summary_result = await test_summary_generation(client, episode)
        results["summary"] = summary_result
        
        all_results.append(results)
    
    # Calculate overall metrics
    print(f"\n{'='*70}")
    print("📊 OVERALL QUALITY ANALYSIS")
    print(f"{'='*70}")
    
    # Entity metrics
    entity_f1_scores = [r["entities"]["entity_f1"] for r in all_results if r["entities"].get("success")]
    avg_entity_f1 = sum(entity_f1_scores) / len(entity_f1_scores) if entity_f1_scores else 0
    
    # Relationship metrics  
    rel_f1_scores = [r["entities"]["rel_f1"] for r in all_results if r["entities"].get("success")]
    avg_rel_f1 = sum(rel_f1_scores) / len(rel_f1_scores) if rel_f1_scores else 0
    
    # Summary metrics
    summary_scores = [r["summary"]["quality_score"] for r in all_results if r["summary"].get("success")]
    avg_summary_quality = sum(summary_scores) / len(summary_scores) if summary_scores else 0
    
    # Performance metrics
    entity_times = [r["entities"]["time"] for r in all_results if r["entities"].get("success")]
    summary_times = [r["summary"]["time"] for r in all_results if r["summary"].get("success")]
    avg_entity_time = sum(entity_times) / len(entity_times) if entity_times else 0
    avg_summary_time = sum(summary_times) / len(summary_times) if summary_times else 0
    
    print(f"\n🎯 Quality Metrics:")
    print(f"  • Entity Extraction F1: {avg_entity_f1:.2%}")
    print(f"  • Relationship Extraction F1: {avg_rel_f1:.2%}")
    print(f"  • Summary Quality: {avg_summary_quality:.2%}")
    print(f"  • Overall Quality Score: {(avg_entity_f1 + avg_rel_f1 + avg_summary_quality) / 3:.2%}")
    
    print(f"\n⚡ Performance:")
    print(f"  • Avg Entity Extraction: {avg_entity_time:.2f}s")
    print(f"  • Avg Summary Generation: {avg_summary_time:.2f}s")
    print(f"  • Total Response Time: {avg_entity_time + avg_summary_time:.2f}s per episode")
    
    print(f"\n💡 Assessment:")
    overall_quality = (avg_entity_f1 + avg_rel_f1 + avg_summary_quality) / 3
    
    if overall_quality >= 0.8:
        print("  ✅ Excellent quality - Ready for production use")
    elif overall_quality >= 0.6:
        print("  ✅ Good quality - Acceptable for most use cases")  
    elif overall_quality >= 0.4:
        print("  ⚠️  Moderate quality - May need prompt tuning")
    else:
        print("  ❌ Poor quality - Consider alternative models")
    
    if avg_entity_time < 2.0:
        print("  ⚡ Excellent speed - Suitable for real-time applications")
    
    # Save detailed results
    final_results = {
        "timestamp": datetime.now().isoformat(),
        "model": "llama-4-scout-17b-16e-instruct",
        "structured_outputs": True,
        "metrics": {
            "entity_f1": avg_entity_f1,
            "relationship_f1": avg_rel_f1,
            "summary_quality": avg_summary_quality,
            "overall_quality": overall_quality,
            "avg_entity_time": avg_entity_time,
            "avg_summary_time": avg_summary_time
        },
        "episodes": all_results
    }
    
    with open("cerebras_structured_quality_results.json", "w") as f:
        json.dump(final_results, f, indent=2)
    
    print(f"\n💾 Detailed results saved to cerebras_structured_quality_results.json")
    print("=" * 70)

if __name__ == "__main__":
    asyncio.run(main())